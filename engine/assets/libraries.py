"""Open-asset library integrations.

Each library implements `query(kind, ...) -> MediaAsset | None`, returning a real
asset for the kinds it serves or `None` to defer to the next source. The parsing
of each API's response is a pure function (`_parse_*`) so it's unit-testable
without network. HTTP is done lazily via httpx and any error degrades to `None`.

Libraries wired here:
  * Poly Haven  — CC0 textures / HDRIs / models (keyless)          -> image, map, model
  * Freesound   — CC0/CC-BY sounds (needs an API token)            -> sound
  * Sketchfab   — downloadable models (needs an API token)         -> model, character, animation
  * CC0 packs   — a small curated index (Kenney / OpenGameArt), no network, URIs only
"""
from __future__ import annotations

import logging

from engine.assets.models import AssetKind, MediaAsset

log = logging.getLogger("engine.assets.libraries")

_HTTP_TIMEOUT = 6.0
# Poly Haven's API ToS requires a unique, app-identifying User-Agent per caller.
_USER_AGENT = "EEG-Horror-Engine/0.1 (+https://github.com/NebByte/EEG-horror-game-1)"


def _http_get_json(url: str, params: dict | None = None, headers: dict | None = None):
    """Lazy httpx GET returning parsed JSON, or None on any failure."""
    try:
        import httpx
    except ImportError:
        log.warning("httpx not installed; remote asset libraries disabled.")
        return None
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=_HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001 — never break a run on a fetch error
        log.info("asset fetch failed for %s (%s)", url, exc)
        return None


def _pick(items: list, seed: int):
    return items[seed % len(items)] if items else None


class LibrarySource:
    name = "library"
    kinds: tuple[AssetKind, ...] = ()

    def __init__(self) -> None:
        self._cache: dict = {}

    def handles(self, kind: AssetKind) -> bool:
        return kind in self.kinds

    def query(self, kind: AssetKind, seed: int, mood: str, tags: list[str],
              fears: list[str], escalation: float) -> MediaAsset | None:
        if not self.handles(kind):
            return None
        key = (kind, tuple(tags[:3]))
        if key not in self._cache:
            self._cache[key] = self._search(kind, tags, fears)  # list of candidates
        cands = self._cache[key] or []
        chosen = _pick(cands, seed)
        return self._to_asset(kind, chosen, seed) if chosen else None

    # subclasses implement:
    def _search(self, kind: AssetKind, tags: list[str], fears: list[str]) -> list:
        return []

    def _to_asset(self, kind: AssetKind, item, seed: int) -> MediaAsset | None:
        return None


# --------------------------------------------------------------------------- #
# Poly Haven — CC0, keyless
# --------------------------------------------------------------------------- #
_POLYHAVEN_TYPE = {"image": "textures", "map": "hdris", "model": "models"}


def _parse_polyhaven_assets(data: dict) -> list[dict]:
    """The /assets endpoint returns {id: {name, categories, ...}}."""
    out = []
    for aid, meta in (data or {}).items():
        out.append({"id": aid, "name": meta.get("name", aid), "categories": meta.get("categories", [])})
    return out


# The /assets endpoint only yields ids; the browser needs a *direct* image/glTF
# URL, not the metadata endpoint. /files/{id} returns the real per-resolution
# download map, which these pure parsers turn into a single loadable URL. We
# prefer the lightest resolution so the client download stays small.
_TEX_COLOR_KEYS = ("diffuse", "diff", "albedo", "color", "col")
_RES_ORDER = ("1k", "2k", "4k", "8k")


def _first_res(node: dict) -> dict | None:
    """Pick the smallest listed resolution (1k first) from a file-type node."""
    if not isinstance(node, dict):
        return None
    for res in _RES_ORDER:
        if isinstance(node.get(res), dict):
            return node[res]
    for v in node.values():          # any resolution we didn't anticipate
        if isinstance(v, dict):
            return v
    return None


def _file_url(fmt_node: dict, formats: tuple[str, ...]) -> str | None:
    """First format whose entry carries a url (preferred formats first)."""
    if not isinstance(fmt_node, dict):
        return None
    for f in formats:
        entry = fmt_node.get(f)
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    for entry in fmt_node.values():
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    return None


def _polyhaven_texture_url(files: dict) -> str | None:
    """A direct colour/diffuse texture URL (jpg/png) from a /files response."""
    if not isinstance(files, dict):
        return None
    lowered = {k.lower(): k for k in files}      # keys vary in case: Diffuse/diff/...
    for want in _TEX_COLOR_KEYS:
        if want in lowered:
            url = _file_url(_first_res(files[lowered[want]]) or {}, ("jpg", "png"))
            if url:
                return url
    return None


def _polyhaven_model_files(files: dict) -> dict | None:
    """{'url': gltf_url, 'includes': {relpath: url}} for the glTF variant, or None.

    Poly Haven glTF is multi-file (a .gltf plus .bin and textures); the client
    must rewrite those relative includes to their absolute URLs, so we surface
    the whole include map alongside the entry point."""
    if not isinstance(files, dict):
        return None
    node = (_first_res(files.get("gltf") or {}) or {}).get("gltf")
    if not isinstance(node, dict) or not node.get("url"):
        return None
    includes = {rel: meta["url"] for rel, meta in (node.get("include") or {}).items()
                if isinstance(meta, dict) and meta.get("url")}
    return {"url": node["url"], "includes": includes}


def _polyhaven_hdri_url(files: dict) -> str | None:
    """A direct HDRI/tonemapped URL from a /files response."""
    if not isinstance(files, dict):
        return None
    tm = files.get("tonemapped")
    if isinstance(tm, dict) and tm.get("url"):
        return tm["url"]
    return _file_url(_first_res(files.get("hdri") or {}) or {}, ("hdr", "exr"))


class PolyHavenLibrary(LibrarySource):
    name = "polyhaven"
    kinds = ("image", "map", "model")
    BASE = "https://api.polyhaven.com"

    def _search(self, kind, tags, fears):
        data = _http_get_json(f"{self.BASE}/assets", params={"type": _POLYHAVEN_TYPE[kind]},
                              headers={"User-Agent": _USER_AGENT})
        items = _parse_polyhaven_assets(data or {})
        # Prefer assets whose categories intersect our tags (dark/industrial/etc).
        wanted = set(t.lower() for t in tags)
        items.sort(key=lambda a: len(wanted & set(c.lower() for c in a["categories"])), reverse=True)
        return items[:40]

    def _resolve_uri(self, kind: str, aid: str, params: dict) -> str | None:
        """Turn an asset id into a direct, browser-loadable URL (one lazy GET)."""
        files = _http_get_json(f"{self.BASE}/files/{aid}", headers={"User-Agent": _USER_AGENT})
        if not files:
            return None
        if kind == "image":
            return _polyhaven_texture_url(files)
        if kind == "map":
            return _polyhaven_hdri_url(files)
        if kind == "model":
            mf = _polyhaven_model_files(files)
            if mf:
                params["includes"] = mf["includes"]   # for the client's URL rewriter
                return mf["url"]
        return None

    def _to_asset(self, kind, item, seed):
        aid = item["id"]
        params = {"provider": "polyhaven", "asset_id": aid, "type": _POLYHAVEN_TYPE[kind]}
        # A direct download URL when we can resolve it; else the metadata endpoint
        # (the client just falls back to procedural art if the URL isn't media).
        uri = self._resolve_uri(kind, aid, params) or f"{self.BASE}/files/{aid}"
        return MediaAsset(
            id=f"polyhaven:{aid}", kind=kind, name=item["name"], source="remote:polyhaven",
            uri=uri, tags=item.get("categories", []),
            license="CC0", attribution="Poly Haven (CC0)",
            source_url=f"https://polyhaven.com/a/{aid}", seed=seed, params=params)


# --------------------------------------------------------------------------- #
# Freesound — needs an API token
# --------------------------------------------------------------------------- #
def _parse_freesound(data: dict) -> list[dict]:
    return list((data or {}).get("results", []))


class FreesoundLibrary(LibrarySource):
    name = "freesound"
    kinds = ("sound",)
    BASE = "https://freesound.org/apiv2"

    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token

    def _search(self, kind, tags, fears):
        if not self.token:
            return []
        query = " ".join(dict.fromkeys((tags[:2] + fears[:1]) or ["horror ambience"]))
        # Token in the Authorization header, not the query string (keeps the
        # secret out of URLs/logs).
        data = _http_get_json(f"{self.BASE}/search/text/", params={
            "query": query, "fields": "id,name,license,username,previews,url",
            "filter": "duration:[2.0 TO 60.0]", "page_size": 30},
            headers={"Authorization": f"Token {self.token}"})
        return _parse_freesound(data or {})

    def _to_asset(self, kind, item, seed):
        prev = (item.get("previews") or {})
        return MediaAsset(
            id=f"freesound:{item['id']}", kind="sound", name=item.get("name", "sound"),
            source="remote:freesound", uri=prev.get("preview-hq-mp3") or prev.get("preview-lq-mp3"),
            license=item.get("license"), attribution=f"{item.get('username','?')} via Freesound",
            source_url=item.get("url"), seed=seed,
            params={"provider": "freesound", "sound_id": item["id"]})


# --------------------------------------------------------------------------- #
# Sketchfab — needs an API token
# --------------------------------------------------------------------------- #
def _parse_sketchfab(data: dict) -> list[dict]:
    return list((data or {}).get("results", []))


class SketchfabLibrary(LibrarySource):
    name = "sketchfab"
    kinds = ("model", "character", "animation")
    BASE = "https://api.sketchfab.com/v3"

    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token

    def _search(self, kind, tags, fears):
        if not self.token:
            return []
        q = " ".join(dict.fromkeys((tags[:2] + fears[:1]) or ["horror"]))
        if kind == "animation":
            q += " animated"
        # Build params without `animated` by default — httpx serialises None as an
        # empty query value (`animated=`) rather than omitting it.
        params = {"type": "models", "q": q, "downloadable": "true", "count": 24}
        if kind == "animation":
            params["animated"] = "true"
        data = _http_get_json(f"{self.BASE}/search", params=params,
                              headers={"Authorization": f"Token {self.token}"})
        return _parse_sketchfab(data or {})

    def _to_asset(self, kind, item, seed):
        lic = (item.get("license") or {})
        return MediaAsset(
            id=f"sketchfab:{item['uid']}", kind=kind, name=item.get("name", "model"),
            source="remote:sketchfab", uri=item.get("viewerUrl") or item.get("uri"),
            license=lic.get("label"), attribution=f"{(item.get('user') or {}).get('username','?')} via Sketchfab",
            source_url=item.get("viewerUrl"), seed=seed,
            params={"provider": "sketchfab", "uid": item["uid"], "downloadable": item.get("isDownloadable", False)})


# --------------------------------------------------------------------------- #
# Curated CC0 packs — no network, URIs only (Kenney / OpenGameArt)
# --------------------------------------------------------------------------- #
_CC0_PACKS = {
    "model": [("Kenney — Graveyard Kit", "https://kenney.nl/assets/graveyard-kit"),
              ("Kenney — Furniture Kit", "https://kenney.nl/assets/furniture-kit")],
    "character": [("Kenney — Character pack", "https://kenney.nl/assets/blocky-characters")],
    "image": [("OpenGameArt — Horror textures", "https://opengameart.org/art-search?keys=horror+texture")],
    "sound": [("Kenney — Impact sounds", "https://kenney.nl/assets/impact-sounds")],
    "animation": [("Mixamo — export required (Adobe login)", "https://www.mixamo.com/")],
}


class Cc0PackLibrary(LibrarySource):
    name = "cc0pack"
    kinds = ("model", "character", "image", "sound", "animation")

    def _search(self, kind, tags, fears):
        return _CC0_PACKS.get(kind, [])

    def _to_asset(self, kind, item, seed):
        name, url = item
        return MediaAsset(
            id=f"cc0:{kind}:{seed & 0xffff:04x}", kind=kind, name=name, source="pack",
            uri=url, license="CC0", attribution=name, source_url=url, seed=seed,
            params={"provider": "cc0pack", "pack": name})

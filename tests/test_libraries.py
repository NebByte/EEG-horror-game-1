"""Multiple asset libraries: routing, per-kind fallback, response parsing, and
the licensing manifest — all without network."""
from __future__ import annotations

from engine.assets.libraries import (Cc0PackLibrary, LibrarySource,
                                     _parse_freesound, _parse_polyhaven_assets,
                                     _parse_sketchfab, _polyhaven_hdri_url,
                                     _polyhaven_model_files, _polyhaven_texture_url)
from engine.assets.models import MediaAsset
from engine.assets.resolver import license_manifest
from engine.assets.sources import MultiLibrarySource, ProceduralAssetSource


class _FakeSoundLib(LibrarySource):
    name = "fake"
    kinds = ("sound",)

    def _search(self, kind, tags, fears):
        return [{"id": 42}]

    def _to_asset(self, kind, item, seed):
        return MediaAsset(id="fake:42", kind="sound", name="scream", source="remote:fake",
                          uri="http://x/y.mp3", license="CC-BY", attribution="tester", seed=seed)


def test_routes_to_library_then_falls_back_to_procedural():
    src = MultiLibrarySource([_FakeSoundLib()])
    # sound -> served by the fake library
    snd = src.fetch("sound", 1, "dread", ["x"], ["darkness"], 0.5)
    assert snd.source == "remote:fake" and snd.uri.endswith(".mp3")
    # map -> the library doesn't handle it -> procedural fallback
    mp = src.fetch("map", 1, "dread", ["x"], ["darkness"], 0.5)
    assert mp.source == "procedural" and mp.kind == "map"


def test_library_miss_falls_back():
    class _Empty(LibrarySource):
        kinds = ("sound",)
        def _search(self, kind, tags, fears):
            return []
    src = MultiLibrarySource([_Empty()])
    snd = src.fetch("sound", 3, "dread", [], [], 0.4)
    assert snd.source == "procedural"


def test_cc0_pack_offline_returns_uris():
    lib = Cc0PackLibrary()
    a = lib.query("model", 5, "dread", ["decay"], ["darkness"], 0.5)
    assert a and a.source == "pack" and a.uri.startswith("http") and a.license == "CC0"


def test_parsers():
    ph = _parse_polyhaven_assets({"rock_wall": {"name": "Rock Wall", "categories": ["rock"]}})
    assert ph[0]["id"] == "rock_wall" and ph[0]["name"] == "Rock Wall"
    fs = _parse_freesound({"results": [{"id": 1, "name": "drip"}]})
    assert fs[0]["id"] == 1
    sk = _parse_sketchfab({"results": [{"uid": "abc", "name": "statue"}]})
    assert sk[0]["uid"] == "abc"


def test_polyhaven_resolves_direct_urls_from_files_response():
    # A /files response shaped like Poly Haven's: nested type -> res -> format.
    tex_files = {
        "Diffuse": {"1k": {"jpg": {"url": "https://dl/ph/diff_1k.jpg"},
                           "png": {"url": "https://dl/ph/diff_1k.png"}},
                    "2k": {"jpg": {"url": "https://dl/ph/diff_2k.jpg"}}},
        "nor_gl": {"1k": {"jpg": {"url": "https://dl/ph/nor_1k.jpg"}}},
    }
    # smallest resolution, jpg preferred over png
    assert _polyhaven_texture_url(tex_files) == "https://dl/ph/diff_1k.jpg"
    # non-colour maps alone must not resolve as a colour texture
    assert _polyhaven_texture_url({"nor_gl": tex_files["nor_gl"]}) is None

    model_files = {
        "gltf": {"1k": {"gltf": {"url": "https://dl/ph/statue_1k.gltf",
                                 "include": {"statue_1k.bin": {"url": "https://dl/ph/statue_1k.bin"},
                                             "textures/col.jpg": {"url": "https://dl/ph/col.jpg"}}}}},
        "blend": {"1k": {"blend": {"url": "https://dl/ph/statue.blend"}}},
    }
    mf = _polyhaven_model_files(model_files)
    assert mf["url"] == "https://dl/ph/statue_1k.gltf"
    assert mf["includes"]["textures/col.jpg"] == "https://dl/ph/col.jpg"
    assert _polyhaven_model_files({"blend": model_files["blend"]}) is None

    assert _polyhaven_hdri_url({"tonemapped": {"url": "https://dl/ph/tm.jpg"}}) == "https://dl/ph/tm.jpg"
    assert _polyhaven_hdri_url({"hdri": {"1k": {"hdr": {"url": "https://dl/ph/sky_1k.hdr"}}}}) \
        == "https://dl/ph/sky_1k.hdr"
    assert _polyhaven_texture_url({}) is None and _polyhaven_model_files(None) is None


def test_license_manifest_dedups_and_skips_procedural():
    assets = {
        "a": [MediaAsset(id="polyhaven:x", kind="image", name="Wall", source="remote:polyhaven",
                         license="CC0", attribution="Poly Haven", source_url="http://p/x").model_dump()],
        "b": [ProceduralAssetSource().fetch("sound", 1, "dread", [], [], 0.5).model_dump()],
        "c": [MediaAsset(id="polyhaven:x", kind="image", name="Wall", source="remote:polyhaven",
                         license="CC0", attribution="Poly Haven", source_url="http://p/x").model_dump()],
    }
    man = license_manifest(assets)
    assert len(man) == 1  # procedural skipped, duplicate deduped
    assert man[0]["attribution"] == "Poly Haven"

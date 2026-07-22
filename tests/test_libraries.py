"""Multiple asset libraries: routing, per-kind fallback, response parsing, and
the licensing manifest — all without network."""
from __future__ import annotations

from engine.assets.libraries import (Cc0PackLibrary, LibrarySource,
                                     _parse_freesound, _parse_polyhaven_assets,
                                     _parse_sketchfab)
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

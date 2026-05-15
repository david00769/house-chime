from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from custom_components.house_chime.media import async_media_exists


class FakeConfig:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, *parts: str) -> str:
        return str(self.root.joinpath(*parts))


class FakeHass:
    def __init__(self, root: Path) -> None:
        self.config = FakeConfig(root)


class MediaTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_media_source_exists_under_config_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_file = root / "media" / "announcements" / "front-door.mp3"
            media_file.parent.mkdir(parents=True)
            media_file.write_bytes(b"mp3")

            exists = await async_media_exists(
                FakeHass(root),
                "media-source://media_source/local/announcements/front-door.mp3",
            )

        self.assertTrue(exists)

    async def test_local_media_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exists = await async_media_exists(
                FakeHass(Path(tmp)),
                "media-source://media_source/local/announcements/missing.mp3",
            )

        self.assertFalse(exists)


if __name__ == "__main__":
    unittest.main()

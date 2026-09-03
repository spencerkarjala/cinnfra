import importlib.util
import tempfile
import unittest

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("import-music.py")
SPEC = importlib.util.spec_from_file_location("import_music", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
import_music = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(import_music)


class FakeAudio:
    def __init__(self, tags):
        self.tags = tags


class CheckReleasesReadyTests(unittest.TestCase):
    def test_only_returns_releases_with_every_track_marked_done(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ready_path = root / "ready"
            unfinished_path = root / "unfinished"
            ready_path.mkdir()
            unfinished_path.mkdir()

            ready_tracks = [ready_path / "one.flac", ready_path / "two.flac"]
            unfinished_tracks = [
                unfinished_path / "one.flac",
                unfinished_path / "two.flac",
            ]
            for track in ready_tracks + unfinished_tracks:
                track.touch()

            tags_by_path = {
                ready_tracks[0]: {"done": ["1"]},
                ready_tracks[1]: {"DONE": ["yes"]},
                unfinished_tracks[0]: {"done": ["1"]},
                unfinished_tracks[1]: {"done": ["no"]},
            }

            with patch.object(
                import_music.mutagen,
                "File",
                side_effect=lambda path: FakeAudio(tags_by_path[Path(path)]),
            ):
                ready_releases = import_music.check_releases_ready(
                    [
                        import_music.Release(path=ready_path),
                        import_music.Release(path=unfinished_path),
                    ]
                )

            self.assertEqual(ready_releases, [import_music.Release(path=ready_path)])


class MainTests(unittest.TestCase):
    def test_only_ready_releases_are_processed_and_failures_do_not_block_others(self):
        valid_path = Path("/music/todo/valid")
        invalid_path = Path("/music/todo/invalid")
        unfinished_path = Path("/music/todo/unfinished")
        valid_release = import_music.Release(path=valid_path)
        invalid_release = import_music.Release(path=invalid_path)
        validation_failure = import_music.FailedRelease(
            path=invalid_path,
            error="missing tags",
        )

        with (
            patch.object(
                import_music,
                "identify_release_directories",
                return_value=[valid_path, invalid_path, unfinished_path],
            ),
            patch.object(
                import_music,
                "check_releases_ready",
                return_value=[valid_release, invalid_release],
            ),
            patch.object(
                import_music,
                "preprocess_releases",
                return_value=([valid_release, invalid_release], []),
            ) as preprocess_releases,
            patch.object(
                import_music,
                "validate_releases",
                return_value=([valid_release], [validation_failure]),
            ),
            patch.object(
                import_music,
                "publish_releases",
                return_value=([valid_release], []),
            ) as publish_releases,
            redirect_stdout(StringIO()),
        ):
            import_music.main()

        preprocess_releases.assert_called_once_with([valid_path, invalid_path])
        publish_releases.assert_called_once_with(
            [valid_release],
            import_music.LIBRARY_PATH,
        )


if __name__ == "__main__":
    unittest.main()

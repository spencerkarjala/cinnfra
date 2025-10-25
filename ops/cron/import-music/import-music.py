from pathlib import Path
from dataclasses import dataclass
import mutagen
import re

ROOT_MUSIC_DIR = Path("/music/")

def identify_release_directories(root_dir: Path) -> list[Path]:
    """
    Returns the list of all release directories recursively under the provided `root_dir`. That is,
    the list of all leaf directories in the directory tree rooted at root_dir.
    """
    leaf_dirs = []

    def find_leaf_dirs(directory: Path) -> None:
        try:
            subdirs = [d for d in directory.iterdir() if d.is_dir()]

            if not subdirs:
                leaf_dirs.append(directory)
            else:
                for subdir in subdirs:
                    find_leaf_dirs(subdir)
        except PermissionError:
            print(f"Warning: Permission denied accessing {directory}, skipping")

    if root_dir.is_dir():
        find_leaf_dirs(root_dir)

    return leaf_dirs


@dataclass
class Release:
    path: Path


@dataclass
class FailedRelease:
    path: Path
    error: str


def preprocess_releases(releases: list[Path]) -> tuple[list[Release], list[FailedRelease]]:
    """
    Check every track in every release to strip out consistent metadata issues.

    Returns:
    - successful_releases: list of Release objects that passed preprocessing
    - failed_releases: list of FailedRelease objects with error info
    """
    successful_releases = []
    failed_releases = []

    bandcamp_comment_pattern = re.compile(r"Visit https://.*\.bandcamp\.com", re.IGNORECASE)

    def is_music_file(file_path: Path) -> bool:
        try:
            return mutagen.File(file_path) is not None
        except Exception:
            return False

    def preprocess_track(track_path: Path) -> None:
        """
        Preprocess a single track - check and set metadata.
        Currently removes bandcamp spam from comment fields.
        """
        audio = mutagen.File(track_path)
        if audio is None:
            return

        # Clear out any "Visit us at bandcamp.com" comments
        if hasattr(audio, 'tags') and audio.tags:
            for tag in audio.tags:
                # Each key can be a single string, or a (tag, value) tuple
                tag_normalized = tag[0].lower() if isinstance(tag, tuple) else tag.lower()

                if tag_normalized == "comment":
                    comment_value = audio.tags.get(tag)
                    comment_text = comment_value[0] if isinstance(comment_value, list) else str(comment_value)

                    if bandcamp_comment_pattern.search(comment_text):
                        del audio.tags[tag]
                        audio.save()

    # Loop over and preprocess all tracks in the release, collecting errors as they arise
    for release_path in releases:
        track_errors = []

        for file_path in release_path.iterdir():
            if file_path.is_file() and is_music_file(file_path):
                try:
                    preprocess_track(file_path)
                except Exception as e:
                    track_errors.append(f"{file_path.name}: {str(e)}")

        if track_errors:
            error_message = "; ".join(track_errors)
            failed_releases.append(FailedRelease(path=release_path, error=error_message))
        else:
            successful_releases.append(Release(path=release_path))

    return successful_releases, failed_releases


def validate_releases(releases: list[Release]) -> tuple[list[Release], list[FailedRelease]]:
    """
    Validates each release by checking every track.
    Checks things like:
    - Can we open the file?
    - Is it a valid WAV/FLAC/etc?
    - Does it have required metadata fields?
    - Other validation rules we'll add later

    Returns:
    - valid_releases: list of Release objects that passed validation
    - failed_releases: list of FailedRelease objects with error info
    """
    pass


def check_releases_ready(releases: list[Release]) -> list[Release]:
    """
    Check if releases are marked as "done" and ready to publish.
    For each release, checks that every track has a "done" metadata field
    set to "1" or "true" (or similar truthy value).

    Returns list of Release objects that are ready to publish.
    """
    pass


def publish_releases(releases: list[Release], library_path: Path) -> tuple[list[Release], list[FailedRelease]]:
    """
    Move releases to the library directory.
    For each release:
    - Check if it already exists in library
    - If exists, verify every file matches exactly (checksums/sizes)
    - If mismatch, don't overwrite and add to failed list
    - If doesn't exist or matches, copy/move to library

    Does NOT delete from to-import directory (will happen next iteration).

    Returns:
    - successfully_published: list of Release objects that were published
    - failed_to_publish: list of FailedRelease objects with error info
    """
    pass


def main() -> None:
    releases_to_validate = identify_release_directories(ROOT_MUSIC_DIR)

    # Step 1: Preprocess to catch annoying issues
    preprocessed_releases, preprocess_failures = preprocess_releases(releases_to_validate)

    print(preprocess_failures)

    # Step 2: Validate releases
    # validated_releases, validation_failures = validate_releases(preprocessed_releases)

    # Step 3: Check which valid releases are marked as "done"
    # ready_to_publish = check_releases_ready(validated_releases)

    # Step 4: Publish releases to library
    # published, publish_failures = publish_releases(ready_to_publish, LIBRARY_PATH)

    # TODO: Log/report results
    # - How many preprocessed
    # - How many passed validation
    # - Preprocess failures and why
    # - Validation failures and why
    # - How many ready to publish
    # - Successfully published
    # - Publish failures and why

if __name__ == "__main__":
    main()

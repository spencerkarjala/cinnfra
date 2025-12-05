import base64
import hashlib
import mutagen
import re
import subprocess
import traceback

from dataclasses import dataclass
from pathlib import Path
from PIL import Image
from typing import Any, Optional

ROOT_MUSIC_DIR = Path("/music/todo/")

TARGET_LOSSLESS_CODEC = ".flac"
TARGET_LOSSY_CODEC = ".opus"
SUPPORTED_LOSSLESS_CODECS = {'FLAC', 'WAV', 'AIFF', 'WavPack', 'ALAC', 'APE', 'TrueAudio'}
SUPPORTED_LOSSY_CODECS = {'MP3', 'Vorbis', 'Opus', 'AAC', 'WMA', 'OGG'}

file_extension_to_codec = {
    '.flac': 'FLAC',
    '.wav': 'WAV',
    '.aiff': 'AIFF',
    '.wv': 'WavPack',
    '.ape': 'APE',
    '.mp3': 'MP3',
    '.ogg': 'OGG',
    '.opus': 'Opus',
    '.m4a': 'AAC',
    '.mp4': 'AAC',
    '.wma': 'WMA',
}


def _normalize_mutagen_tag_key(raw_key: Any) -> str:
    """
    Sometimes, mutagen keys are not simply strings. This function normalizes them.
    """
    if isinstance(raw_key, tuple):
        raw_key = raw_key[0]
    return str(raw_key)


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


def is_music_file(file_path: Path) -> bool:
    try:
        return mutagen.File(file_path) is not None
    except Exception:
        return False


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

    def enforce_release_permissions(release_path: Path) -> None:
        """
        Verify ownership is 1000:1000 and enforce 755 permissions on release directory and all files.
        """
        expected_uid = 1000
        expected_gid = 1000
        expected_permissions = 0o755

        dir_stat = release_path.stat()
        if dir_stat.st_uid != expected_uid or dir_stat.st_gid != expected_gid:
            raise PermissionError(
                f"Directory ownership mismatch: expected {expected_uid}:{expected_gid}, "
                f"got {dir_stat.st_uid}:{dir_stat.st_gid}"
            )

        for file_path in release_path.iterdir():
            if file_path.is_file():
                file_stat = file_path.stat()
                if file_stat.st_uid != expected_uid or file_stat.st_gid != expected_gid:
                    raise PermissionError(
                        f"{file_path.name}: ownership mismatch: expected {expected_uid}:{expected_gid}, "
                        f"got {file_stat.st_uid}:{file_stat.st_gid}"
                    )

        release_path.chmod(expected_permissions)
        for file_path in release_path.iterdir():
            if file_path.is_file():
                file_path.chmod(expected_permissions)

    def transcode_release(release_path: Path) -> None:
        """
        Transcode all tracks in release to standard pre-chosen formats.
        """
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue

            audio = mutagen.File(file_path)
            if audio is None:
                raise ValueError(f"Unable to open audio file: {file_path}")

            codec = file_extension_to_codec.get(file_path.suffix.lower())
            if codec is None:
                raise ValueError(f"Unknown file extension: {file_path.suffix}")

            is_lossless = codec in SUPPORTED_LOSSLESS_CODECS
            is_lossy = codec in SUPPORTED_LOSSY_CODECS

            if not is_lossless and not is_lossy:
                raise ValueError(f"Unknown codec: {codec}")
            elif is_lossless and is_lossy:
                raise ValueError(f"File is both lossless and lossy: {file_path}")

            if (
                codec == file_extension_to_codec[TARGET_LOSSLESS_CODEC]
                or codec == file_extension_to_codec[TARGET_LOSSY_CODEC]
            ):
                continue

            if is_lossless:
                new_path = file_path.with_suffix('.flac')
                subprocess.run([
                    'ffmpeg', '-i', str(file_path),
                    '-c:a', 'flac',
                    '-y',
                    str(new_path)
                ], check=True, capture_output=True)
            else:
                new_path = file_path.with_suffix('.opus')
                subprocess.run([
                    'ffmpeg', '-i', str(file_path),
                    '-c:a', 'libopus',
                    '-b:a', '192k',
                    '-y',
                    str(new_path)
                ], check=True, capture_output=True)

            if not new_path.exists():
                raise RuntimeError(f"Transcoded file not created: {new_path}")

            file_path.unlink()

    def embed_release_cover_art(release_path: Path) -> None:
        """
        Ensure all tracks have embedded cover art from cover.jpg in release directory.
        Converts any cover.* file to cover.jpg if needed.
        """
        # Find any file named "cover" (case-insensitive, any extension)
        cover_path = None
        for file_path in release_path.iterdir():
            if file_path.is_file() and file_path.stem.lower() == 'cover':
                cover_path = file_path
                break

        if cover_path is None:
            raise FileNotFoundError("No cover image found")

        # If not exactly "cover.jpg", re-encode to JPEG; inefficient, but simple
        target_cover_path = release_path / 'cover.jpg'
        if cover_path.name != 'cover.jpg':
            img = Image.open(cover_path)
            # Convert to RGB if needed (e.g., for PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = rgb_img
            img.save(target_cover_path, 'JPEG', quality=95)

            if not target_cover_path.exists():
                raise RuntimeError(f"Failed to create {target_cover_path}")

            cover_path.unlink()
            cover_path = target_cover_path

        with open(cover_path, 'rb') as f:
            cover_data = f.read()

        cover_hash = hashlib.sha256(cover_data).digest()

        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue

            audio = mutagen.File(file_path)
            if audio is None:
                continue

            embedded_data = None

            if hasattr(audio, 'pictures') and audio.pictures:
                embedded_data = audio.pictures[0].data
            elif (
                isinstance(audio, mutagen.oggopus.OggOpus)
                and 'metadata_block_picture' in audio
                and len(audio['metadata_block_picture']) > 0
            ):
                picture_data = base64.b64decode(audio['metadata_block_picture'][0])
                picture = mutagen.flac.Picture(raw_block)
                embedded_data = picture.data

            if embedded_data:
                embedded_hash = hashlib.sha256(embedded_data).digest()
                if embedded_hash == cover_hash:
                    continue

            print(f"  Embedding cover art into {file_path.name}")

            # Both flac and opus use Vorbis comments for metadata, so they can both have cover art
            # embedded with mutagen.flac.Picture
            picture = mutagen.flac.Picture()
            picture.type = 3
            picture.mime = 'image/jpeg'
            picture.data = cover_data
            if isinstance(audio, mutagen.flac.FLAC):
                audio.clear_pictures()
                audio.add_picture(picture)
                audio.save()
            elif isinstance(audio, mutagen.oggopus.OggOpus):
                audio['metadata_block_picture'] = [base64.b64encode(picture.write()).decode('ascii')]
                audio.save()
            else:
                raise ValueError(f"Cover image embedding encountered unexpected audio type: {type(audio)} for {file_path}")

    def preprocess_release_metadata(release_path: Path) -> None:
        """
        Clean up metadata across a release.
        """
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue

            audio = mutagen.File(file_path)
            if audio is None:
                raise ValueError(f"Unable to open audio file: {file_path}")

            if not hasattr(audio, "tags") or not audio.tags:
                continue

            for tag in list(audio.tags.keys()):
                tag_str = _normalize_mutagen_tag_key(tag)

                if tag_str.lower() == "comment":
                    comment_value = audio.tags.get(tag)
                    if comment_value == None:
                        comment_text = ""
                    elif isinstance(comment_value, list):
                        comment_value[0] if comment_value else ""
                    else:
                        comment_text = str(comment_value)

                    if bandcamp_comment_pattern.search(comment_text):
                        del audio.tags[tag]
                        audio.save()

    def enforce_label_publisher_consistency(release_path: Path) -> None:
        """
        If any of label/publisher/tpub (case-insensitive) are set on any track in the release,
        enforce that:
        - all three upper-case keys ('LABEL', 'PUBLISHER', 'TPUB') exist on every track that has at least one defined, and
        - they all have the same value for that track.
        """
        canonical_keys = ["LABEL", "PUBLISHER", "TPUB"]

        # First pass: see if any of these tags exist at all in the release
        any_present = False
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue
            audio = mutagen.File(file_path)
            if audio is None or not getattr(audio, "tags", None):
                continue
            for key in list(audio.tags.keys()):
                tag_str = _normalize_mutagen_tag_key(key)
                if tag_str.upper() in canonical_keys:
                    any_present = True
                    break
            if any_present:
                break

        if not any_present:
            return

        # Second pass: normalize keys and values on each track
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue

            audio = mutagen.File(file_path)
            if audio is None:
                raise ValueError(f"Unable to open audio file: {file_path}")

            if not hasattr(audio, "tags") or audio.tags is None:
                raise ValueError(f"Missing tags on file while enforcing label/publisher consistency: {file_path}")

            tags = audio.tags

            # Collect any existing values for label/publisher/tpub (case-insensitive)
            values: list[str] = []
            keys_to_delete: list[str] = []

            for tag in list(audio.tags.keys()):
                tag_str = _normalize_mutagen_tag_key(tag)
                upper = tag_str.upper()
                if upper in canonical_keys:
                    value = audio.tags[tag]
                    if isinstance(value, (list, tuple)):
                        if not value:
                            continue
                        value = value[0]
                    value_str = str(value)
                    if value_str:
                        values.append(value_str)
                    # We'll re-write under canonical upper-case keys
                    keys_to_delete.append(tag)

            # Remove old variants (including non-uppercase)
            for key in keys_to_delete:
                if key in audio.tags:
                    del audio.tags[key]

            # Decide the canonical value for this track, if any
            canonical_value = None
            if values:
                # Require that all existing values on this track match
                first = values[0]
                for v in values[1:]:
                    if v != first:
                        raise ValueError(
                            f"Inconsistent label/publisher/tpub values in file {file_path}: {values}"
                        )
                canonical_value = first

            # If we have a value, set all three canonical upper-case keys to that value
            if canonical_value is not None:
                for ck in canonical_keys:
                    tags[ck] = canonical_value

            audio.save()

    def normalize_all_tag_keys_to_uppercase(release_path: Path) -> None:
        """
        For every track in the release, convert all tag keys to uppercase.

        If a uppercase key already exists and we are raising another variant of it,
        we keep the existing uppercase key's value and drop the non-uppercase one.
        """
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue
            audio = mutagen.File(file_path)
            if audio is None or not getattr(audio, "tags", None):
                continue

            tags = audio.tags
            original_tags = list(tags.keys())

            for raw_tag in original_tags:
                key_str = _normalize_mutagen_tag_key(raw_tag)
                upper = key_str.upper()
                if key_str == upper:
                    continue

                value = tags[raw_tag]
                del tags[raw_tag]

                if upper in tags:
                    continue
                tags[upper] = value

            audio.save()

    def preprocess_release(release_path: Path) -> None:
        """
        Release-level preprocessing: permissions, transcoding, cover art, metadata cleanup.
        """
        enforce_release_permissions(release_path)
        transcode_release(release_path)
        embed_release_cover_art(release_path)
        preprocess_release_metadata(release_path)
        enforce_label_publisher_consistency(release_path)
        normalize_all_tag_keys_to_uppercase(release_path)

    for release_path in releases:
        try:
            preprocess_release(release_path)
            successful_releases.append(Release(path=release_path))
        except Exception as e:
            tb = traceback.format_exc()
            error_text = f"{repr(e)}\n{tb}"
            print(f"Error while preprocessing {release_path}:\n{error_text}")
            failed_releases.append(FailedRelease(path=release_path, error=error_text))

    return successful_releases, failed_releases


def validate_releases(releases: list[Release]) -> None:
    def validate_all_tag_keys_uppercase(release_path: Path) -> None:
        """
        Ensure that all tag keys on all tracks in the release are uppercase.
        """
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue

            audio = mutagen.File(file_path)
            if audio is None or not getattr(audio, "tags", None):
                continue

            for raw_key in audio.tags.keys():
                key_str = _normalize_mutagen_tag_key(raw_key)
                if key_str != key_str.upper():
                    raise ValueError(
                        f"Non-uppercase tag key {key_str!r} found in file {file_path}; "
                        f"all tag keys must be uppercase."
                    )

    def validate_release_labels(release_path: Path) -> None:
        """
        Enforce that any label-related tags are identical across the entire release.
        """
        canonical_keys = ["LABEL", "PUBLISHER", "TPUB"]
        canonical_keys_upper = {k.upper() for k in canonical_keys}

        # First, check if there are any label tags to validate
        any_present = False
        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue
            audio = mutagen.File(file_path)
            if audio is None or not getattr(audio, "tags", None):
                continue
            for key in audio.tags.keys():
                if _normalize_mutagen_tag_key(key).upper() in canonical_keys_upper:
                    any_present = True
                    break
            if any_present:
                break

        if not any_present:
            return

        release_value: Optional[str] = None

        for file_path in release_path.iterdir():
            if not file_path.is_file() or not is_music_file(file_path):
                continue

            audio = mutagen.File(file_path)
            if audio is None or not getattr(audio, "tags", None):
                raise ValueError(f"Missing tags on file while validating label/publisher/tpub: {file_path}")

            tags = audio.tags

            # Force an error if any values are found that aren't all upper-case
            for key in list(tags.keys()):
                key_str = _normalize_mutagen_tag_key(key)
                if key_str.upper() in canonical_keys_upper and key_str not in canonical_keys:
                    raise ValueError(
                        f"Non-canonical label key {key_str!r} in {file_path}; "
                        f"use uppercase {canonical_keys} only."
                    )

            # Collect the values for each label field on this track
            stored_label_values: list[str] = []
            for ck in canonical_keys:
                if ck in tags:
                    value = tags[ck]
                    if isinstance(value, (list, tuple)):
                        if not value:
                            continue
                        value = value[0]
                    value_str = str(value).strip()
                    if value_str:
                        stored_label_values.append(value_str)

            if not stored_label_values:
                raise ValueError(
                    f"File {file_path} has no label/publisher/tpub set, "
                    f"but other files in the release do."
                )

            # Enforce all keys have the same value
            first = stored_label_values[0]
            for v in stored_label_values[1:]:
                if v != first:
                    raise ValueError(
                        f"Inconsistent label tags in file {file_path}: {stored_label_values}"
                    )

            track_value = first

            # Release-wide consistency (same value on every track)
            if release_value is None:
                release_value = track_value
            elif release_value != track_value:
                raise ValueError(
                    f"Inconsistent label across release: file {file_path} has {track_value!r}, "
                    f"expected {release_value!r}"
                )

    for release in releases:
        validate_all_tag_keys_uppercase(release.path)
        validate_release_labels(release.path)


def check_releases_ready(releases: list[Release]) -> list[Release]:
    """
    Check if releases are marked as "done" and ready to publish.
    For each release, checks that every track has a "done" metadata field
    set to a truthy value ("1", "true", "yes", "y", case-insensitive).

    Returns list of Release objects that are ready to publish.
    """
    ready_releases: list[Release] = []

    def is_track_done(audio: mutagen.FileType) -> bool:
        if not hasattr(audio, "tags") or audio.tags is None:
            return False

        tags = audio.tags
        truthy_values = {"1", "true", "yes", "y"}

        if "DONE" not in tags:
            return False

        value = tags["DONE"]
        if isinstance(value, (list, tuple)):
            if not value:
                return False;
            value = value[0]
        
        value_str = str(value).strip().lower()
        return value_str in truthy_values

    for release in releases:
        all_done = True
        at_least_one_done = False

        for file_path in release.path.iterdir():
            if not file_path.is_file():
                continue

            try:
                audio = mutagen.File(file_path)
            except Exception:
                audio = None

            if audio is None:
                continue

            if not is_track_done(audio):
                all_done = False
                break

            at_least_one_done = True
            print(f"Found a file marked 'done': {file_path}")

        if all_done:
            print(f"Including release in releases to publish: {release.path}")
            ready_releases.append(release)
        elif at_least_one_done:
            print(f"Found a partially-done release: {release.path}")

    return ready_releases


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

    if preprocess_failures:
        print("failures:")
        for failure in preprocess_failures:
            print(f"--- {failure.path} ---")
            print(failure.error)
            print()

    validate_releases(preprocessed_releases)

    # Step 2: Check which valid releases are marked as "done"
    ready_to_publish = check_releases_ready(preprocessed_releases)
    print("ready releases:")
    print(ready_to_publish)

    # Step 3: Publish releases to library
    # published, publish_failures = publish_releases(ready_to_publish, LIBRARY_PATH)


if __name__ == "__main__":
    main()

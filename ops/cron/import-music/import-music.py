from pathlib import Path
from dataclasses import dataclass
from PIL import Image
import mutagen
import re
import stat
import subprocess
import hashlib

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

    def embed_cover_art(release_path: Path) -> None:
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

        # If not exactly "cover.jpg", re-encode to JPEG
        target_cover_path = release_path / 'cover.jpg'
        if cover_path.name != 'cover.jpg':
            img = Image.open(cover_path)
            # Convert to RGB if needed (e.g., for PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = rgb_img
            # img.save(target_cover_path, 'JPEG', quality=95)

            if not target_cover_path.exists():
                raise RuntimeError(f"Failed to create {target_cover_path}")

            print(f"would have saved {target_cover_path} and deleted {cover_path}")
            # cover_path.unlink()
            # cover_path = target_cover_path

        # Read cover data
        # with open(cover_path, 'rb') as f:
        #     cover_data = f.read()

        # cover_hash = hashlib.sha256(cover_data).digest()

        # # Check all music files
        # for file_path in release_path.iterdir():
        #     if not file_path.is_file() or not is_music_file(file_path):
        #         continue

        #     audio = mutagen.File(file_path)
        #     if audio is None:
        #         continue

        #     # Get embedded artwork
        #     embedded_data = None

        #     # FLAC/Opus (Vorbis comments with Picture)
        #     if hasattr(audio, 'pictures') and audio.pictures:
        #         embedded_data = audio.pictures[0].data
        #     # MP3 (ID3)
        #     elif hasattr(audio, 'tags') and audio.tags:
        #         for key in audio.tags:
        #             if key.startswith('APIC'):
        #                 embedded_data = audio.tags[key].data
        #                 break

        #     # Check if embedded artwork matches cover file
        #     if embedded_data:
        #         embedded_hash = hashlib.sha256(embedded_data).digest()
        #         if embedded_hash == cover_hash:
        #             continue  # Already has correct cover

        #     # Need to embed cover art (always JPEG)
        #     if isinstance(audio, mutagen.flac.FLAC):
        #         from mutagen.flac import Picture
        #         picture = Picture()
        #         picture.type = 3
        #         picture.mime = 'image/jpeg'
        #         picture.data = cover_data
        #         audio.clear_pictures()
        #         audio.add_picture(picture)
        #         audio.save()
        #     elif isinstance(audio, mutagen.oggopus.OggOpus):
        #         from mutagen.flac import Picture
        #         import base64
        #         picture = Picture()
        #         picture.type = 3
        #         picture.mime = 'image/jpeg'
        #         picture.data = cover_data
        #         audio['metadata_block_picture'] = [base64.b64encode(picture.write()).decode('ascii')]
        #         audio.save()
        #     elif isinstance(audio, mutagen.mp3.MP3):
        #         from mutagen.id3 import APIC
        #         audio.tags.add(APIC(
        #             encoding=3,
        #             mime='image/jpeg',
        #             type=3,
        #             desc='Cover',
        #             data=cover_data
        #         ))
        #         audio.save()

    def preprocess_release(release_path: Path) -> None:
        """
        Release-level preprocessing: permissions, cover art embedding.
        """
        enforce_release_permissions(release_path)
        embed_cover_art(release_path)

    def transcode_track(track_path: Path) -> Path:
        """
        Transcode track to standard format:
        - FLAC for lossless audio
        - Opus 192k for lossy audio
        Returns the (possibly updated) track path.
        """
        audio = mutagen.File(track_path)
        if audio is None:
            raise ValueError("Unable to open audio file")

        codec = file_extension_to_codec.get(track_path.suffix.lower())
        if codec is None:
            raise ValueError(f"Unknown file extension: {track_path.suffix}")

        is_lossless = codec in SUPPORTED_LOSSLESS_CODECS
        is_lossy = codec in SUPPORTED_LOSSY_CODECS

        if not is_lossless and not is_lossy:
            raise ValueError(f"Unknown codec: {codec}")
        elif is_lossless and is_lossy:
            raise ValueError(f"Somehow received file that's both lossless and lossy: {track_path}")

        if (
            codec == file_extension_to_codec[TARGET_LOSSLESS_CODEC]
            or codec == file_extension_to_codec[TARGET_LOSSY_CODEC]
        ):
            return track_path

        if is_lossless:
            new_path = track_path.with_suffix('.flac')
            subprocess.run([
                'ffmpeg', '-i', str(track_path),
                '-c:a', 'flac',
                '-y',
                str(new_path)
            ], check=True, capture_output=True)
        else:
            new_path = track_path.with_suffix('.opus')
            subprocess.run([
                'ffmpeg', '-i', str(track_path),
                '-c:a', 'libopus',
                '-b:a', '192k',
                '-y',
                str(new_path)
            ], check=True, capture_output=True)

        if not new_path.exists():
            raise RuntimeError(f"Transcoded file not created: {new_path}")

        track_path.unlink()

        return new_path

    def preprocess_track(track_path: Path) -> Path:
        """
        Preprocess a single track - check and set metadata.
        - Removes bandcamp spam from comment fields
        Returns the (possibly updated) track path.
        """
        track_path = transcode_track(track_path)

        audio = mutagen.File(track_path)
        if audio is None:
            raise ValueError("Unable to open audio file")

        # Clear out any "Visit us at bandcamp.com" comments
        if hasattr(audio, 'tags') and audio.tags:
            for tag in audio.tags:
                # Each key can be a single string, or a (tag, value) tuple
                if isinstance(tag, tuple):
                    tag = tag[0]

                if tag.lower() == "comment":
                    comment_value = audio.tags.get(tag)
                    comment_text = comment_value[0] if isinstance(comment_value, list) else str(comment_value)

                    if bandcamp_comment_pattern.search(comment_text):
                        del audio.tags[tag]
                        audio.save()

        return track_path

    # Loop over and preprocess all tracks in the release, collecting errors as they arise
    for release_path in releases:
        try:
            preprocess_release(release_path)
        except Exception as e:
            failed_releases.append(FailedRelease(path=release_path, error=str(e)))
            continue

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

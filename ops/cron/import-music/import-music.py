from pathlib import Path

ROOT_MUSIC_DIR = Path("/music/")

# print([str(f) for f in Path("/music/").glob("**")])

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
            pass

    if root_dir.is_dir():
        find_leaf_dirs(root_dir)

    return leaf_dirs

def main() -> None:
    print(identify_release_directories(ROOT_MUSIC_DIR))

if __name__ == "__main__":
    main()

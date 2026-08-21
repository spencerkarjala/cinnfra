import os
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent.parent
REFERENCES_DATABASE_PATH = Path(
    os.environ.get("REFERENCES_DATABASE_PATH", "/output/references.db")
)
BOARDS_DATABASE_PATH = Path(
    os.environ.get("BOARDS_DATABASE_PATH", "/output/boards.db")
)
ARTWORK_DIR = Path(os.environ.get("ARTWORK_DIR", "/output"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", SOURCE_ROOT / "static"))

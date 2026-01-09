import os
from pathlib import Path

OUTPUT_DIRECTORY = Path(os.environ.get("OUTPUT_DIR", "/output"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "/output/references.db"))

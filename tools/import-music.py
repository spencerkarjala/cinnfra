from pathlib import Path

print([str(f) for f in Path("/music/").glob("**")])
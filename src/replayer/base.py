import os
from pathlib import Path

DB_DIR = Path(__file__).parent.joinpath("databases").resolve()
if not DB_DIR.exists():
    os.mkdir(DB_DIR)

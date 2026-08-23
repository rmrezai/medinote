import os
import sys
from pathlib import Path

# Ensure the backend package root is on sys.path so that `from app.xxx import ...`
# works regardless of the directory from which pytest is invoked.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('TEST_BYPASS_AUTH', 'true')

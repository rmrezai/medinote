import sys
import os
from pathlib import Path

# Ensure the backend directory is on sys.path so `from app.*` imports
# resolve correctly regardless of the working directory pytest is invoked from.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('TEST_BYPASS_AUTH', 'true')

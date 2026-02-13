import sys
from pathlib import Path
import os

root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

os.environ.setdefault("SECRET_KEY", "test-secret-key")

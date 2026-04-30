import sys
from pathlib import Path
__version__ = '1.0.0'
_ALGO = Path(__file__).resolve().parent.parent / 'algorithm'
if _ALGO.is_dir() and str(_ALGO) not in sys.path:
    sys.path.insert(0, str(_ALGO))

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT, _ROOT / 'algorithm'):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

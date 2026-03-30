"""Pytest path setup for chat package tests (algorithm on sys.path)."""
import os
import sys

# test file: algorithm/chat/tests/conftest.py -> algorithm/
_algo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _algo not in sys.path:
    sys.path.insert(0, _algo)

"""
Doc check: validate README and API specs exist.
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_readme_exists():
    assert os.path.isfile(os.path.join(_ROOT, 'README.md')), 'README.md must exist'


def test_api_specs_exist():
    api_dir = os.path.join(_ROOT, 'api')
    assert os.path.isdir(api_dir), 'api/ directory must exist'

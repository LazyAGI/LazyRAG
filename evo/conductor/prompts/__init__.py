from pathlib import Path

_DIR = Path(__file__).parent


def load(name: str) -> str:
    return (_DIR / f'{name}.md').read_text(encoding='utf-8')

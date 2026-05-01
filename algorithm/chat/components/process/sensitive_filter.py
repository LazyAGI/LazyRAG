import os
from typing import Tuple, Optional
from lazyllm import LOG


class SensitiveFilter:

    def __init__(self, keyword_path: Optional[str] = None):
        self.actree = None
        self.loaded = False
        self.keyword_count = 0

        if keyword_path:
            self._load_keywords(keyword_path)

    def _load_keywords(self, path: str):
        try:
            import ahocorasick
        except ImportError:
            LOG.error(
                '[SensitiveFilter] pyahocorasick not installed. '
                'Please install: pip install pyahocorasick'
            )
            return

        if not os.path.exists(path):
            LOG.warning(f'[SensitiveFilter] Keyword file not found: {path}')
            return

        if not os.path.isfile(path):
            LOG.warning(f'[SensitiveFilter] Path is not a file: {path}')
            return

        # Initialize AC automaton
        self.actree = ahocorasick.Automaton()

        # Load sensitive words
        loaded_count = 0
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip()
                    if word:  # skip empty lines
                        self.actree.add_word(word, (word, 'default'))
                        loaded_count += 1

            # Build failure pointers (core of the AC automaton)
            self.actree.make_automaton()
            self.loaded = True
            self.keyword_count = loaded_count

        except Exception as e:
            LOG.error(f'[SensitiveFilter] Failed to load keywords: {e}')
            self.actree = None
            self.loaded = False

    def check(self, text: str) -> Tuple[bool, str]:
        if not self.loaded or not self.actree:
            return False, ''

        if not text:
            return False, ''

        # AC automaton matching
        # iter() returns (end_index, (word, category))
        try:
            for _, (word, _) in self.actree.iter(text):
                # Return True immediately upon hitting any sensitive word
                return True, word
        except Exception as e:
            LOG.error(f'[SensitiveFilter] Error during check: {e}')
            # Default to pass on error (do not block business flow)
            return False, ''

        return False, ''

import sys
import types

from chat.components.process.sensitive_filter import SensitiveFilter


def test_sensitive_filter_returns_pass_when_not_loaded():
    filter_ = SensitiveFilter()

    assert filter_.check('anything') == (False, '')
    assert filter_.check('') == (False, '')


def test_sensitive_filter_loads_keywords_and_returns_first_match(monkeypatch, tmp_path):
    class FakeAutomaton:
        def __init__(self):
            self.words = []

        def add_word(self, word, payload):
            self.words.append((word, payload))

        def make_automaton(self):
            return None

        def iter(self, text):
            for word, payload in self.words:
                pos = text.find(word)
                if pos >= 0:
                    yield pos + len(word) - 1, payload

    monkeypatch.setitem(sys.modules, 'ahocorasick', types.SimpleNamespace(Automaton=FakeAutomaton))
    keyword_file = tmp_path / 'keywords.txt'
    keyword_file.write_text('\nblocked\nignored\n', encoding='utf-8')

    filter_ = SensitiveFilter(str(keyword_file))

    assert filter_.loaded is True
    assert filter_.keyword_count == 2
    assert filter_.check('this text is blocked') == (True, 'blocked')

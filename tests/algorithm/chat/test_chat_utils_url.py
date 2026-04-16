from chat.utils.url import get_url_basename, is_path_like, is_sane_posix_path, is_url, is_valid_path


def test_url_helpers_distinguish_urls_and_paths():
    assert is_url('https://example.com/a/b.txt') is True
    assert is_url('file:///tmp/a.txt') is True
    assert is_url('not a url') is False

    assert is_path_like('/tmp/data.txt') is True
    assert is_path_like('../docs/readme.md') is True
    assert is_path_like('C:\\temp\\data.txt') is True
    assert is_path_like('plain-text') is False


def test_is_sane_posix_path_rejects_control_chars_and_quoted_segments():
    assert is_sane_posix_path('/tmp/data.txt') is True
    assert is_sane_posix_path("/tmp/'bad'/data.txt") is False
    assert is_sane_posix_path('/tmp/data\x00.txt') is False


def test_is_valid_path_and_get_url_basename_cover_both_forms():
    assert is_valid_path('https://example.com/assets/image.png?x=1') is True
    assert is_valid_path('/var/tmp/image.png') is True
    assert is_valid_path('image.png') is False

    assert get_url_basename('https://example.com/assets/image.png?x=1') == 'image.png'
    assert get_url_basename('/var/tmp/image.png') == 'image.png'

from chat.utils.url import get_url_basename, is_path_like, is_sane_posix_path, is_url, is_valid_path


def test_url_helpers_validate_urls_and_file_urls():
    assert is_url('https://example.test/assets/chart.png') is True
    assert is_url('file:///tmp/chart.png') is True
    assert is_url('not-a-url') is False

    assert is_valid_path('https://example.test/assets/chart.png') is True
    assert is_valid_path('file:///tmp/chart.png') is True


def test_url_helpers_validate_local_paths_and_reject_malformed_paths():
    assert is_path_like('/tmp/chart.png') is True
    assert is_path_like('./chart.png') is True
    assert is_path_like('../chart.png') is True
    assert is_path_like('C:/tmp/chart.png') is True
    assert is_path_like('relative/chart.png') is False

    assert is_sane_posix_path('/tmp/chart.png') is True
    assert is_sane_posix_path('./chart.png') is True
    assert is_sane_posix_path('/tmp/"img_url"/chart.png') is False
    assert is_sane_posix_path('/tmp/chart\n.png') is False
    assert is_sane_posix_path('/tmp/chart\x00.png') is False
    assert is_sane_posix_path('relative/chart.png') is False
    assert is_sane_posix_path('') is False
    assert is_sane_posix_path(None) is False


def test_get_url_basename_handles_urls_and_paths():
    assert get_url_basename('https://example.test/assets/chart.png?token=1') == 'chart.png'
    assert get_url_basename('/tmp/chart.png') == 'chart.png'
    assert get_url_basename('./nested/chart.png') == 'chart.png'

import os

from chat.utils.static_file_url import static_file_url_from_any, static_file_url_from_full_path


def test_static_file_url_from_full_path_signs_upload_relative_path(tmp_path, monkeypatch):
    upload_root = tmp_path / 'uploads'
    image = upload_root / 'normalized_images' / 'exp9' / 'frame.jpg'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'jpg')

    monkeypatch.setenv('LAZYRAG_UPLOAD_ROOT', str(upload_root))
    monkeypatch.setenv('LAZYRAG_FILE_URL_SIGN_SECRET', 'test-secret')

    signed = static_file_url_from_full_path(str(image))
    assert signed.startswith('/static-files/normalized_images/exp9/frame.jpg?')
    assert 'expires=' in signed
    assert 'sig=' in signed


def test_static_file_url_from_any_strips_external_host_prefix(tmp_path, monkeypatch):
    upload_root = tmp_path / 'uploads'
    image = upload_root / 'normalized_images' / 'exp9' / 'frame.jpg'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'jpg')

    monkeypatch.setenv('LAZYRAG_UPLOAD_ROOT', str(upload_root))
    monkeypatch.setenv('LAZYRAG_FILE_URL_SIGN_SECRET', 'test-secret')

    raw = (
        'https://ext.lazyrag.ai:19537/var/lib/lazyrag/uploads/'
        'normalized_images/exp9/frame.jpg'
    )
    signed = static_file_url_from_any(raw)
    assert signed.startswith('/static-files/normalized_images/exp9/frame.jpg?')

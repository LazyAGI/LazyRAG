import pytest

from core.errors import AppException, AuthError, ErrorCodes, error_payload_from_exception, raise_error


def test_app_exception_string_returns_message():
    exc = AppException(http_code=400, code=1, message='Bad request')

    assert str(exc) == 'Bad request'


def test_raise_error_builds_app_exception_with_extra_message():
    with pytest.raises(AppException) as exc:
        raise_error(ErrorCodes.USER_NOT_FOUND, extra_msg='user-1')

    assert exc.value.http_code == 404
    assert exc.value.code == 1000401
    assert exc.value.message == 'User not found'
    assert exc.value.extra == 'user-1'


def test_raise_error_supports_custom_exception_class():
    with pytest.raises(AuthError) as exc:
        raise_error(ErrorCodes.INVALID_CREDENTIALS, exc_cls=AuthError)

    assert exc.value.code == 1000105


def test_error_payload_from_exception_matches_api_shape():
    exc = AppException(http_code=403, code=1000302, message='Forbidden', extra='missing permission')

    assert error_payload_from_exception(exc) == {
        'code': 1000302,
        'message': 'Forbidden',
        'ex_mesage': 'missing permission',
    }

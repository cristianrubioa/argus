import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi import status

from argus.models import AdminUser
from argus.web.auth import hash_password
from argus.web.auth import require_csrf

_CSRF_INPUT_RE = re.compile(r'name="csrf_token" value="([^"]*)"')


def _login_and_get_token(client, session):
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    client.post("/login", data={"username": "admin", "password": "secret"})
    return _CSRF_INPUT_RE.search(client.get("/settings").text).group(1)


def test_require_csrf_accepts_matching_token():
    # Setup
    request = SimpleNamespace(session={"csrf_token": "abc123"})
    # Action / Expected
    require_csrf(request, csrf_token="abc123")


def test_require_csrf_rejects_missing_session_token():
    # Setup
    request = SimpleNamespace(session={})
    # Action
    with pytest.raises(HTTPException) as exc_info:
        require_csrf(request, csrf_token="abc123")
    # Expected
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_require_csrf_rejects_missing_form_field():
    # Setup
    request = SimpleNamespace(session={"csrf_token": "abc123"})
    # Action
    with pytest.raises(HTTPException) as exc_info:
        require_csrf(request, csrf_token=None)
    # Expected
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_require_csrf_rejects_mismatched_token():
    # Setup
    request = SimpleNamespace(session={"csrf_token": "abc123"})
    # Action
    with pytest.raises(HTTPException) as exc_info:
        require_csrf(request, csrf_token="different")
    # Expected
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


_MUTATING_ROUTES = (
    ("/whitelist/authorize/999999", {}),
    ("/whitelist/revoke/999999", {}),
    ("/whitelist/rename/999999", {}),
    ("/settings", {"profile": "monitor", "language": "en", "theme": "dark", "font_size": "md", "log_retention": "1_year"}),
    ("/settings/mqtt-test", {}),
    ("/settings/enforce-review", {}),
    (
        "/settings/password",
        {"current_password": "secret", "new_password": "newpassword1", "confirm_password": "newpassword1"},
    ),
)


@pytest.mark.parametrize("path,data", _MUTATING_ROUTES)
def test_mutating_route_without_csrf_token_is_rejected(client, session, path, data):
    # Setup
    _login_and_get_token(client, session)
    # Action
    response = client.post(path, data=data)
    # Expected
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize("path,data", _MUTATING_ROUTES)
def test_mutating_route_with_mismatched_csrf_token_is_rejected(client, session, path, data):
    # Setup
    _login_and_get_token(client, session)
    # Action
    response = client.post(path, data={**data, "csrf_token": "not-the-real-token"})
    # Expected
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_mutating_route_with_matching_csrf_token_succeeds(client, session):
    # Setup
    token = _login_and_get_token(client, session)
    # Action
    response = client.post(
        "/settings/password",
        data={
            "current_password": "secret",
            "new_password": "newpassword1",
            "confirm_password": "newpassword1",
            "csrf_token": token,
        },
    )
    # Expected
    assert (response.status_code, response.url.path) == (status.HTTP_200_OK, "/settings")

import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus import profiles
from argus.models import AdminUser
from argus.web import auth
from argus.web.auth import hash_password


def test_login_success(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.post("/login", data={"username": "admin", "password": "secret"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/"


def test_login_wrong_password(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/login"
    assert "Invalid username or password" in response.text


def test_unauthenticated_request_redirects_to_login(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/login"


def test_lockout_after_max_failed_attempts(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    for _ in range(5):
        client.post("/login", data={"username": "admin", "password": "wrong"})
    # Action
    response = client.post("/login", data={"username": "admin", "password": "secret"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/login"
    assert "Too many attempts" in response.text


def test_successful_login_resets_failure_count(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    for _ in range(4):
        client.post("/login", data={"username": "admin", "password": "wrong"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    # Action
    for _ in range(3):
        client.post("/login", data={"username": "admin", "password": "wrong"})
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    # Expected
    assert "Too many attempts" not in response.text


def test_failed_login_is_logged(client, session, caplog):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    with caplog.at_level(logging.WARNING):
        client.post("/login", data={"username": "admin", "password": "wrong"})
    # Expected
    assert "Failed login attempt" in caplog.text


def test_login_error_is_localized(client, session):
    # Setup
    profiles.set_language(session, "es")
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    # Expected
    assert "Usuario o contraseña incorrectos" in response.text


def test_stale_login_attempts_are_pruned_opportunistically_by_any_failure():
    # Setup
    old_attempt_at = datetime.now(timezone.utc) - timedelta(hours=2)
    auth._login_attempts["1.2.3.4"] = (1, None, old_attempt_at)
    # Action
    auth.record_failure("5.6.7.8")
    # Expected
    assert "1.2.3.4" not in auth._login_attempts

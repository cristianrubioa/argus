from fastapi import status

from argus.models import AdminUser
from argus.web.auth import hash_password


def test_no_admin_redirects_any_request_to_register(client):
    # Action
    response = client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/register"


def test_successful_registration_creates_account_and_logs_in(client, session):
    # Action
    response = client.post(
        "/register", data={"username": "admin", "password": "longenough", "confirm_password": "longenough"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/"
    assert session.query(AdminUser).count() == 1


def test_register_unreachable_once_account_exists_get(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.get("/register")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/login"


def test_register_unreachable_once_account_exists_post(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.post(
        "/register", data={"username": "second", "password": "longenough", "confirm_password": "longenough"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/login"
    assert session.query(AdminUser).count() == 1


def test_registration_rejects_too_short_password(client, session):
    # Action
    response = client.post("/register", data={"username": "admin", "password": "short", "confirm_password": "short"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/register"
    assert "Password must be at least 8 characters" in response.text
    assert session.query(AdminUser).count() == 0


def test_registration_rejects_mismatched_confirmation(client, session):
    # Action
    response = client.post(
        "/register", data={"username": "admin", "password": "longenough", "confirm_password": "somethingelse"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/register"
    assert "Passwords don&#39;t match" in response.text
    assert session.query(AdminUser).count() == 0

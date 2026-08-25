from fastapi import status

from argus.models import AdminUser
from argus.web.auth import hash_password


def test_register_submit_button_starts_disabled(client):
    # Action
    response = client.get("/register")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="register-form-button" disabled' in response.text


def test_no_admin_redirects_any_request_to_register(client):
    # Action
    response = client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.url.path == "/register"


def test_no_admin_request_gets_a_303_with_register_location(client):
    # Action
    response = client.get("/", follow_redirects=False)
    # Expected
    assert (response.status_code, response.headers["location"]) == (status.HTTP_303_SEE_OTHER, "/register")


def test_htmx_no_admin_request_gets_an_hx_redirect_instead_of_a_303(client):
    # Action
    response = client.get("/", headers={"HX-Request": "true"}, follow_redirects=False)
    # Expected
    assert (response.status_code, response.headers["hx-redirect"]) == (status.HTTP_200_OK, "/register")


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

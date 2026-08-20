from argus.models import AdminUser
from argus.web.auth import hash_password


def test_login_success(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.post("/login", data={"username": "admin", "password": "secret"})
    # Expected
    assert response.status_code == 200
    assert response.url.path == "/"


def test_login_wrong_password(client, session):
    # Setup
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    # Action
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    # Expected
    assert response.status_code == 200
    assert response.url.path == "/login"
    assert "Invalid username or password" in response.text


def test_unauthenticated_request_redirects_to_login(client):
    # Action
    response = client.get("/")
    # Expected
    assert response.status_code == 200
    assert response.url.path == "/login"

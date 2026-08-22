from fastapi import status


def test_successful_password_change(logged_in_client):
    # Action
    response = logged_in_client.post(
        "/settings/password",
        data={"current_password": "secret", "new_password": "newpassword1", "confirm_password": "newpassword1"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Password changed." in response.text
    old_login = logged_in_client.post("/login", data={"username": "admin", "password": "secret"})
    assert "Invalid username or password" in old_login.text
    new_login = logged_in_client.post("/login", data={"username": "admin", "password": "newpassword1"})
    assert new_login.url.path == "/"


def test_wrong_current_password_rejected(logged_in_client):
    # Action
    response = logged_in_client.post(
        "/settings/password",
        data={"current_password": "wrongpass", "new_password": "newpassword1", "confirm_password": "newpassword1"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Current password is incorrect" in response.text
    still_works = logged_in_client.post("/login", data={"username": "admin", "password": "secret"})
    assert still_works.url.path == "/"


def test_mismatched_new_password_rejected(logged_in_client):
    # Action
    response = logged_in_client.post(
        "/settings/password",
        data={"current_password": "secret", "new_password": "newpassword1", "confirm_password": "somethingelse"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Passwords don&#39;t match" in response.text
    still_works = logged_in_client.post("/login", data={"username": "admin", "password": "secret"})
    assert still_works.url.path == "/"


def test_too_short_new_password_rejected(logged_in_client):
    # Action
    response = logged_in_client.post(
        "/settings/password",
        data={"current_password": "secret", "new_password": "short", "confirm_password": "short"},
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Password must be at least 8 characters" in response.text
    still_works = logged_in_client.post("/login", data={"username": "admin", "password": "secret"})
    assert still_works.url.path == "/"

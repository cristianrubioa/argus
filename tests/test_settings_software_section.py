from fastapi import status

from argus import profiles
from argus import version_check

_UPDATE_COMMAND = "curl -fsSL https://install.crubio.fyi/argus | sudo bash"


def test_software_section_has_no_code_row_when_up_to_date(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: version_check.installed_version())
    profiles.get_settings(session).version_checked_at = None
    session.commit()
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="software"' in response.text
    assert _UPDATE_COMMAND not in response.text


def test_software_section_shows_update_command_verbatim(logged_in_client, session, monkeypatch):
    # Setup
    monkeypatch.setattr(version_check, "fetch_latest_version", lambda: "99.0.0")
    profiles.get_settings(session).version_checked_at = None
    session.commit()
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert _UPDATE_COMMAND in response.text
    assert "v99.0.0" in response.text

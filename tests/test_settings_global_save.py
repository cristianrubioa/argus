from fastapi import status

from argus import profiles
from argus.models import LogRetention
from argus.models import Profile


def test_single_submit_commits_all_fields_together(logged_in_client, session):
    # Action
    response = logged_in_client.post(
        "/settings",
        data={
            "profile": "enforce",
            "language": "es",
            "theme": "light",
            "font_size": "lg",
            "log_retention": "90_days",
            "mqtt_port": "1883",
        },
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert (
        profiles.get_active_profile(session),
        profiles.get_language(session),
        profiles.get_theme(session),
        profiles.get_font_size(session),
        profiles.get_log_retention(session),
    ) == (Profile.ENFORCE, "es", "light", "lg", LogRetention.NINETY_DAYS)


def test_retention_narrow_modal_is_present(logged_in_client, session):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="retention-narrow-modal"' in response.text
    assert 'id="retention-narrow-continue"' in response.text
    assert 'id="retention-narrow-cancel"' in response.text


def test_save_button_starts_disabled(logged_in_client, session):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="settings-save-button" disabled' in response.text


def test_successful_save_shows_a_toast(logged_in_client, session):
    # Action
    response = logged_in_client.post(
        "/settings",
        data={
            "profile": "monitor",
            "language": "en",
            "theme": "dark",
            "font_size": "md",
            "log_retention": "1_year",
            "mqtt_port": "1883",
        },
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Settings saved." in response.text


def test_agent_status_poll_does_not_consume_a_pending_toast(logged_in_client, session):
    # Setup
    logged_in_client.post(
        "/settings",
        data={
            "profile": "monitor",
            "language": "en",
            "theme": "dark",
            "font_size": "md",
            "log_retention": "1_year",
            "mqtt_port": "1883",
        },
        follow_redirects=False,
    )
    # Action
    logged_in_client.get("/agent-status/partial")
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Settings saved." in response.text


def test_settings_config_fields_share_one_form_separate_from_the_password_form(logged_in_client, session):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.count('action="/settings"') == 1

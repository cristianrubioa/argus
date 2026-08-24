from fastapi import status

from argus import profiles
from argus.models import Profile


def test_single_submit_commits_all_fields_together(logged_in_client, session):
    # Action
    response = logged_in_client.post(
        "/settings", data={"profile": "enforce", "language": "es", "theme": "light", "font_size": "lg"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert (
        profiles.get_active_profile(session),
        profiles.get_language(session),
        profiles.get_theme(session),
        profiles.get_font_size(session),
    ) == (Profile.ENFORCE, "es", "light", "lg")


def test_settings_config_fields_share_one_form_separate_from_the_password_form(logged_in_client, session):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.count('action="/settings"') == 1

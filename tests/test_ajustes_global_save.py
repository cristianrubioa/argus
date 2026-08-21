from fastapi import status

from argus import profiles
from argus.models import Profile


def test_single_submit_commits_all_fields_together(logged_in_client, session):
    # Action
    response = logged_in_client.post(
        "/ajustes", data={"profile": "enforce", "language": "es", "theme": "light", "font_size": "lg"}
    )
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_active_profile(session) == Profile.ENFORCE
    assert profiles.get_language(session) == "es"
    assert profiles.get_theme(session) == "light"
    assert profiles.get_font_size(session) == "lg"


def test_ajustes_page_has_a_single_form(logged_in_client, session):
    # Action
    response = logged_in_client.get("/ajustes")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert response.text.count("<form") == 1

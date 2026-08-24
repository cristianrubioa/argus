from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from argus import profiles
from argus.db import Base
from argus.db import init_db
from argus.web import i18n
from argus.web.i18n import t


def test_t_falls_back_to_english_for_missing_key(monkeypatch):
    # Setup
    monkeypatch.setitem(i18n.TRANSLATIONS["en"], "only_in_en", "Hi")
    # Action & Expected
    assert t("only_in_en", "es") == "Hi"


def test_t_unknown_key_returns_the_key_itself():
    # Action & Expected
    assert t("does_not_exist", "en") == "does_not_exist"


def test_language_persists_via_profiles(session):
    # Setup
    assert profiles.get_language(session) == "en"
    # Action
    profiles.set_language(session, "fr")
    # Expected
    assert profiles.get_language(session) == "fr"


def test_init_db_is_idempotent_on_a_database_that_already_has_language():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)"))}
    assert "language" in columns


_BASE_SETTINGS_FORM = {"profile": "monitor", "language": "en", "theme": "dark", "font_size": "md"}


def test_language_persists_via_settings_route(logged_in_client, session):
    # Action
    response = logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "language": "de"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert profiles.get_language(session) == "de"


def test_settings_route_ignores_unsupported_language(logged_in_client, session):
    # Action
    logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "language": "xx"})
    # Expected
    assert profiles.get_language(session) == "en"


def test_dashboard_renders_in_selected_language(logged_in_client, session):
    # Setup
    profiles.set_language(session, "fr")
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["fr"]["dashboard_heading"] in response.text
    assert i18n.TRANSLATIONS["fr"]["nav_settings"] in response.text

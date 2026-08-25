from fastapi import status

from argus import profiles
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.factories import WhitelistEntryFactory
from argus.web import i18n


def test_logs_shows_device_serial(logged_in_client, session):
    # Setup
    DeviceEventFactory(device__serial="AAE9055C")
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "AAE9055C" in response.text


def test_logs_shows_placeholder_when_device_has_no_serial(logged_in_client, session):
    # Setup
    DeviceEventFactory(device__serial=None)
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "—" in response.text


def test_dashboard_shows_device_serial(logged_in_client, session):
    # Setup
    DeviceEventFactory(device__serial="AAE9055C")
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "AAE9055C" in response.text


def test_devices_page_shows_already_authorized_for_whitelisted_device(logged_in_client, session):
    # Setup
    WhitelistEntryFactory()
    # Action
    response = logged_in_client.get("/devices")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["status_already_authorized"] in response.text


def test_devices_page_shows_authorize_action_for_unwhitelisted_device(logged_in_client, session):
    # Setup
    DeviceFactory()
    # Action
    response = logged_in_client.get("/devices")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["action_authorize"] in response.text


def test_whitelist_hint_links_to_devices_page(logged_in_client, session):
    # Action
    response = logged_in_client.get("/whitelist")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<a href="/devices"' in response.text
    assert i18n.TRANSLATIONS["en"]["whitelist_hint_link"] in response.text


def test_whitelist_hint_links_in_selected_language(logged_in_client, session):
    # Setup
    profiles.set_language(session, "es")
    # Action
    response = logged_in_client.get("/whitelist")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert '<a href="/devices"' in response.text
    assert i18n.TRANSLATIONS["es"]["whitelist_hint_link"] in response.text


def test_settings_shows_security_profile_before_account_section(logged_in_client, session):
    # Action
    response = logged_in_client.get("/settings")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    security_index = response.text.index(i18n.TRANSLATIONS["en"]["settings_security_heading"])
    account_index = response.text.index(i18n.TRANSLATIONS["en"]["signed_in_as"])
    assert security_index < account_index

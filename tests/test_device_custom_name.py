from fastapi import status

from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory


def test_display_name_falls_back_to_name_when_no_custom_name(session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    # Action & Expected
    assert device.display_name == "Mass Storage"


def test_setting_a_custom_name_updates_display_name(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    response = logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    session.refresh(device)
    assert device.display_name == "Backup SSD"


def test_clearing_the_custom_name_reverts_display_name_to_name(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action
    response = logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": ""})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    session.refresh(device)
    assert device.custom_name is None
    assert device.display_name == "Mass Storage"


def test_custom_name_persists_after_revoke_and_reauthorize(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action
    logged_in_client.post(f"/whitelist/revoke/{device.id}")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    session.refresh(device)
    assert device.display_name == "Backup SSD"


def test_rename_is_a_no_op_for_a_device_not_yet_whitelisted(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    # Action
    response = logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    session.refresh(device)
    assert device.custom_name is None


def test_dashboard_renders_the_custom_name_once_set(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    DeviceEventFactory(device=device)
    # Action
    response = logged_in_client.get("/")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Backup SSD" in response.text
    assert "Mass Storage" not in response.text


def test_devices_page_renders_the_custom_name_once_set(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action
    response = logged_in_client.get("/dispositivos")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Backup SSD" in response.text

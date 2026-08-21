from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus import profiles
from argus.factories import DeviceFactory
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.web import i18n


def test_authorize_records_whitelist_authorize_action(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    # Action
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    action = session.query(AdminAction).one()
    assert action.actor == "admin"
    assert action.action_type == AdminActionType.WHITELIST_AUTHORIZE
    assert device.vid_pid in action.target
    assert "Mass Storage" in action.target


def test_revoke_records_whitelist_revoke_action_that_survives_entry_deletion(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    logged_in_client.post(f"/whitelist/revoke/{device.id}")
    # Expected
    revoke_action = session.query(AdminAction).filter_by(action_type=AdminActionType.WHITELIST_REVOKE).one()
    assert revoke_action.actor == "admin"
    assert "Mass Storage" in revoke_action.target
    assert device.whitelist_entry is None


def test_rename_records_device_rename_action_with_before_and_after(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.DEVICE_RENAME).one()
    assert "Mass Storage" in action.target
    assert "Backup SSD" in action.target


def test_renaming_to_the_same_name_records_nothing(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action — renaming to the exact same value again
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.DEVICE_RENAME).count() == 1


def test_profile_switch_records_profile_switch_action(logged_in_client, session):
    # Action
    logged_in_client.post("/ajustes", data={"profile": "enforce", "language": "en", "theme": "dark", "font_size": "md"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.PROFILE_SWITCH).one()
    assert action.target == "monitor -> enforce"


def test_ajustes_save_without_profile_change_records_nothing(logged_in_client, session):
    # Action — only theme changes, profile stays at its default (monitor)
    logged_in_client.post("/ajustes", data={"profile": "monitor", "language": "en", "theme": "light", "font_size": "md"})
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.PROFILE_SWITCH).count() == 0


def test_logs_page_shows_recorded_admin_actions(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert i18n.TRANSLATIONS["en"]["action_type_whitelist_authorize"] in response.text
    assert "Mass Storage" in response.text


def test_prune_deletes_old_admin_actions_when_retention_configured(session, monkeypatch):
    # Setup
    monkeypatch.setenv("ARGUS_LOG_RETENTION_DAYS", "30")
    session.add(
        AdminAction(
            actor="admin",
            action_type=AdminActionType.WHITELIST_AUTHORIZE,
            target="old",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(AdminAction).count() == 0


def test_prune_keeps_admin_actions_when_retention_unset(session, monkeypatch):
    # Setup
    monkeypatch.delenv("ARGUS_LOG_RETENTION_DAYS", raising=False)
    session.add(
        AdminAction(
            actor="admin",
            action_type=AdminActionType.WHITELIST_AUTHORIZE,
            target="old",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=9999),
        )
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(AdminAction).count() == 1

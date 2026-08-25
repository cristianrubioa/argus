from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import status

from argus import profiles
from argus.factories import DeviceFactory
from argus.models import AdminAction
from argus.models import AdminActionType
from argus.models import LogRetention
from argus.web import i18n

_BASE_SETTINGS_FORM = {
    "profile": "monitor",
    "language": "en",
    "theme": "dark",
    "font_size": "md",
    "log_retention": "1_year",
    "mqtt_port": "1883",
}


def test_authorize_records_whitelist_authorize_action(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    # Action
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Expected
    action = session.query(AdminAction).one()
    assert (action.actor, action.action_type, action.vid_pid, action.serial, action.source, action.target) == (
        "admin",
        AdminActionType.WHITELIST_AUTHORIZE,
        device.vid_pid,
        device.serial,
        None,
        "Mass Storage",
    )


def test_revoke_records_whitelist_revoke_action_that_survives_entry_deletion(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    logged_in_client.post(f"/whitelist/revoke/{device.id}")
    # Expected
    revoke_action = session.query(AdminAction).filter_by(action_type=AdminActionType.WHITELIST_REVOKE).one()
    assert (revoke_action.actor, revoke_action.vid_pid, revoke_action.serial, revoke_action.target) == (
        "admin",
        device.vid_pid,
        device.serial,
        "Mass Storage",
    )
    assert device.whitelist_entry is None


def test_rename_records_device_rename_action_with_before_and_after(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.DEVICE_RENAME).one()
    assert (action.vid_pid, action.serial, action.source, action.target) == (
        device.vid_pid,
        device.serial,
        "Mass Storage",
        "Backup SSD",
    )


def test_renaming_to_the_same_name_records_nothing(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.DEVICE_RENAME).count() == 1


def test_profile_switch_records_profile_switch_action(logged_in_client, session):
    # Action
    logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "profile": "enforce"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.PROFILE_SWITCH).one()
    assert (action.vid_pid, action.source, action.target) == (None, "monitor", "enforce")


def test_settings_save_without_profile_change_records_nothing(logged_in_client, session):
    # Action
    logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "theme": "light"})
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.PROFILE_SWITCH).count() == 0


def test_retention_change_records_retention_change_action(logged_in_client, session):
    # Action
    logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "log_retention": "90_days"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.RETENTION_CHANGE).one()
    assert (action.vid_pid, action.source, action.target) == (None, "1_year", "90_days")
    assert profiles.get_log_retention(session) == LogRetention.NINETY_DAYS


def test_settings_save_without_retention_change_records_nothing(logged_in_client, session):
    # Action
    logged_in_client.post("/settings", data={**_BASE_SETTINGS_FORM, "theme": "light"})
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.RETENTION_CHANGE).count() == 0


def test_logs_page_renders_both_tab_panels_since_visibility_is_toggled_client_side(logged_in_client, session):
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="events-panel"' in response.text
    assert 'id="actions-panel" class="hidden"' in response.text
    assert 'id="tab-events-btn"' in response.text
    assert 'id="tab-actions-btn"' in response.text


def test_logs_page_reopens_on_the_admin_actions_tab_when_requested(logged_in_client, session):
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="events-panel" class="hidden"' in response.text
    assert 'id="actions-panel" class=""' in response.text


def test_logs_page_ignores_an_invalid_tab_value(logged_in_client, session):
    # Action
    response = logged_in_client.get("/logs", params={"tab": "nonsense"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert 'id="events-panel" class=""' in response.text
    assert 'id="actions-panel" class="hidden"' in response.text


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


def test_logs_page_shows_source_and_vid_pid_columns_for_rename(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action
    response = logged_in_client.get("/logs")
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert device.vid_pid in response.text
    assert "Mass Storage" in response.text
    assert "Backup SSD" in response.text


def test_admin_actions_filter_narrows_by_action_type(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions", "a_action": "whitelist_authorize"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Mass Storage" in response.text
    assert "Backup SSD" not in response.text


def test_admin_actions_search_matches_serial(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage", serial="UNIQUESERIAL1")
    other = DeviceFactory(name="Other Device", serial="DIFFERENT2")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    logged_in_client.post(f"/whitelist/authorize/{other.id}")
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions", "a_q": "UNIQUESERIAL1"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Mass Storage" in response.text
    assert "Other Device" not in response.text


def test_admin_actions_date_range_excludes_actions_outside_it(logged_in_client, session):
    # Setup
    session.add(
        AdminAction(
            actor="admin",
            action_type=AdminActionType.WHITELIST_AUTHORIZE,
            target="Old Device",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
    )
    session.commit()
    device = DeviceFactory(name="Recent Device")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions"})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Old Device" not in response.text
    assert "Recent Device" in response.text


def test_admin_actions_sort_by_occurred_at_ascending_orders_oldest_first(logged_in_client, session):
    # Setup
    older = DeviceFactory(name="Older Device")
    logged_in_client.post(f"/whitelist/authorize/{older.id}")
    newer = DeviceFactory(name="Newer Device")
    logged_in_client.post(f"/whitelist/authorize/{newer.id}")
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions", "a_sort": "occurred_at", "a_dir": "asc"})
    # Expected
    assert response.text.index("Older Device") < response.text.index("Newer Device")


def test_admin_actions_pagination_moves_to_the_next_page(logged_in_client, session):
    # Setup
    for i in range(21):
        session.add(
            AdminAction(
                actor="admin",
                action_type=AdminActionType.WHITELIST_AUTHORIZE,
                target=f"Device {i}",
                occurred_at=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
        )
    session.commit()
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions", "a_page": 2})
    # Expected
    assert response.status_code == status.HTTP_200_OK
    assert "Device 20" in response.text
    assert "Device 0" not in response.text


def test_prune_deletes_old_admin_actions_when_retention_configured(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.NINETY_DAYS)
    session.add(
        AdminAction(
            actor="admin",
            action_type=AdminActionType.WHITELIST_AUTHORIZE,
            target="old",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=91),
        )
    )
    session.commit()
    # Action
    profiles.prune_old_events(session)
    # Expected
    assert session.query(AdminAction).count() == 0


def test_prune_keeps_admin_actions_when_retention_is_forever(session):
    # Setup
    profiles.set_log_retention(session, LogRetention.FOREVER)
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

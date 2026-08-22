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
    assert action.vid_pid == device.vid_pid
    assert action.serial == device.serial
    assert action.source is None
    assert action.target == "Mass Storage"


def test_revoke_records_whitelist_revoke_action_that_survives_entry_deletion(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    logged_in_client.post(f"/whitelist/revoke/{device.id}")
    # Expected
    revoke_action = session.query(AdminAction).filter_by(action_type=AdminActionType.WHITELIST_REVOKE).one()
    assert revoke_action.actor == "admin"
    assert revoke_action.vid_pid == device.vid_pid
    assert revoke_action.serial == device.serial
    assert revoke_action.target == "Mass Storage"
    assert device.whitelist_entry is None


def test_rename_records_device_rename_action_with_before_and_after(logged_in_client, session):
    # Setup
    device = DeviceFactory(name="Mass Storage")
    logged_in_client.post(f"/whitelist/authorize/{device.id}")
    # Action
    logged_in_client.post(f"/whitelist/rename/{device.id}", data={"custom_name": "Backup SSD"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.DEVICE_RENAME).one()
    assert action.vid_pid == device.vid_pid
    assert action.serial == device.serial
    assert action.source == "Mass Storage"
    assert action.target == "Backup SSD"


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
    logged_in_client.post("/settings", data={"profile": "enforce", "language": "en", "theme": "dark", "font_size": "md"})
    # Expected
    action = session.query(AdminAction).filter_by(action_type=AdminActionType.PROFILE_SWITCH).one()
    assert action.vid_pid is None
    assert action.source == "monitor"
    assert action.target == "enforce"


def test_settings_save_without_profile_change_records_nothing(logged_in_client, session):
    # Action — only theme changes, profile stays at its default (monitor)
    logged_in_client.post("/settings", data={"profile": "monitor", "language": "en", "theme": "light", "font_size": "md"})
    # Expected
    assert session.query(AdminAction).filter_by(action_type=AdminActionType.PROFILE_SWITCH).count() == 0


def test_logs_page_renders_both_tab_panels(logged_in_client, session):
    # Action
    response = logged_in_client.get("/logs")
    # Expected — both panels are in the DOM (client-side JS toggles visibility, not the server)
    assert response.status_code == status.HTTP_200_OK
    assert 'id="events-panel"' in response.text
    assert 'id="actions-panel" class="hidden"' in response.text
    assert 'id="tab-events-btn"' in response.text
    assert 'id="tab-actions-btn"' in response.text


def test_logs_page_reopens_on_the_admin_actions_tab_when_requested(logged_in_client, session):
    # Action
    response = logged_in_client.get("/logs", params={"tab": "actions"})
    # Expected — events panel is hidden, actions panel is visible, on a fresh page load (not a JS toggle)
    assert response.status_code == status.HTTP_200_OK
    assert 'id="events-panel" class="hidden"' in response.text
    assert 'id="actions-panel" class=""' in response.text


def test_logs_page_ignores_an_invalid_tab_value(logged_in_client, session):
    # Action
    response = logged_in_client.get("/logs", params={"tab": "nonsense"})
    # Expected — falls back to the events tab
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
    # Action — the rename target ("Backup SSD") only ever appears in the rename row, never
    # in the filter panel's static labels, so its absence proves the row itself was filtered out
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
    # Setup — one action outside the default 7-day range, one inside it
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
    # Setup — one more row than fits on a single page
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

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from argus.agent.main import handle_event
from argus.models import Decision
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import WhitelistEntry

# Captured verbatim from `sudo usbguard watch -w` on a real Ubuntu Noble host.
_INSERT_BLOCKED_WITH_SERIAL = (
    "[device] PresenceChanged: id=20\n"
    " event=Insert\n"
    " target=block\n"
    ' device_rule=block id 058f:6387 serial "AAE9055C" name "Mass Storage" '
    'hash "nenPRn0Y6FeYFUGzorTU6vCVd8iLMlDs2nQfDtRiNwI=" '
    'parent-hash "jEP/6WzviqdJ5VSeTUY8PatCNBKeaREvo2OqdplND/o=" '
    'via-port "3-5" with-interface 08:06:50 with-connect-type "hotplug"'
)

_INSERT_BLOCKED_NO_SERIAL = (
    "[device] PresenceChanged: id=21\n"
    " event=Insert\n"
    " target=block\n"
    ' device_rule=block id 046d:c542 serial "" name "Wireless Receiver" '
    'hash "RE4eSWo4C6sJnh9noxTYUChFLUFP68OpRaakLzFKohg=" '
    'parent-hash "jEP/6WzviqdJ5VSeTUY8PatCNBKeaREvo2OqdplND/o=" '
    'via-port "3-5" with-interface 03:01:02 with-connect-type "hotplug"'
)

_INSERT_ALLOWED = (
    "[device] PresenceChanged: id=22\n"
    " event=Insert\n"
    " target=allow\n"
    ' device_rule=allow id 1d6b:0002 serial "0000:00:0d.0" name "xHCI Host Controller" '
    'hash "d3YN7OD60Ggqc9hClW0/al6tlFEshidDnQKzZRRk410=" '
    'parent-hash "Y1kBdG1uWQr5CjULQs7uh2F6pHgFb6VDHcWLk83v+tE=" '
    'with-interface 09:00:00 with-connect-type ""'
)

_REMOVE = (
    "[device] PresenceChanged: id=19\n"
    " event=Remove\n"
    " target=allow\n"
    ' device_rule=allow id 058f:6387 serial "AAE9055C" name "Mass Storage"'
)

_POLICY_CHANGED = (
    "[device] PolicyChanged: id=20\n"
    " target_old=block\n"
    " target_new=allow\n"
    ' device_rule=allow id 058f:6387 serial "AAE9055C" name "Mass Storage"\n'
    " rule_id=4294967294"
)

# Captured verbatim right after the matching Insert above — USBGuard's own decision settling.
_POLICY_APPLIED_SETTLED_ALLOW = (
    "[device] PolicyApplied: id=20\n"
    " target_new=allow\n"
    ' device_rule=allow id 058f:6387 serial "AAE9055C" name "Mass Storage"\n'
    " rule_id=4294967294"
)

_POLICY_APPLIED_SETTLED_BLOCK = (
    "[device] PolicyApplied: id=20\n"
    " target_new=block\n"
    ' device_rule=block id 058f:6387 serial "AAE9055C" name "Mass Storage"\n'
    " rule_id=4294967294"
)

_POLICY_APPLIED_NO_SERIAL_ALLOW = (
    "[device] PolicyApplied: id=21\n"
    " target_new=allow\n"
    ' device_rule=allow id 046d:c542 serial "" name "Wireless Receiver"\n'
    " rule_id=4294967294"
)

# A different connection id than any Insert fixture above — no event should ever match it.
_POLICY_APPLIED_UNKNOWN_CONNECTION = (
    "[device] PolicyApplied: id=999\n"
    " target_new=allow\n"
    ' device_rule=allow id 058f:6387 serial "AAE9055C" name "Mass Storage"\n'
    " rule_id=4294967294"
)


def test_event_recorded_with_full_device_attributes(session):
    # Action
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    # Expected
    device = session.query(Device).one()
    assert device.vid_pid == "058f:6387"
    assert device.serial == "AAE9055C"
    assert device.name == "Mass Storage"
    assert device.connect_type == "hotplug"
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.BLOCKED


def test_hardwired_device_connect_type_is_persisted(session):
    # Action
    handle_event(session, _INSERT_ALLOWED)
    # Expected
    device = session.query(Device).one()
    assert device.connect_type == ""


def test_rapid_duplicate_inserts_recorded_once(session):
    # Action
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    # Expected
    assert session.query(Device).count() == 1
    assert session.query(DeviceEvent).count() == 1


def test_event_recorded_for_device_without_serial(session):
    # Action
    handle_event(session, _INSERT_BLOCKED_NO_SERIAL)
    # Expected
    device = session.query(Device).one()
    assert device.serial is None
    assert session.query(DeviceEvent).count() == 1


def test_unrecognized_device_not_blocked_by_usbguard(session):
    # Action
    handle_event(session, _INSERT_ALLOWED)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.UNRECOGNIZED


def test_remove_event_is_ignored(session):
    # Action
    handle_event(session, _REMOVE)
    # Expected
    assert session.query(Device).count() == 0
    assert session.query(DeviceEvent).count() == 0


def test_policy_changed_alone_corrects_provisional_block_to_unrecognized(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    # Action
    handle_event(session, _POLICY_CHANGED)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.UNRECOGNIZED


def test_ipc_status_line_is_ignored(session):
    # Action
    handle_event(session, "[IPC] Connected")
    # Expected
    assert session.query(Device).count() == 0
    assert session.query(DeviceEvent).count() == 0


def test_policy_applied_corrects_provisional_block_to_unrecognized(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    # Action
    handle_event(session, _POLICY_APPLIED_SETTLED_ALLOW)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.UNRECOGNIZED


def test_policy_applied_matching_the_recorded_decision_is_a_no_op(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    # Action
    handle_event(session, _POLICY_APPLIED_SETTLED_BLOCK)
    # Expected
    assert session.query(DeviceEvent).count() == 1
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.BLOCKED


def test_first_settle_reaches_authorized_when_device_is_whitelisted(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_NO_SERIAL)
    device = session.query(Device).one()
    session.add(WhitelistEntry(device_id=device.id, added_by="admin"))
    session.commit()
    # Action
    handle_event(session, _POLICY_APPLIED_NO_SERIAL_ALLOW)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.AUTHORIZED
    assert event.settled_at is not None


def test_handle_policy_settled_never_touches_an_already_settled_event(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    handle_event(session, _POLICY_APPLIED_SETTLED_BLOCK)
    device = session.query(Device).one()
    session.add(WhitelistEntry(device_id=device.id, added_by="admin"))
    session.commit()
    # Action
    handle_event(session, _POLICY_APPLIED_SETTLED_ALLOW)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.BLOCKED
    assert event.usbguard_connection_id == 20


def test_policy_applied_with_unknown_connection_id_is_a_no_op(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    # Action
    handle_event(session, _POLICY_APPLIED_UNKNOWN_CONNECTION)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.BLOCKED


def test_policy_applied_with_no_events_recorded_yet_is_a_no_op(session):
    # Action
    handle_event(session, _POLICY_APPLIED_SETTLED_ALLOW)
    # Expected
    assert session.query(Device).count() == 0
    assert session.query(DeviceEvent).count() == 0


def test_policy_applied_applies_even_after_a_long_delay(session):
    # Setup
    handle_event(session, _INSERT_BLOCKED_WITH_SERIAL)
    event = session.query(DeviceEvent).one()
    event.occurred_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.commit()
    # Action
    handle_event(session, _POLICY_APPLIED_SETTLED_ALLOW)
    # Expected
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.UNRECOGNIZED

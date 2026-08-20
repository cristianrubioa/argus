from argus.agent.main import handle_line
from argus.models import Decision
from argus.models import Device
from argus.models import DeviceEvent


def test_event_recorded_with_full_device_attributes(session):
    # Setup
    line = 'DevicePolicyChanged target=allow id 1d6b:0002 name "xHCI Host Controller" serial "0000:00:0d.0"'
    # Action
    handle_line(session, line)
    # Expected
    device = session.query(Device).one()
    assert device.vid_pid == "1d6b:0002"
    assert device.serial == "0000:00:0d.0"
    event = session.query(DeviceEvent).one()
    assert event.decision == Decision.UNRECOGNIZED


def test_event_recorded_for_device_without_serial(session):
    # Setup
    line = 'DevicePolicyChanged target=allow id 046d:c52b name "USB Receiver"'
    # Action
    handle_line(session, line)
    # Expected
    device = session.query(Device).one()
    assert device.serial is None
    assert session.query(DeviceEvent).count() == 1


def test_non_device_line_is_ignored(session):
    # Action
    handle_line(session, "Waiting for IPC connection")
    # Expected
    assert session.query(Device).count() == 0
    assert session.query(DeviceEvent).count() == 0

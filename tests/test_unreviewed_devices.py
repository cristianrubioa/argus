from argus import profiles
from argus.agent import usbguard_cli
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory


def test_hardwired_device_is_excluded(session):
    # Setup
    device = DeviceFactory(connect_type="")
    DeviceEventFactory(device=device)
    # Action
    devices = profiles.unreviewed_devices(session)
    # Expected
    assert devices == []


def test_hotplug_device_is_included(session):
    # Setup
    device = DeviceFactory(connect_type="hotplug")
    DeviceEventFactory(device=device)
    # Action
    devices = profiles.unreviewed_devices(session)
    # Expected
    assert devices == [device]


def test_unknown_connect_type_excluded_when_not_currently_connected(session, monkeypatch):
    # Setup
    device = DeviceFactory(connect_type=None)
    DeviceEventFactory(device=device)
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [])
    # Action
    devices = profiles.unreviewed_devices(session)
    # Expected
    assert devices == []


def test_unknown_connect_type_included_when_live_lookup_resolves_hotplug(session, monkeypatch):
    # Setup
    device = DeviceFactory(connect_type=None)
    DeviceEventFactory(device=device)
    listed = usbguard_cli.ListedDevice(vid=device.vid, pid=device.pid, serial=device.serial, target="allow", hotplug=True)
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [listed])
    # Action
    devices = profiles.unreviewed_devices(session)
    # Expected
    assert devices == [device]


def test_unknown_connect_type_excluded_when_live_lookup_resolves_hardwired(session, monkeypatch):
    # Setup
    device = DeviceFactory(connect_type=None)
    DeviceEventFactory(device=device)
    listed = usbguard_cli.ListedDevice(vid=device.vid, pid=device.pid, serial=device.serial, target="allow", hotplug=False)
    monkeypatch.setattr(usbguard_cli, "list_devices", lambda: [listed])
    # Action
    devices = profiles.unreviewed_devices(session)
    # Expected
    assert devices == []

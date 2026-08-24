import factory

from argus.models import AdminUser
from argus.models import Decision
from argus.models import Device
from argus.models import DeviceEvent
from argus.models import Profile
from argus.models import WhitelistEntry


class DeviceFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Device
        sqlalchemy_session_persistence = "commit"

    vid = factory.Sequence(lambda n: f"{n % 0xFFFF:04x}")
    pid = factory.Sequence(lambda n: f"{(n * 7) % 0xFFFF:04x}")
    name = factory.Sequence(lambda n: f"Test Device {n}")
    serial = factory.Sequence(lambda n: f"SN{n}")
    connect_type = "hotplug"


class DeviceEventFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = DeviceEvent
        sqlalchemy_session_persistence = "commit"

    device = factory.SubFactory(DeviceFactory)
    decision = Decision.AUTHORIZED
    profile = Profile.MONITOR


class WhitelistEntryFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = WhitelistEntry
        sqlalchemy_session_persistence = "commit"

    device = factory.SubFactory(DeviceFactory)
    added_by = "test-admin"


class AdminUserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = AdminUser
        sqlalchemy_session_persistence = "commit"

    username = factory.Sequence(lambda n: f"admin{n}")
    password_hash = "unused-in-factory-default"

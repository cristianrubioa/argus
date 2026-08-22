import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from argus.db import Base
from argus.db import get_session
from argus.factories import AdminUserFactory
from argus.factories import DeviceEventFactory
from argus.factories import DeviceFactory
from argus.factories import WhitelistEntryFactory
from argus.models import AdminUser
from argus.web import auth
from argus.web.auth import hash_password
from argus.web.main import app

_FACTORIES = (DeviceFactory, DeviceEventFactory, WhitelistEntryFactory, AdminUserFactory)


@pytest.fixture(autouse=True)
def _reset_login_attempts():
    auth._reset_login_attempts()
    yield
    auth._reset_login_attempts()


@pytest.fixture(autouse=True)
def _reset_admin_exists_cache():
    auth._reset_admin_exists_cache()
    yield
    auth._reset_admin_exists_cache()


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db_session = sessionmaker(bind=engine)()

    for factory in _FACTORIES:
        factory._meta.sqlalchemy_session = db_session
        factory._meta.sqlalchemy_session_persistence = "commit"

    yield db_session
    db_session.close()


@pytest.fixture()
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def logged_in_client(client, session):
    session.add(AdminUser(username="admin", password_hash=hash_password("secret")))
    session.commit()
    client.post("/login", data={"username": "admin", "password": "secret"})
    return client

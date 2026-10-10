import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from argus import db
from argus import version_check
from argus.db import Base
from argus.db import init_db
from argus.models import Decision
from argus.models import Profile


def _engine_missing_settled_at():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE device_events DROP COLUMN settled_at"))
        conn.execute(
            text(
                "INSERT INTO devices (vid, pid, name, first_seen_at, last_seen_at) "
                "VALUES ('058f', '6387', 'Mass Storage', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO device_events (device_id, decision, profile, occurred_at) "
                "VALUES (1, :dec, :p, CURRENT_TIMESTAMP)"
            ),
            {"dec": Decision.BLOCKED.value, "p": Profile.ENFORCE.value},
        )
    return engine


def test_settled_at_backfills_pre_existing_rows_on_upgrade():
    # Setup
    engine = _engine_missing_settled_at()
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        row = conn.execute(text("SELECT settled_at FROM device_events")).one()
    assert row.settled_at is not None


def test_settled_at_migration_is_idempotent_and_does_not_clobber_unsettled_rows():
    # Setup
    engine = _engine_missing_settled_at()
    init_db(bind_engine=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_events (device_id, decision, profile, occurred_at, settled_at) "
                "VALUES (1, :dec, :p, CURRENT_TIMESTAMP, NULL)"
            ),
            {"dec": Decision.BLOCKED.value, "p": Profile.ENFORCE.value},
        )
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        row = conn.execute(text("SELECT settled_at FROM device_events WHERE id = 2")).one()
    assert row.settled_at is None


def test_add_missing_columns_reraises_an_unrelated_operational_error():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE admin_actions"))
    # Action & Expected
    with pytest.raises(OperationalError, match="no such table"):
        db._add_missing_columns(engine)


def test_add_device_events_settled_at_reraises_an_unrelated_operational_error():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE device_events"))
    # Action & Expected
    with pytest.raises(OperationalError, match="no such table"):
        db._add_device_events_settled_at(engine)


def test_log_retention_column_backfills_to_one_year_on_upgrade():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE settings DROP COLUMN log_retention"))
        conn.execute(
            text(
                "INSERT INTO settings (id, profile, language, theme, font_size, mqtt_enabled, mqtt_port, "
                "mqtt_topic_prefix, mqtt_tls_enabled) VALUES (1, :p, 'en', 'dark', 'md', 0, 1883, 'argus', 0)"
            ),
            {"p": Profile.MONITOR.value},
        )
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        row = conn.execute(text("SELECT log_retention FROM settings WHERE id = 1")).one()
    assert row.log_retention == "ONE_YEAR"


def _engine_missing_mqtt_columns():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_enabled"))
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_host"))
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_port"))
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_topic_prefix"))
        conn.execute(
            text(
                "INSERT INTO settings (id, profile, language, theme, font_size, log_retention, mqtt_tls_enabled) "
                "VALUES (1, :p, 'en', 'dark', 'md', 'ONE_YEAR', 0)"
            ),
            {"p": Profile.MONITOR.value},
        )
    return engine


def test_mqtt_columns_backfill_to_disabled_defaults_on_upgrade():
    # Setup
    engine = _engine_missing_mqtt_columns()
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        query = "SELECT mqtt_enabled, mqtt_host, mqtt_port, mqtt_topic_prefix FROM settings WHERE id = 1"
        row = conn.execute(text(query)).one()
    assert (row.mqtt_enabled, row.mqtt_host, row.mqtt_port, row.mqtt_topic_prefix) == (0, None, 1883, "argus")


def test_mqtt_columns_migration_is_idempotent():
    # Setup
    engine = _engine_missing_mqtt_columns()
    init_db(bind_engine=engine)
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)"))}
    assert {"mqtt_enabled", "mqtt_host", "mqtt_port", "mqtt_topic_prefix"} <= columns


def _engine_missing_mqtt_tls_auth_columns():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_username"))
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_password"))
        conn.execute(text("ALTER TABLE settings DROP COLUMN mqtt_tls_enabled"))
        conn.execute(
            text(
                "INSERT INTO settings (id, profile, language, theme, font_size, log_retention, mqtt_enabled, "
                "mqtt_port, mqtt_topic_prefix) VALUES (1, :p, 'en', 'dark', 'md', 'ONE_YEAR', 0, 1883, 'argus')"
            ),
            {"p": Profile.MONITOR.value},
        )
    return engine


def test_mqtt_tls_auth_columns_backfill_to_disabled_defaults_on_upgrade():
    # Setup
    engine = _engine_missing_mqtt_tls_auth_columns()
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        row = conn.execute(text("SELECT mqtt_username, mqtt_password, mqtt_tls_enabled FROM settings WHERE id = 1")).one()
    assert (row.mqtt_username, row.mqtt_password, row.mqtt_tls_enabled) == (None, None, 0)


def test_mqtt_tls_auth_columns_migration_is_idempotent():
    # Setup
    engine = _engine_missing_mqtt_tls_auth_columns()
    init_db(bind_engine=engine)
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)"))}
    assert {"mqtt_username", "mqtt_password", "mqtt_tls_enabled"} <= columns


def test_log_retention_migration_is_idempotent():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    init_db(bind_engine=engine)
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)"))}
    assert "log_retention" in columns


def test_release_notes_seen_version_backfills_to_installed_version_on_upgrade():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE settings DROP COLUMN release_notes_seen_version"))
        conn.execute(
            text(
                "INSERT INTO settings (id, profile, language, theme, font_size, log_retention, mqtt_enabled, "
                "mqtt_port, mqtt_topic_prefix, mqtt_tls_enabled) "
                "VALUES (1, :p, 'en', 'dark', 'md', 'ONE_YEAR', 0, 1883, 'argus', 0)"
            ),
            {"p": Profile.MONITOR.value},
        )
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        row = conn.execute(text("SELECT release_notes_seen_version FROM settings WHERE id = 1")).one()
    assert row.release_notes_seen_version == version_check.installed_version()


def test_release_notes_seen_version_migration_is_idempotent():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    init_db(bind_engine=engine)
    # Action
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)"))}
    assert "release_notes_seen_version" in columns


def test_add_release_notes_seen_version_reraises_an_unrelated_operational_error():
    # Setup
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE settings"))
    # Action & Expected
    with pytest.raises(OperationalError, match="no such table"):
        db._add_release_notes_seen_version(engine)

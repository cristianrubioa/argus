from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker

from argus import config


class Base(DeclarativeBase):
    pass


def make_engine(db_path=None):
    path = db_path if db_path is not None else config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _set_wal_mode(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine)


def init_db(bind_engine=None):
    target = bind_engine or engine
    Base.metadata.create_all(bind=target)
    _add_missing_columns(target)
    _add_device_events_settled_at(target)


_SETTINGS_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA = (
    "ALTER TABLE settings ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE settings ADD COLUMN mqtt_last_publish_at DATETIME",
    "ALTER TABLE settings ADD COLUMN mqtt_last_publish_ok BOOLEAN",
    "ALTER TABLE settings ADD COLUMN mqtt_last_error VARCHAR(255)",
    "ALTER TABLE settings ADD COLUMN theme TEXT DEFAULT 'dark'",
    "ALTER TABLE settings ADD COLUMN font_size TEXT DEFAULT 'md'",
    "ALTER TABLE settings ADD COLUMN agent_last_heartbeat_at DATETIME",
    "ALTER TABLE settings ADD COLUMN last_log_prune_at DATETIME",
    "ALTER TABLE settings ADD COLUMN latest_version_available VARCHAR(32)",
    "ALTER TABLE settings ADD COLUMN version_checked_at DATETIME",
)

_DEVICES_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA = ("ALTER TABLE devices ADD COLUMN custom_name VARCHAR(255)",)

_DEVICE_EVENTS_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA = ("ALTER TABLE device_events ADD COLUMN usbguard_connection_id INTEGER",)

_ADMIN_ACTIONS_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA = (
    "ALTER TABLE admin_actions ADD COLUMN vid_pid VARCHAR(9)",
    "ALTER TABLE admin_actions ADD COLUMN source VARCHAR(255)",
    "ALTER TABLE admin_actions ADD COLUMN serial VARCHAR(255)",
)


def _add_missing_columns(target):
    """Guard for schema changes on a pre-existing database — no migration tool yet (add-ui-localization/design.md)."""
    statements = (
        _SETTINGS_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA
        + _DEVICES_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA
        + _ADMIN_ACTIONS_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA
        + _DEVICE_EVENTS_COLUMNS_ADDED_AFTER_INITIAL_SCHEMA
    )
    for statement in statements:
        try:
            with target.begin() as conn:
                conn.execute(text(statement))
        except OperationalError:
            pass


def _add_device_events_settled_at(target):
    """settled_at can't get a same-statement backfill via ALTER TABLE ... DEFAULT CURRENT_TIMESTAMP —
    SQLite rejects a non-constant default on ADD COLUMN ("Cannot add a column with non-constant
    default"). So this adds the column and backfills every pre-existing row as already-settled (never
    eligible for the one-time provisional correction again) in one gated step: if the ALTER fails
    because the column already exists, the whole transaction rolls back and the backfill never runs
    again — new rows keep settled_at NULL until they actually settle."""
    try:
        with target.begin() as conn:
            conn.execute(text("ALTER TABLE device_events ADD COLUMN settled_at DATETIME"))
            conn.execute(text("UPDATE device_events SET settled_at = CURRENT_TIMESTAMP"))
    except OperationalError:
        pass


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

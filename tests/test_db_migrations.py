from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from argus.db import Base
from argus.db import init_db
from argus.models import Decision
from argus.models import Profile


def _engine_missing_settled_at():
    """A DB shaped like one that existed before settled_at was added to the model, with one pre-existing event."""
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
    # Action — a second init_db must not raise, and must leave the freshly-inserted unsettled row alone
    init_db(bind_engine=engine)
    # Expected
    with engine.connect() as conn:
        row = conn.execute(text("SELECT settled_at FROM device_events WHERE id = 2")).one()
    assert row.settled_at is None

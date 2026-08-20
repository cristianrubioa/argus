from sqlalchemy import create_engine
from sqlalchemy import event
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
    Base.metadata.create_all(bind=bind_engine or engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from argus import config
from argus.db import SessionLocal
from argus.db import init_db
from argus.web.auth import ensure_admin_seeded
from argus.web.router import router


@asynccontextmanager
async def _lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as session:
        ensure_admin_seeded(session)
    yield


app = FastAPI(title="Argus", lifespan=_lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.session_secret(), https_only=config.session_https_only())
app.include_router(router)

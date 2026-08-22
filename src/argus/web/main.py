import argparse
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from argus import config
from argus.db import init_db
from argus.web.auth import require_registered
from argus.web.router import register_router
from argus.web.router import router

_DEFAULT_PORT = 8420


@asynccontextmanager
async def _lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Argus", lifespan=_lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.session_secret(), https_only=config.session_https_only())
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(register_router)
app.include_router(router, dependencies=[Depends(require_registered)])


def _resolve_port() -> int:
    parser = argparse.ArgumentParser(prog="argus-web")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    if args.port is not None:
        return args.port
    return int(os.environ.get("ARGUS_WEB_PORT", _DEFAULT_PORT))


def main() -> None:
    port = _resolve_port()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("0.0.0.0", port))
    except OSError:
        sys.exit(f"Port {port} is already in use. Pick another with --port or ARGUS_WEB_PORT.")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

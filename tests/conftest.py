"""Shared pytest fixtures.

The async SQLAlchemy engine is a module-level singleton in `jobforge.db.session`.
Under pytest-asyncio each test gets its own event loop, so an engine created in
one test cannot be reused in another (asyncpg connections bind to the loop).
We reset the singleton between tests to keep things isolated.
"""
from __future__ import annotations

import pytest

from jobforge.db import session as db_session


@pytest.fixture(autouse=True)
def _reset_db_engine_singleton() -> None:
    db_session._engine = None
    db_session._sessionmaker = None
    yield
    db_session._engine = None
    db_session._sessionmaker = None

"""
Persistence layer for fantasy data.
No business logic, no simulation — only read/write interfaces.
"""
from .db import get_connection, init_db
from .repositories import (
    UserRepository,
    TeamRepository,
    MatchRepository,
)

__all__ = [
    "get_connection",
    "init_db",
    "UserRepository",
    "TeamRepository",
    "MatchRepository",
]

"""Shared declarative base for PostgreSQL models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class whose metadata is consumed by Alembic migrations."""

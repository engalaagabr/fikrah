"""Exercise Alembic's real connection setup with a percent-encoded URL."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def test_alembic_preserves_encoded_connection_options(postgres_engine):
    # The disposable schema's options=-csearch_path=... contains an encoded '='.
    assert "%" in postgres_engine.url.render_as_string(hide_password=False)
    command.upgrade(Config("alembic.ini"), "20261121_02")
    assert "projects" in inspect(postgres_engine).get_table_names()

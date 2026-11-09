"""FIKRAH Backend application package."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_local_environment(env_file: Path = PROJECT_ROOT / ".env") -> None:
    """Load local settings without overriding variables supplied by the host."""
    load_dotenv(env_file, override=False)


load_local_environment()

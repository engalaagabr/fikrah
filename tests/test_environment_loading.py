from pathlib import Path
import os

from app import load_local_environment


def test_local_environment_file_loads_without_overriding_host_values(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FIKRAH_ENV_TEST_EXISTING=from-file\nFIKRAH_ENV_TEST_NEW=loaded\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FIKRAH_ENV_TEST_EXISTING", "from-host")
    monkeypatch.delenv("FIKRAH_ENV_TEST_NEW", raising=False)

    load_local_environment(env_file)

    assert os.environ["FIKRAH_ENV_TEST_EXISTING"] == "from-host"
    assert os.environ["FIKRAH_ENV_TEST_NEW"] == "loaded"

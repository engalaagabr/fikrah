"""Validate local SMTP routing using Compose's own configuration renderer."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI required")
@pytest.mark.parametrize("service", ["api", "worker"])
def test_local_email_senders_share_mailpit(tmp_path: Path, service: str) -> None:
    compose = Path(__file__).resolve().parents[1] / "compose.yaml"
    env_file = tmp_path / ".env"
    env_file.write_text("SMTP_HOST=external.invalid\nSMTP_PORT=465\n")
    result = subprocess.run(
        [
            "docker", "compose",
            "--project-directory", str(tmp_path),
            "--env-file", str(env_file),
            "-f", str(compose),
            "config", "--format", "json", "--no-env-resolution",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    config = json.loads(result.stdout)["services"][service]
    assert {
        key: value
        for key, value in config["environment"].items()
        if key.startswith("SMTP_")
    } == {
        "SMTP_HOST": "mailpit",
        "SMTP_PORT": "1025",
        "SMTP_FROM": "no-reply@fikrah.local",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "SMTP_USE_TLS": "false",
        "SMTP_START_TLS": "false",
    }
    assert config["depends_on"]["mailpit"]["condition"] == "service_healthy"

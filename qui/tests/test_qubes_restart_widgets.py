"""Tests for the script restarting widgets after a package upgrade."""

# pylint: disable=redefined-outer-name

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "qubes-restart-widgets"

SYSTEMCTL = """#!/bin/sh
echo "$*" >> "$SYSTEMCTL_LOG"
case "$*" in
    *"-M 1000@ is-active"*) exit 0 ;;
    *is-active*) exit 3 ;;
    *try-restart*) exit "${TRY_RESTART_RC:-0}" ;;
esac
"""


@pytest.fixture
def run_script(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    systemd_dir = tmp_path / "systemd"
    log = tmp_path / "systemctl.log"
    log.touch()

    def run(loginctl_output="", loginctl_rc=0, systemd=True, env=None):
        (bin_dir / "systemctl").write_text(SYSTEMCTL)
        (bin_dir / "loginctl").write_text(
            f"#!/bin/sh\nprintf '{loginctl_output}'\nexit {loginctl_rc}\n"
        )
        for tool in bin_dir.iterdir():
            tool.chmod(0o755)
        if systemd:
            systemd_dir.mkdir(exist_ok=True)
        script = tmp_path / "qubes-restart-widgets"
        script.write_text(
            SCRIPT.read_text().replace("/run/systemd/system", str(systemd_dir))
        )
        result = subprocess.run(
            ["sh", str(script)],
            env={
                "PATH": f"{bin_dir}:/usr/bin:/bin",
                "SYSTEMCTL_LOG": str(log),
                **(env or {}),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return result, log.read_text().splitlines()

    return run


def test_restart_active_widgets_only(run_script):
    result, calls = run_script("   0 root no active\n 1000 user no active\n")
    assert result.returncode == 0, result.stderr
    assert calls == [
        "--user -M 0@ is-active --quiet qubes-widget@*",
        "--user -M 1000@ is-active --quiet qubes-widget@*",
        "--user -M 1000@ daemon-reload",
        "--user -M 1000@ try-restart qubes-widget@*",
    ]


def test_no_users(run_script):
    result, calls = run_script("")
    assert result.returncode == 0, result.stderr
    assert not calls


def test_no_systemd(run_script):
    result, calls = run_script(" 1000 user\n", systemd=False)
    assert result.returncode == 0, result.stderr
    assert not calls


def test_loginctl_failure(run_script):
    result, calls = run_script(loginctl_rc=1)
    assert result.returncode != 0
    assert not calls


def test_restart_failure(run_script):
    result, _calls = run_script(" 1000 user\n", env={"TRY_RESTART_RC": "1"})
    assert result.returncode != 0

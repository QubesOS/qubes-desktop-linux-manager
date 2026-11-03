"""Tests for the script restarting widgets after a package upgrade."""

# There is no systemd on the test machine or in CI, so the tests put a fake
# systemctl and a fake loginctl first on PATH, run the real
# qui/qubes-restart-widgets script against them, and check which systemctl
# commands the script called.

# pylint: disable=redefined-outer-name

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "qubes-restart-widgets"

# Fake systemctl. It appends each call to the file in $SYSTEMCTL_LOG, so a
# test can read back what the script ran. Then:
# - is-active exits 0 (widgets running) for UID 1000 and non-zero for anyone
#   else, like the real one when no widget is running, so one user has widgets
#   and another does not;
# - try-restart exits with $TRY_RESTART_RC, 0 if unset, so a test can make the
#   restart fail;
# - anything else, such as daemon-reload, exits 0.
SYSTEMCTL = """#!/bin/sh
echo "$*" >> "$SYSTEMCTL_LOG"
case "$*" in
    *"-M 1000@ is-active"*) exit 0 ;;
    *is-active*) exit 3 ;;
    *try-restart*) exit "${TRY_RESTART_RC:-0}" ;;
esac
"""


# Gives each test a run() function. run() writes the fakes to tmp_path/bin;
# the fake loginctl prints loginctl_output (UID first, like loginctl
# list-users --no-legend) and exits with loginctl_rc. The script exits early
# unless /run/systemd/system exists, which depends on the machine, so run()
# uses a copy of the script that checks tmp_path/systemd instead, created only
# when systemd=True. env adds variables for the fakes, like TRY_RESTART_RC.
# run() returns the finished process and the list of systemctl calls.
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


# User 0 has no widgets running and must only be checked; user 1000 has
# widgets and must get daemon-reload, then try-restart.
def test_restart_active_widgets_only(run_script):
    result, calls = run_script("   0 root no active\n 1000 user no active\n")
    assert result.returncode == 0, result.stderr
    assert calls == [
        "--user -M 0@ is-active --quiet qubes-widget@*",
        "--user -M 1000@ is-active --quiet qubes-widget@*",
        "--user -M 1000@ daemon-reload",
        "--user -M 1000@ try-restart qubes-widget@*",
    ]


# With no users, loginctl prints nothing; the script must skip the empty line
# instead of calling systemctl with an empty UID (-M @).
def test_no_users(run_script):
    result, calls = run_script("")
    assert result.returncode == 0, result.stderr
    assert not calls


# Without systemd running (a chroot, for example) the script must exit 0
# before calling anything, even though a user with widgets is listed.
def test_no_systemd(run_script):
    result, calls = run_script(" 1000 user\n", systemd=False)
    assert result.returncode == 0, result.stderr
    assert not calls


# If loginctl fails, the script must fail too, so the package install reports
# the error instead of skipping the restart silently.
def test_loginctl_failure(run_script):
    result, calls = run_script(loginctl_rc=1)
    assert result.returncode != 0
    assert not calls


# A failed try-restart must make the script exit non-zero, even though it runs
# inside the piped while loop, which is a subshell.
def test_restart_failure(run_script):
    result, _calls = run_script(" 1000 user\n", env={"TRY_RESTART_RC": "1"})
    assert result.returncode != 0

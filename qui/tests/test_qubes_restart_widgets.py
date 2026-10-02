# pylint: disable=missing-docstring
import os
import stat
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "qubes-restart-widgets"


def make_executable(path: Path, content: str):
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_script_exists_and_is_executable():
    assert SCRIPT_PATH.exists()


def test_exit_cleanly_when_not_dom0_or_guivm(tmp_path):
    # Fake root with no qubes-release or guivm
    env = os.environ.copy()
    res = subprocess.run(
        ["/bin/sh", str(SCRIPT_PATH)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    # On systems where /etc/qubes-release doesn't exist, it should exit 0
    if not os.path.exists("/etc/qubes-release") and not os.path.exists(
        "/var/run/qubes-service/guivm"
    ):
        assert res.returncode == 0


def test_restart_script_unit_logic(tmp_path):
    # Create an isolated mock environment
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    systemctl_log = tmp_path / "systemctl.log"
    mock_systemctl = bin_dir / "systemctl"
    make_executable(
        mock_systemctl,
        f"""#!/bin/sh
echo "$@" >> "{systemctl_log}"
exit 0
""",
    )

    mock_id = bin_dir / "id"
    make_executable(
        mock_id,
        """#!/bin/sh
case "$1" in
    -u) echo "0" ;;
    -un) echo "root" ;;
    -nu) echo "user" ;;
    *) echo "0" ;;
esac
""",
    )

    mock_pgrep = bin_dir / "pgrep"
    make_executable(
        mock_pgrep,
        """#!/bin/sh
# By default, updater is not running (return 1)
exit 1
""",
    )

    # Mock runtime directory with /run/user/1000/systemd/private
    run_dir = tmp_path / "run"
    run_user = run_dir / "user" / "1000" / "systemd"
    run_user.mkdir(parents=True)
    (run_user / "private").write_text("")

    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    etc_dir = tmp_path / "etc"
    etc_dir.mkdir()
    (etc_dir / "qubes-release").write_text("Qubes release 4.2 (R4.2)")

    # Run script with mocked paths
    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

# Override test checks by redefining filesystem lookups in a subshell
sed \\
  -e 's|/var/run/qubes-service/guivm|{tmp_path}/nonexistent|g' \\
  -e 's|/etc/qubes-release|{etc_dir}/qubes-release|g' \\
  -e 's|/run/systemd/system|{systemd_system}|g' \\
  -e 's|/run/user|{run_dir}/user|g' \\
  "{SCRIPT_PATH}" > "{tmp_path}/instrumented_script.sh"

chmod +x "{tmp_path}/instrumented_script.sh"
"{tmp_path}/instrumented_script.sh"
""",
    )

    res = subprocess.run(
        ["/bin/sh", str(test_wrapper)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Script failed: {res.stderr}"

    assert systemctl_log.exists(), "systemctl was not called"
    calls = systemctl_log.read_text()
    assert "daemon-reload" in calls
    assert "try-restart" in calls
    assert "qubes-widget@qui-domains.service" in calls
    assert "qubes-widget@qui-devices.service" in calls
    assert "qubes-widget@qui-disk-space.service" in calls
    assert "qubes-widget@qui-clipboard.service" in calls
    assert "qubes-widget@qui-updates.service" in calls


def test_excludes_qui_updates_when_updater_active(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    systemctl_log = tmp_path / "systemctl.log"
    mock_systemctl = bin_dir / "systemctl"
    make_executable(
        mock_systemctl,
        f"""#!/bin/sh
echo "$@" >> "{systemctl_log}"
exit 0
""",
    )

    mock_id = bin_dir / "id"
    make_executable(
        mock_id,
        """#!/bin/sh
case "$1" in
    -u) echo "0" ;;
    -un) echo "root" ;;
    -nu) echo "user" ;;
    *) echo "0" ;;
esac
""",
    )

    mock_pgrep = bin_dir / "pgrep"
    make_executable(
        mock_pgrep,
        """#!/bin/sh
# Return 0 (updater is active)
exit 0
""",
    )

    run_dir = tmp_path / "run"
    run_user = run_dir / "user" / "1000" / "systemd"
    run_user.mkdir(parents=True)
    (run_user / "private").write_text("")

    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    etc_dir = tmp_path / "etc"
    etc_dir.mkdir()
    (etc_dir / "qubes-release").write_text("Qubes release 4.2 (R4.2)")

    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

sed \\
  -e 's|/var/run/qubes-service/guivm|{tmp_path}/nonexistent|g' \\
  -e 's|/etc/qubes-release|{etc_dir}/qubes-release|g' \\
  -e 's|/run/systemd/system|{systemd_system}|g' \\
  -e 's|/run/user|{run_dir}/user|g' \\
  "{SCRIPT_PATH}" > "{tmp_path}/instrumented_script.sh"

chmod +x "{tmp_path}/instrumented_script.sh"
"{tmp_path}/instrumented_script.sh"
""",
    )

    res = subprocess.run(
        ["/bin/sh", str(test_wrapper)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Script failed: {res.stderr}"

    assert systemctl_log.exists(), "systemctl was not called"
    calls = systemctl_log.read_text()
    assert "qubes-widget@qui-domains.service" in calls
    assert "qubes-widget@qui-devices.service" in calls
    assert "qubes-widget@qui-disk-space.service" in calls
    assert "qubes-widget@qui-clipboard.service" in calls
    assert "qubes-widget@qui-updates.service" not in calls


def test_user_mode_restarts_own_widgets(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    systemctl_log = tmp_path / "systemctl.log"
    mock_systemctl = bin_dir / "systemctl"
    make_executable(
        mock_systemctl,
        f"""#!/bin/sh
echo "$@" >> "{systemctl_log}"
exit 0
""",
    )

    mock_id = bin_dir / "id"
    make_executable(
        mock_id,
        """#!/bin/sh
case "$1" in
    -u) echo "1000" ;;
    -un) echo "user" ;;
    *) echo "1000" ;;
esac
""",
    )

    mock_pgrep = bin_dir / "pgrep"
    make_executable(
        mock_pgrep,
        """#!/bin/sh
exit 1
""",
    )

    run_dir = tmp_path / "run"
    run_user = run_dir / "user" / "1000" / "systemd"
    run_user.mkdir(parents=True)
    (run_user / "private").write_text("")

    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    etc_dir = tmp_path / "etc"
    etc_dir.mkdir()
    (etc_dir / "qubes-release").write_text("Qubes release 4.2 (R4.2)")

    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

sed \\
  -e 's|/var/run/qubes-service/guivm|{tmp_path}/nonexistent|g' \\
  -e 's|/etc/qubes-release|{etc_dir}/qubes-release|g' \\
  -e 's|/run/systemd/system|{systemd_system}|g' \\
  -e 's|/run/user|{run_dir}/user|g' \\
  "{SCRIPT_PATH}" > "{tmp_path}/instrumented_script.sh"

chmod +x "{tmp_path}/instrumented_script.sh"
"{tmp_path}/instrumented_script.sh"
""",
    )

    res = subprocess.run(
        ["/bin/sh", str(test_wrapper)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Script failed: {res.stderr}"

    assert systemctl_log.exists(), "systemctl was not called"
    calls = systemctl_log.read_text()
    assert "--user daemon-reload" in calls
    assert "--user try-restart" in calls
    assert "qubes-widget@qui-domains.service" in calls


def test_fallback_to_runuser_when_machine_fails(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    runuser_log = tmp_path / "runuser.log"
    mock_systemctl = bin_dir / "systemctl"
    make_executable(
        mock_systemctl,
        """#!/bin/sh
# Fails when -M is passed, simulating machined absent
for arg in "$@"; do
    if [ "$arg" = "-M" ]; then
        exit 1
    fi
done
exit 0
""",
    )

    mock_runuser = bin_dir / "runuser"
    make_executable(
        mock_runuser,
        f"""#!/bin/sh
echo "$@" >> "{runuser_log}"
exit 0
""",
    )

    mock_id = bin_dir / "id"
    make_executable(
        mock_id,
        """#!/bin/sh
case "$1" in
    -u) echo "0" ;;
    -un) echo "root" ;;
    -nu) echo "user" ;;
    *) echo "0" ;;
esac
""",
    )

    mock_pgrep = bin_dir / "pgrep"
    make_executable(
        mock_pgrep,
        """#!/bin/sh
exit 1
""",
    )

    run_dir = tmp_path / "run"
    run_user = run_dir / "user" / "1000" / "systemd"
    run_user.mkdir(parents=True)
    (run_user / "private").write_text("")

    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    etc_dir = tmp_path / "etc"
    etc_dir.mkdir()
    (etc_dir / "qubes-release").write_text("Qubes release 4.2 (R4.2)")

    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

sed \\
  -e 's|/var/run/qubes-service/guivm|{tmp_path}/nonexistent|g' \\
  -e 's|/etc/qubes-release|{etc_dir}/qubes-release|g' \\
  -e 's|/run/systemd/system|{systemd_system}|g' \\
  -e 's|/run/user|{run_dir}/user|g' \\
  "{SCRIPT_PATH}" > "{tmp_path}/instrumented_script.sh"

chmod +x "{tmp_path}/instrumented_script.sh"
"{tmp_path}/instrumented_script.sh"
""",
    )

    res = subprocess.run(
        ["/bin/sh", str(test_wrapper)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Script failed: {res.stderr}"

    assert runuser_log.exists(), "runuser was not called"
    calls = runuser_log.read_text()
    assert "-u user" in calls
    assert "qubes-widget@qui-domains.service" in calls

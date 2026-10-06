# pylint: disable=missing-docstring,redefined-outer-name,protected-access,import-error
import os
import stat
import subprocess
from pathlib import Path
from qui.tray import updates

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "qubes-restart-widgets"


def make_executable(path: Path, content: str):
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_script_exists_and_is_executable():
    assert SCRIPT_PATH.exists()
    assert os.access(SCRIPT_PATH, os.X_OK)


def test_exit_cleanly_when_not_systemd(tmp_path):
    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
sed -e 's|/run/systemd/system|{tmp_path}/nonexistent|g' \\
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
    assert res.returncode == 0


def test_root_restarts_widgets_for_active_users(tmp_path):
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
echo 0
""",
    )

    mock_loginctl = bin_dir / "loginctl"
    make_executable(
        mock_loginctl,
        """#!/bin/sh
echo " 999 sysuser"
echo " 1000 user1000"
echo " 1001 user1001"
echo " badline"
exit 0
""",
    )

    run_dir = tmp_path / "run"
    # user 1000 has active systemd socket
    user_1000_sock = run_dir / "user" / "1000" / "systemd"
    user_1000_sock.mkdir(parents=True)
    (user_1000_sock / "private").write_text("")

    # user 1001 has no active systemd socket (dir doesn't exist)

    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

sed \\
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
    assert "--user -M 1000@ daemon-reload" in calls
    assert "--user -M 1000@ try-restart" in calls
    assert "qubes-widget@qui-domains.service" in calls
    assert "qubes-widget@qui-devices.service" in calls
    assert "qubes-widget@qui-disk-space.service" in calls
    assert "qubes-widget@qui-clipboard.service" in calls
    assert "qubes-widget@qui-updates.service" in calls

    # Ensure system user (999) and user without private socket (1001) were skipped
    assert "999@" not in calls
    assert "1001@" not in calls


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
echo 1000
""",
    )

    run_dir = tmp_path / "run"
    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

sed \\
  -e 's|/run/systemd/system|{systemd_system}|g' \\
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
    assert "-M" not in calls
    assert "qubes-widget@qui-domains.service" in calls
    assert "qubes-widget@qui-updates.service" in calls


def test_root_continues_if_one_user_fails(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    systemctl_log = tmp_path / "systemctl.log"
    mock_systemctl = bin_dir / "systemctl"
    make_executable(
        mock_systemctl,
        f"""#!/bin/sh
echo "$@" >> "{systemctl_log}"
for arg in "$@"; do
    if [ "$arg" = "1000@" ]; then
        exit 1
    fi
done
exit 0
""",
    )

    mock_id = bin_dir / "id"
    make_executable(
        mock_id,
        """#!/bin/sh
echo 0
""",
    )

    mock_loginctl = bin_dir / "loginctl"
    make_executable(
        mock_loginctl,
        """#!/bin/sh
echo " 1000 user1000"
echo " 1002 user1002"
exit 0
""",
    )

    run_dir = tmp_path / "run"
    for uid in ["1000", "1002"]:
        user_sock = run_dir / "user" / uid / "systemd"
        user_sock.mkdir(parents=True)
        (user_sock / "private").write_text("")

    systemd_system = run_dir / "systemd" / "system"
    systemd_system.mkdir(parents=True)

    test_wrapper = tmp_path / "run_test.sh"
    make_executable(
        test_wrapper,
        f"""#!/bin/sh
export PATH="{bin_dir}:$PATH"

sed \\
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

    assert systemctl_log.exists()
    calls = systemctl_log.read_text()
    assert "--user -M 1000@ daemon-reload" in calls
    assert "--user -M 1000@ try-restart" not in calls
    assert "--user -M 1002@ daemon-reload" in calls
    assert "--user -M 1002@ try-restart" in calls


def test_spawn_detached_uses_systemd_run(monkeypatch):
    called = []

    def mock_which(cmd):
        if cmd == "systemd-run":
            return "/bin/systemd-run"
        return None

    def mock_popen(args, **kwargs):
        called.append((args, kwargs))

    monkeypatch.setattr(updates.shutil, "which", mock_which)
    monkeypatch.setattr(updates.subprocess, "Popen", mock_popen)

    updates._spawn_detached(["qubes-update-gui"])
    assert len(called) == 1
    args, _kwargs = called[0]
    assert args == ["systemd-run", "--user", "--scope", "--quiet", "qubes-update-gui"]


def test_spawn_detached_fallback_when_systemd_run_absent(monkeypatch):
    called = []

    monkeypatch.setattr(updates.shutil, "which", lambda cmd: None)

    def mock_popen(args, **kwargs):
        called.append((args, kwargs))

    monkeypatch.setattr(updates.subprocess, "Popen", mock_popen)

    updates._spawn_detached(["qvm-template-gui"])
    assert len(called) == 1
    args, kwargs = called[0]
    assert args == ["qvm-template-gui"]
    assert kwargs.get("start_new_session") is True


def test_launch_updater_and_template_manager(monkeypatch):
    called = []

    def mock_spawn(cmd):
        called.append(cmd)

    monkeypatch.setattr(updates, "_spawn_detached", mock_spawn)

    updates.UpdatesTray.launch_updater()
    assert called == [["qubes-update-gui"]]

    updates.UpdatesTray.launch_template_manager()
    assert called == [["qubes-update-gui"], ["qvm-template-gui"]]

import sys
import uuid

import pytest

from romeo.autostart import Autostart, SingleInstance, build_command, gui_python, redirect_output


class FakeRegistry:
    def __init__(self):
        self.values = {}

    def get(self, key, name):
        return self.values.get((key, name))

    def set(self, key, name, value):
        self.values[(key, name)] = value

    def delete(self, key, name):
        self.values.pop((key, name), None)


@pytest.fixture
def registry():
    """Real HKCU on Windows (a throwaway key, never the real Run key); fake elsewhere."""
    if sys.platform == "win32":
        import winreg

        from romeo.autostart import WinRegistry

        key = rf"Software\RomeoTest\{uuid.uuid4().hex}"
        yield WinRegistry(), key
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
    else:
        yield FakeRegistry(), r"Software\RomeoTest"


def test_command_runs_romeo_listen_in_background(tmp_path):
    exe = tmp_path / "python.exe"
    exe.write_text("")
    assert build_command(executable=str(exe)) == f'"{exe}" -m romeo listen --background'
    (tmp_path / "pythonw.exe").write_text("")  # windowless interpreter preferred
    assert gui_python(str(exe)) == str(tmp_path / "pythonw.exe")
    assert build_command(("--ui-host", "0.0.0.0"), str(exe)).endswith(
        "listen --background --ui-host 0.0.0.0")


def test_enable_status_disable(registry):
    reg, key = registry
    auto = Autostart(reg, key=key)
    assert auto.status().enabled is False
    command = auto.enable()
    st = auto.status()
    assert st.enabled and st.current and st.command == command
    assert "-m romeo listen --background" in reg.get(key, "Romeo")
    auto.enable(("--no-overlay",))
    assert auto.status().current  # extra flags don't make it stale
    reg.set(key, "Romeo", '"C:\\old\\venv\\pythonw.exe" -m romeo listen --background')
    assert auto.status().current is False  # moved/recreated venv → stale
    assert auto.disable() is True
    assert auto.status().enabled is False
    assert auto.disable() is False  # idempotent


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows guard")
def test_refuses_on_non_windows():
    with pytest.raises(RuntimeError):
        Autostart()


def test_single_instance_blocks_second_copy():
    first, second = SingleInstance("romeo-test-" + uuid.uuid4().hex[:8]), None
    try:
        assert first.acquire()
        second = SingleInstance(first.name)
        assert not second.acquire()
        first.release()
        assert second.acquire()  # free again once the first one exits
    finally:
        first.release()
        if second:
            second.release()


def test_background_output_goes_to_log(isolated_home, monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    path = redirect_output()
    print("hello from background")
    sys.stdout.flush()
    assert "hello from background" in path.read_text("utf-8")
    sys.stdout.close()


def test_open_mic_retries_until_ready():
    from romeo.voice.app import open_mic

    attempts, waits = [], []

    class Mic:
        def __enter__(self):
            attempts.append(1)
            if len(attempts) < 3:
                raise OSError("no default input device")
            return self

    assert isinstance(open_mic(retries=5, delay_s=1, sleep=waits.append, factory=Mic), Mic)
    assert len(attempts) == 3 and waits == [1, 1]

    attempts.clear()
    with pytest.raises(OSError):
        open_mic(retries=1, delay_s=1, sleep=waits.append, factory=Mic)


def test_cli_listen_exits_when_already_running(monkeypatch, capsys):
    from romeo import autostart, cli

    monkeypatch.setattr(autostart.SingleInstance, "acquire", lambda self: False)
    assert cli.main(["listen", "--no-mic"]) == 1
    assert "already running" in capsys.readouterr().out

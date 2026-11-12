"""Servers must import and expose their tools on any OS (Windows libs load lazily)."""
import asyncio


def _names(server):
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def test_windows_tools_registered():
    from romeo.windows_mcp import server
    names = _names(server)
    assert {"screenshot", "get_ui_tree", "click", "type_text", "run_powershell"} <= names


def test_iphone_tools_registered():
    from romeo.iphone_mcp import server
    names = _names(server)
    assert {"iphone_screenshot", "iphone_tap", "iphone_send_message", "iphone_call"} <= names


def test_blocked_action_returns_message(monkeypatch):
    from romeo.common.safety import default_gate
    from romeo.windows_mcp import server
    monkeypatch.setattr(server, "_active_title", lambda: "K PLUS")
    assert "ปฏิเสธ" in server.click(10, 10)


def test_kill_switch_via_cli():
    from romeo.cli import main
    from romeo.common.safety import KillSwitch
    main(["stop"])
    assert KillSwitch().engaged()
    main(["resume"])
    assert not KillSwitch().engaged()


def test_operator_prompt_formats():
    from romeo.cli import operator_prompt
    out = operator_prompt().format(tool_descriptions="TOOLS", skill_examples="")
    assert "Romeo" in out and "TOOLS" in out

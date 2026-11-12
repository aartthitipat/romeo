"""`romeo` command: setup, stop/resume (kill switch), route preview, audit tail."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from romeo.common.safety import KillSwitch, romeo_home


def _openjarvis_home() -> Path:
    return Path(os.environ.get("OPENJARVIS_HOME", Path.home() / ".openjarvis"))


def operator_prompt() -> str:
    rules = resources.files("romeo.agent.prompts").joinpath("operator.md").read_text("utf-8")
    try:
        from openjarvis.agents.native_react import REACT_SYSTEM_PROMPT
    except ImportError:
        REACT_SYSTEM_PROMPT = (
            "For each step respond with exactly one of:\n\n"
            "Thought: <reasoning>\nAction: <tool_name>\nAction Input: <json arguments>\n\n"
            "or\n\nThought: <reasoning>\nFinal Answer: <answer>\n\n"
            "{skill_examples}{tool_descriptions}"
        )
    return rules.rstrip() + "\n\n# Output format\n\n" + REACT_SYSTEM_PROMPT


def mcp_servers_json() -> str:
    exe_dir = Path(sys.executable).parent
    def cmd(name: str) -> str:
        found = shutil.which(name) or shutil.which(name, path=str(exe_dir))
        return found or name

    servers = [{"name": "romeo-windows", "command": cmd("romeo-windows"), "args": []},
               {"name": "romeo-iphone", "command": cmd("romeo-iphone"), "args": []}]
    return json.dumps(servers, ensure_ascii=False)


def cmd_setup(args: argparse.Namespace) -> int:
    home = _openjarvis_home()
    prompt_path = home / "agents" / "native_react" / "system_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(operator_prompt(), encoding="utf-8")
    print(f"✓ wrote operator prompt → {prompt_path}")

    servers_path = romeo_home() / "mcp_servers.json"
    servers_path.parent.mkdir(parents=True, exist_ok=True)
    servers_path.write_text(mcp_servers_json(), encoding="utf-8")
    print(f"✓ wrote MCP server list → {servers_path}")
    print("\nNext: add this to ~/.openjarvis/config.toml (see configs/config.toml):")
    print(f'[tools.mcp]\nenabled = true\nservers = "{servers_path.as_posix()}"')
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    KillSwitch().engage("romeo stop")
    print("■ kill switch engaged — every Romeo action is now refused. `romeo resume` to undo.")
    return 0


def cmd_resume(_: argparse.Namespace) -> int:
    KillSwitch().release()
    print("▶ kill switch released.")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    from romeo.agent.router import route

    r = route(" ".join(args.request))
    print(f"{r.engine} / {r.model}  ({r.reason})")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from romeo.common.audit import log_path

    path = log_path()
    if not path.exists():
        print("(no audit log yet)")
        return 0
    for line in path.read_text("utf-8").splitlines()[-args.n:]:
        print(line)
    return 0


def _voice_errors(fn):
    try:
        return fn()
    except ImportError as exc:
        print(f"✗ missing voice dependency ({exc.name}). Install: uv pip install -e \".[voice]\"")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"✗ {exc}")
    return 1


def _ui_options(args: argparse.Namespace):
    from romeo.voice.app import UiOptions

    return UiOptions(dashboard=not getattr(args, "no_ui", False),
                     overlay=False if getattr(args, "no_overlay", False) else None,
                     host=args.ui_host, port=args.ui_port, open_browser=not args.no_browser)


def cmd_listen(args: argparse.Namespace) -> int:
    from romeo.voice.app import listen

    return _voice_errors(lambda: listen(no_mic=args.no_mic, ui=_ui_options(args)))


def cmd_ui(args: argparse.Namespace) -> int:
    from romeo.voice.app import dashboard_only

    return _voice_errors(lambda: dashboard_only(_ui_options(args)))


def _add_ui_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--ui-host", default="127.0.0.1",
                   help="dashboard address; 0.0.0.0 lets the iPhone open it (needs ROMEO_BRIDGE_TOKEN)")
    p.add_argument("--ui-port", type=int, default=8767)
    p.add_argument("--no-browser", action="store_true", help="do not open the dashboard automatically")


def cmd_voice(args: argparse.Namespace) -> int:
    from romeo.voice import app

    if args.action == "enroll":
        return _voice_errors(lambda: app.enroll(args.count))
    return _voice_errors(lambda: app.live_test(args.seconds))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="romeo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="install prompt + MCP server list for OpenJarvis").set_defaults(fn=cmd_setup)
    sub.add_parser("stop", help="engage kill switch").set_defaults(fn=cmd_stop)
    sub.add_parser("resume", help="release kill switch").set_defaults(fn=cmd_resume)
    p = sub.add_parser("route", help="show which model a request would use")
    p.add_argument("request", nargs="+")
    p.set_defaults(fn=cmd_route)
    p = sub.add_parser("audit", help="show recent audit log entries")
    p.add_argument("-n", type=int, default=20)
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("listen", help='always listen for "Hey Romeo" (+ Siri /ask endpoint)')
    p.add_argument("--no-mic", action="store_true", help="only serve Siri and the dashboard")
    p.add_argument("--no-ui", action="store_true", help="no web dashboard")
    p.add_argument("--no-overlay", action="store_true", help="no floating bubble on screen")
    _add_ui_flags(p)
    p.set_defaults(fn=cmd_listen)
    p = sub.add_parser("ui", help="open the web dashboard only (type commands, see history)")
    _add_ui_flags(p)
    p.set_defaults(fn=cmd_ui)
    p = sub.add_parser("voice", help="voice setup: enroll your voice or test the wake word")
    p.add_argument("action", choices=["enroll", "test"])
    p.add_argument("--count", type=int, default=5, help="enroll: number of recordings")
    p.add_argument("--seconds", type=float, default=60.0, help="test: how long to listen")
    p.set_defaults(fn=cmd_voice)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

import threading

import httpx
import pytest

from romeo.iphone_mcp.shortcuts_bridge import ShortcutsBridge

TOKEN = "t" * 32


@pytest.fixture
def bridge():
    b = ShortcutsBridge(TOKEN, host="127.0.0.1", port=0)
    b.start()
    b.port = b._server.server_address[1]
    yield b
    b.stop()


def test_rejects_short_token():
    with pytest.raises(ValueError):
        ShortcutsBridge("short")


def test_job_roundtrip(bridge):
    base = f"http://127.0.0.1:{bridge.port}"
    h = {"X-Romeo-Token": TOKEN}
    assert httpx.get(base + "/next", headers={"X-Romeo-Token": "bad"}).status_code == 401
    assert httpx.get(base + "/next", headers=h).status_code == 204

    result = {}
    t = threading.Thread(target=lambda: result.setdefault(
        "job", bridge.submit("notify", {"text": "สวัสดี"}, wait_s=5)))
    t.start()
    job = None
    for _ in range(50):
        r = httpx.get(base + "/next", headers=h)
        if r.status_code == 200:
            job = r.json()
            break
    assert job["action"] == "notify" and job["text"] == "สวัสดี"
    assert httpx.post(base + "/result", headers=h,
                      json={"id": job["id"], "ok": True, "output": "shown"}).status_code == 200
    t.join(5)
    assert result["job"].ok is True and result["job"].output == "shown"


def test_unknown_action(bridge):
    with pytest.raises(ValueError):
        bridge.submit("format_phone", {})

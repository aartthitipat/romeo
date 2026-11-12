import json
import threading

import httpx
import pytest

from romeo.common import audit
from romeo.ui.events import EventHub
from romeo.ui.overlay import OverlayModel, shorten
from romeo.ui.server import DashboardServer
from romeo.voice.runner import CommandRunner

TOKEN = "k" * 24


def no_devices():
    return {"windows": {"ok": True, "detail": "test"}, "iphone": {"ok": False, "detail": "test"}}


@pytest.fixture
def dash():
    hub = EventHub()
    runner = CommandRunner(lambda t, e, m: f"ตอบ:{t}", on_event=hub.emit)
    srv = DashboardServer(hub, runner, port=0, wake_model="hey_romeo.onnx", devices=no_devices)
    srv.start()
    yield srv, f"http://127.0.0.1:{srv.port}"
    srv.stop()
    runner.kill_switch.release()


# ------------------------------------------------------------------ hub ---

def test_hub_publish_subscribe_and_history():
    hub = EventHub(history=3)
    q = hub.subscribe()
    for i in range(5):
        hub.publish("heard", {"text": str(i)})
    hub.publish("state", {"state": "thinking"})
    assert hub.state == "thinking"
    assert q.qsize() == 6
    assert [e["kind"] for e in hub.history()] == ["heard", "heard", "state"]
    last = hub.history()[-1]["id"]
    assert hub.history(after_id=last) == []
    hub.unsubscribe(q)
    hub.publish("heard", {"text": "x"})
    assert q.qsize() == 6


# --------------------------------------------------------------- server ---

def test_page_and_state(dash):
    srv, base = dash
    page = httpx.get(base + "/")
    assert page.status_code == 200 and "Romeo" in page.text and "text/html" in page.headers["content-type"]
    s = httpx.get(base + "/api/state").json()
    assert s["state"] == "idle" and s["local"] is True and s["wake_model"] == "hey_romeo.onnx"


def test_ask_publishes_conversation(dash):
    srv, base = dash
    r = httpx.post(base + "/api/ask", json={"text": "Hey Romeo วันนี้วันอะไร"})
    assert r.json() == {"reply": "ตอบ:วันนี้วันอะไร"}
    kinds = [(e["kind"], e.get("state") or e.get("text")) for e in srv.hub.history()]
    assert kinds == [("heard", "วันนี้วันอะไร"), ("state", "thinking"),
                     ("reply", "ตอบ:วันนี้วันอะไร"), ("state", "idle")]
    assert all(e.get("source", "web") == "web" for e in srv.hub.history() if e["kind"] != "state")
    assert httpx.post(base + "/api/ask", json={"text": "  "}).status_code == 400


def test_stop_and_resume(dash):
    srv, base = dash
    assert httpx.post(base + "/api/stop").json() == {"stopped": True}
    assert httpx.get(base + "/api/state").json()["state"] == "stopped"
    assert "หยุดอยู่" in httpx.post(base + "/api/ask", json={"text": "เปิด notepad"}).json()["reply"]
    assert httpx.post(base + "/api/resume").json() == {"stopped": False}
    assert not srv.runner.kill_switch.engaged()


def test_audit_and_devices(dash):
    srv, base = dash
    audit.record("windows", "click", {"x": 1, "y": 2}, "allow")
    audit.record("windows", "run_powershell", {"command": "dir"}, "user_denied")
    rows = httpx.get(base + "/api/audit?n=10").json()
    assert [r["verdict"] for r in rows] == ["user_denied", "allow"]  # newest first
    assert httpx.get(base + "/api/devices").json()["windows"]["ok"] is True


def test_sse_stream_delivers_events(dash):
    srv, base = dash
    srv.hub.publish("heard", {"text": "ก่อนเชื่อมต่อ", "source": "voice"})
    got = []

    def reader():
        with httpx.stream("GET", base + "/api/events?after=0", timeout=5) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    got.append(json.loads(line[6:]))
                    if len(got) == 2:
                        return

    t = threading.Thread(target=reader)
    t.start()
    for _ in range(50):
        if got:
            break
        threading.Event().wait(0.05)
    srv.hub.publish("reply", {"text": "สด", "source": "voice"})
    t.join(5)
    assert [e["text"] for e in got] == ["ก่อนเชื่อมต่อ", "สด"]


def test_remote_dashboard_requires_token():
    hub, runner = EventHub(), CommandRunner(lambda *a: "ok")
    with pytest.raises(ValueError):
        DashboardServer(hub, runner, host="0.0.0.0", port=0)
    srv = DashboardServer(hub, runner, host="0.0.0.0", port=0, token=TOKEN, devices=no_devices)
    srv.start()
    try:
        base = f"http://127.0.0.1:{srv.port}"
        assert httpx.get(base + "/").status_code == 200  # page itself is public, data is not
        assert httpx.get(base + "/api/state").status_code == 401
        assert httpx.get(base + "/api/state", headers={"X-Romeo-Token": "wrong"}).status_code == 401
        assert httpx.get(base + "/api/state", headers={"X-Romeo-Token": TOKEN}).status_code == 200
        assert httpx.get(base + f"/api/state?token={TOKEN}").status_code == 200
    finally:
        srv.stop()


# -------------------------------------------------------------- overlay ---

def test_overlay_shows_during_conversation_and_hides_after():
    m = OverlayModel(hide_after_s=2.0)
    assert not m.visible
    m.apply({"kind": "state", "state": "awake"}, now=0)
    assert m.visible and m.label == "ได้ยินแล้ว"
    m.apply({"kind": "heard", "text": "เปิด Chrome"}, now=1)
    m.apply({"kind": "state", "state": "thinking"}, now=1)
    assert m.color == "#8b5cf6"
    m.apply({"kind": "reply", "text": "เปิดแล้วครับ"}, now=2)
    m.apply({"kind": "state", "state": "follow_up"}, now=3)
    m.tick(now=100)
    assert m.visible  # still in the follow-up window
    m.apply({"kind": "state", "state": "idle"}, now=10)
    m.tick(now=11)
    assert m.visible
    m.tick(now=12.1)
    assert not m.visible


def test_overlay_new_conversation_clears_old_text():
    m = OverlayModel()
    m.apply({"kind": "heard", "text": "เก่า"}, now=0)
    m.apply({"kind": "state", "state": "idle"}, now=0)
    m.tick(now=100)
    m.apply({"kind": "state", "state": "awake"}, now=101)
    assert m.heard == "" and m.reply == ""


def test_overlay_stays_on_emergency_stop_and_shortens_text():
    m = OverlayModel()
    m.apply({"kind": "state", "state": "stopped"}, now=0)
    m.tick(now=1000)
    assert m.visible and m.color == "#e5484d"
    assert len(shorten("ก" * 500, 140)) == 140


# ---------------------------------------------- assistant → hub events ---

def test_assistant_emits_events_in_order():
    from tests.test_voice import SILENCE, SPEECH, WAKE, feed, make

    a, _, _ = make()
    events = []
    a.hooks.event = lambda kind, data: events.append((kind, data.get("state") or data.get("text")))
    a.runner._event = a.hooks.event
    feed(a, (WAKE, 3), (SPEECH, 4), (SILENCE, 10))
    assert events[:2] == [("state", "awake"), ("state", "listening")]
    assert ("heard", "คลิกปุ่ม Save") in events
    assert ("state", "thinking") in events
    assert events.index(("state", "speaking")) > events.index(("reply", "เรียบร้อยครับ"))
    assert events[-1] == ("state", "follow_up")

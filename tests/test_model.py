import httpx
import pytest

from romeo.ui.events import EventHub
from romeo.ui.model import find_model, pick_glb
from romeo.ui.server import DashboardServer, static_file
from romeo.voice.runner import CommandRunner

GLB = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 64  # header is enough for serving tests
TOKEN = "t" * 24


def no_devices():
    return {}


# ------------------------------------------------------------- discovery ---

def test_pick_prefers_named_character(tmp_path):
    for name in ("zebra.glb", "a_scene.glb", "My_Romeo.glb", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert pick_glb(tmp_path).name == "My_Romeo.glb"
    (tmp_path / "My_Romeo.glb").unlink()
    assert pick_glb(tmp_path).name == "a_scene.glb"  # otherwise alphabetical
    assert pick_glb(tmp_path / "missing") is None


def test_find_model_order(tmp_path, monkeypatch):
    ui = tmp_path / "UI"
    ui.mkdir()
    (ui / "avatar.glb").write_bytes(b"x")
    other = tmp_path / "other.glb"
    other.write_bytes(b"x")
    monkeypatch.delenv("ROMEO_MODEL", raising=False)

    assert find_model(search=[tmp_path / "empty", ui]).name == "avatar.glb"
    assert find_model(search=[]) is None
    monkeypatch.setenv("ROMEO_MODEL", str(other))
    assert find_model(search=[ui]).name == "other.glb"  # env beats the UI folder
    assert find_model(str(ui), search=[]).name == "avatar.glb"  # --model beats env
    with pytest.raises(FileNotFoundError):
        find_model(str(tmp_path / "nope.glb"))


def test_default_search_includes_project_ui_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("ROMEO_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "UI").mkdir()
    (tmp_path / "UI" / "romeo.glb").write_bytes(b"x")
    assert find_model().name == "romeo.glb"


# ---------------------------------------------------------------- server ---

@pytest.fixture
def served(tmp_path):
    model = tmp_path / "romeo.glb"
    model.write_bytes(GLB)
    srv = DashboardServer(EventHub(), CommandRunner(lambda *a: "ok"), port=0,
                          devices=no_devices, model_path=model)
    srv.start()
    yield srv, f"http://127.0.0.1:{srv.port}"
    srv.stop()


def test_model_api_and_download(served):
    srv, base = served
    info = httpx.get(base + "/api/model").json()
    assert info == {"available": True, "name": "romeo.glb", "size": len(GLB), "url": "/model.glb"}
    r = httpx.get(base + "/model.glb")
    assert r.status_code == 200 and r.content == GLB
    assert r.headers["content-type"] == "model/gltf-binary"


def test_no_model_keeps_orb():
    srv = DashboardServer(EventHub(), CommandRunner(lambda *a: "ok"), port=0, devices=no_devices)
    srv.start()
    try:
        base = f"http://127.0.0.1:{srv.port}"
        assert httpx.get(base + "/api/model").json() == {"available": False}
        assert httpx.get(base + "/model.glb").status_code == 404
    finally:
        srv.stop()


def test_static_assets_served_with_types(served):
    _, base = served
    for path, ctype in [("/static/avatar.js", "text/javascript"),
                        ("/static/vendor/three/three.module.min.js", "text/javascript"),
                        ("/static/vendor/three/addons/loaders/GLTFLoader.js", "text/javascript"),
                        ("/static/vendor/three/addons/libs/draco/gltf/draco_decoder.wasm",
                         "application/wasm")]:
        r = httpx.get(base + path)
        assert r.status_code == 200, path
        assert r.headers["content-type"].startswith(ctype), path


def test_static_refuses_traversal(served):
    _, base = served
    assert static_file("../server.py") is None
    assert static_file("../../common/safety.py") is None
    assert httpx.get(base + "/static/../server.py").status_code == 404
    assert httpx.get(base + "/static/%2e%2e/server.py").status_code == 404


def test_remote_model_needs_token(tmp_path):
    model = tmp_path / "romeo.glb"
    model.write_bytes(GLB)
    srv = DashboardServer(EventHub(), CommandRunner(lambda *a: "ok"), host="0.0.0.0", port=0,
                          token=TOKEN, devices=no_devices, model_path=model)
    srv.start()
    try:
        base = f"http://127.0.0.1:{srv.port}"
        assert httpx.get(base + "/static/avatar.js").status_code == 200  # code is public
        assert httpx.get(base + "/model.glb").status_code == 401  # the model is not
        assert httpx.get(base + f"/model.glb?token={TOKEN}").content == GLB
    finally:
        srv.stop()


def test_page_wires_importmap_and_avatar():
    from importlib import resources

    html = resources.files("romeo.ui").joinpath("static/index.html").read_text("utf-8")
    assert '"three": "/static/vendor/three/three.module.min.js"' in html
    assert 'import("/static/avatar.js")' in html and 'id="avatar-wrap"' in html

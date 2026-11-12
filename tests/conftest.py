import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ROMEO_HOME", str(tmp_path / "romeo"))
    import romeo.common.safety as safety
    import romeo.common.approval as approval

    monkeypatch.setattr(safety, "_default_gate", None)
    monkeypatch.setattr(approval, "_default", None)
    yield tmp_path

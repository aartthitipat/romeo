import pytest

from romeo.common import approval
from romeo.common.guard import ActionBlocked, guard
from romeo.common.safety import KillSwitch, Risk, SafetyGate, Verdict


def test_read_and_act_are_allowed():
    gate = SafetyGate()
    assert gate.check("screenshot", Risk.READ, targets=["Notepad"]).allowed
    assert gate.check("click", Risk.ACT, targets=["Google Chrome"]).allowed


@pytest.mark.parametrize("target", ["K PLUS", "SCB EASY", "com.kasikornbank.kplus",
                                    "เป๋าตัง", "Bitwarden", "Krungthai NEXT"])
def test_banking_and_secret_apps_denied(target):
    assert SafetyGate().check("click", Risk.ACT, targets=[target]).verdict is Verdict.DENY


@pytest.mark.parametrize("text", ["my password is 1234", "รหัส OTP 445566", "รหัสผ่าน"])
def test_typing_secrets_denied(text):
    assert SafetyGate().check("type_text", Risk.ACT, text=text).verdict is Verdict.DENY


def test_sensitive_needs_approval():
    assert SafetyGate().check("run_powershell", Risk.SENSITIVE).verdict is Verdict.ASK


def test_dangerous_command_escalates_to_ask():
    d = SafetyGate().check("x", Risk.ACT, command="Remove-Item C:\\tmp -Recurse")
    assert d.verdict is Verdict.ASK


def test_kill_switch_blocks_everything(tmp_path):
    ks = KillSwitch(tmp_path / "STOP")
    gate = SafetyGate(kill_switch=ks)
    ks.engage()
    assert gate.check("screenshot", Risk.READ).verdict is Verdict.DENY
    ks.release()
    assert gate.check("screenshot", Risk.READ).allowed


def test_guard_denied_by_user_raises():
    approval.set_default_approver(approval.Approver(lambda a, d: False))
    with pytest.raises(ActionBlocked):
        guard("windows", "run_powershell", Risk.SENSITIVE, {"command": "dir"})


def test_guard_approved_and_audited(isolated_home):
    approval.set_default_approver(approval.Approver(lambda a, d: True))
    guard("windows", "run_powershell", Risk.SENSITIVE, {"command": "dir"})
    log = (isolated_home / "romeo" / "logs" / "audit.jsonl").read_text("utf-8")
    assert "user_approved" in log


def test_headless_default_denies_sensitive():
    # No callback and not on Windows -> never silently approve.
    import sys
    if sys.platform != "win32":
        assert approval.Approver().request("x") is False

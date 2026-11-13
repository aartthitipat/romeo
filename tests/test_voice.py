import httpx
import numpy as np
import pytest

from romeo.common.safety import KillSwitch
from romeo.voice.ask_server import AskServer
from romeo.voice.assistant import Hooks, State, Timing, VoiceAssistant
from romeo.voice.audio import FRAME, RingBuffer, seconds_to_frames
from romeo.voice.runner import CommandRunner, clean_command, is_stop
from romeo.voice.speaker import SpeakerVerifier
from romeo.voice.wakeword import WakeDetector, keywords_for

# Fake audio: frame value 0 = silence, 1 = speech, 9 = the wake phrase.
SILENCE, SPEECH, WAKE = 0, 1, 9


def frame(kind: int) -> np.ndarray:
    return np.full(FRAME, kind, dtype=np.int16)


class FakeVAD:
    def is_speech(self, f):
        return f[0] != SILENCE


def wake_scorer(f):
    return 0.95 if f[0] == WAKE else 0.01


def make(stt_text="hey romeo", command_text="คลิกปุ่ม Save", speaker=None, replies=None):
    calls = []

    def stt(wav, language):
        calls.append(language)
        return stt_text if language is None else command_text

    asked = []

    def ask(text, engine, model):
        asked.append((text, engine))
        return (replies or {}).get(text, "เรียบร้อยครับ")

    spoken = []
    hooks = Hooks(stt=stt, speak=spoken.append, log=lambda *_: None)
    a = VoiceAssistant(WakeDetector(wake_scorer, candidate_threshold=0.5, confirm_threshold=0.7),
                       FakeVAD(), CommandRunner(ask), hooks, speaker=speaker,
                       keywords=keywords_for("hey_romeo.onnx"), verify_with_stt=True,
                       timing=Timing(end_silence_s=0.4, start_timeout_s=0.8, follow_up_s=0.8))
    return a, asked, spoken


def feed(a, *kinds_and_counts):
    for kind, n in kinds_and_counts:
        for _ in range(n):
            a.step(frame(kind))


# ---------------------------------------------------------------- detector --

def test_detector_needs_several_strong_frames():
    det = WakeDetector(lambda f: f[0] / 100, candidate_threshold=0.5, confirm_threshold=0.7)
    assert det.process(frame(60)) is None  # candidate but not confirmed
    assert det.process(frame(80)) is None  # one strong frame
    assert det.process(frame(80)) is not None  # second strong frame confirms
    assert det.process(frame(90)) is None  # cooldown


def test_detector_ignores_single_spike():
    det = WakeDetector(lambda f: f[0] / 100, candidate_threshold=0.5, confirm_threshold=0.7)
    events = [det.process(frame(v)) for v in (1, 95, 1, 1, 1, 1, 1, 1, 1, 95)]
    assert not any(events)


def test_keywords_from_model_name():
    assert keywords_for("C:/x/hey_romeo.onnx")[0] == "romeo"
    assert "โรมิโอ" in keywords_for("hey_romeo_v0.1.onnx")
    assert keywords_for("hey_jarvis")[0] == "jarvis"


def test_ring_buffer_keeps_only_recent():
    rb = RingBuffer(0.16)  # 2 frames
    for v in (1, 2, 3):
        rb.append(frame(v))
    assert rb.last().size == 2 * FRAME and rb.last()[0] == 2


# --------------------------------------------------------------- assistant --

def test_full_flow_wake_command_reply_follow_up():
    a, asked, spoken = make()
    feed(a, (SILENCE, 5), (WAKE, 3))
    assert a.state is State.LISTENING
    feed(a, (SPEECH, 10), (SILENCE, seconds_to_frames(0.4)))
    assert asked == [("คลิกปุ่ม Save", "cloud")]  # GUI task routed to Claude
    assert spoken == ["เรียบร้อยครับ"]
    assert a.state is State.FOLLOW_UP
    # follow-up without saying the wake word again
    feed(a, (SPEECH, 4), (SILENCE, seconds_to_frames(0.4)))
    assert len(asked) == 2
    # silence → back to idle
    feed(a, (SILENCE, seconds_to_frames(0.8) + 1))
    assert a.state is State.IDLE


def test_stt_confirmation_rejects_false_trigger():
    a, asked, _ = make(stt_text="hello there")
    feed(a, (WAKE, 3), (SPEECH, 5), (SILENCE, 10))
    assert a.state is State.IDLE and asked == []


def test_thai_transcription_of_wake_word_accepted():
    a, _, _ = make(stt_text="เฮ้ โรมิโอ")
    feed(a, (WAKE, 3))
    assert a.state is State.LISTENING


def test_wake_without_voice_activity_rejected():
    a, _, _ = make()
    a.vad = type("Silent", (), {"is_speech": lambda self, f: False})()
    feed(a, (WAKE, 3))
    assert a.state is State.IDLE


def test_speaker_verification_blocks_other_voice(tmp_path):
    owner = np.array([1.0, 0.0], dtype=np.float32)
    np.save(tmp_path / "owner.npy", owner)
    stranger = SpeakerVerifier(embedder=lambda s: np.array([0.0, 1.0]), path=tmp_path / "owner.npy")
    a, _, _ = make(speaker=stranger)
    feed(a, (WAKE, 3))
    assert a.state is State.IDLE

    me = SpeakerVerifier(embedder=lambda s: np.array([0.9, 0.1]), path=tmp_path / "owner.npy")
    a, _, _ = make(speaker=me)
    feed(a, (WAKE, 3))
    assert a.state is State.LISTENING


def test_enroll_saves_profile(tmp_path):
    v = SpeakerVerifier(embedder=lambda s: np.array([3.0, 4.0]), path=tmp_path / "o.npy")
    with pytest.raises(ValueError):
        v.enroll([np.zeros(16000, dtype=np.int16)])
    v.enroll([np.zeros(16000, dtype=np.int16)] * 3)
    assert v.enrolled and (tmp_path / "o.npy").exists()
    assert v.verify(np.zeros(16000, dtype=np.int16))[0]


def test_voice_stop_engages_kill_switch():
    a, asked, spoken = make(command_text="หยุด")
    feed(a, (WAKE, 3), (SPEECH, 4), (SILENCE, 10))
    assert KillSwitch().engaged()
    assert asked == []  # never reached the LLM
    assert a.state is State.IDLE
    KillSwitch().release()


# ------------------------------------------------------------------ runner --

def test_clean_command_and_stop_words():
    assert clean_command("Hey Romeo, เปิด Chrome") == "เปิด Chrome"
    assert clean_command("โรมิโอ ปิดเสียง") == "ปิดเสียง"
    assert is_stop("Hey Romeo stop")
    assert is_stop("หยุดทุกอย่าง")
    assert not is_stop("หยุดเพลง")  # stopping music is a normal command


def test_cloud_failure_falls_back_to_local():
    seen = []

    def ask(text, engine, model):
        seen.append(engine)
        if engine == "cloud":
            raise RuntimeError("no API key")
        return "ok"

    assert CommandRunner(ask).handle("คลิกปุ่ม Save") == "ok"
    assert seen == ["cloud", "ollama"]


def test_runner_refuses_while_stopped():
    r = CommandRunner(lambda *a: "should not run")
    r.kill_switch.engage()
    assert "หยุดอยู่" in r.handle("เปิด notepad")
    r.kill_switch.release()


# -------------------------------------------------------------- ask server --

def test_ask_server_token_and_reply():
    srv = AskServer("s" * 20, CommandRunner(lambda t, e, m: f"echo:{t}"), host="127.0.0.1", port=0)
    srv.start()
    try:
        url = f"http://127.0.0.1:{srv.port}/ask"
        assert httpx.post(url, json={"text": "hi"}, headers={"X-Romeo-Token": "bad"}).status_code == 401
        r = httpx.post(url, json={"text": "Hey Romeo วันนี้วันอะไร"}, headers={"X-Romeo-Token": "s" * 20})
        assert r.json() == {"reply": "echo:วันนี้วันอะไร"}
    finally:
        srv.stop()


# --------------------------------------------------- real openWakeWord model --

def test_real_model_quiet_on_noise():
    pytest.importorskip("openwakeword")
    from romeo.voice.wakeword import openwakeword_scorer

    det = WakeDetector(openwakeword_scorer("hey_jarvis"))
    rng = np.random.default_rng(0)
    events = [det.process((rng.normal(0, 300, FRAME)).astype(np.int16)) for _ in range(60)]
    assert not any(events)

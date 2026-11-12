"""Wire the voice assistant to the microphone and OpenJarvis speech backends."""

from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np

from romeo.voice import audio


def _session():
    from openjarvis.cli._voice_chat import VoiceSession

    return VoiceSession()


def openjarvis_stt(session=None):
    session = session or _session()
    backend = session.get_stt_backend()
    if backend is None:
        raise RuntimeError("no speech-to-text backend — install one, e.g. "
                           "`uv pip install faster-whisper`, then check `jarvis doctor`")

    def stt(wav: bytes, language: Optional[str]) -> str:
        return backend.transcribe(wav, format="wav", language=language).text or ""

    return stt


def openjarvis_speak(session=None):
    from rich.console import Console
    from openjarvis.cli._voice_chat import speak

    session = session or _session()
    console = Console()

    def say(text: str) -> None:
        try:
            speak(text, console, session)
        except Exception as exc:
            console.print(f"[dim](TTS unavailable: {exc})[/dim]")

    return say


def chime(kind: str) -> None:
    tones = {"wake": [(880, 0.09), (1320, 0.11)], "done": [(660, 0.08)], "reject": [(220, 0.12)]}
    if kind in tones:
        audio.play(np.concatenate([audio.beep(f, s) for f, s in tones[kind]]))


def build_assistant(mic: audio.MicStream):
    from romeo.voice.assistant import Hooks, VoiceAssistant
    from romeo.voice.runner import CommandRunner
    from romeo.voice.speaker import SpeakerVerifier
    from romeo.voice.vad import VoiceActivity
    from romeo.voice.wakeword import WakeDetector, default_model, keywords_for, openwakeword_scorer

    model = default_model()
    session = _session()
    hooks = Hooks(stt=openjarvis_stt(session), speak=openjarvis_speak(session),
                  chime=chime, flush=mic.flush)
    assistant = VoiceAssistant(
        WakeDetector(openwakeword_scorer(model)),
        VoiceActivity(),
        CommandRunner(),
        hooks,
        speaker=SpeakerVerifier(),
        keywords=keywords_for(model),
        language=os.environ.get("ROMEO_LANGUAGE", "th"),
    )
    return assistant, model


def listen(no_mic: bool = False) -> int:
    from romeo.voice.ask_server import AskServer
    from romeo.voice.runner import CommandRunner

    token = os.environ.get("ROMEO_BRIDGE_TOKEN")
    server = None
    if token:
        server = AskServer(token, CommandRunner(),
                           host=os.environ.get("ROMEO_ASK_HOST", "0.0.0.0"),
                           port=int(os.environ.get("ROMEO_ASK_PORT", "8766")))
        server.start()
        print(f"✓ Siri endpoint: POST http://<this PC>:{server.port}/ask")
    else:
        print("ℹ set ROMEO_BRIDGE_TOKEN to enable 'Hey Siri, Romeo' from the iPhone")

    if no_mic:
        if server is None:
            print("nothing to do: --no-mic without ROMEO_BRIDGE_TOKEN")
            return 1
        print("listening for Siri requests only… Ctrl+C to quit")
        try:
            import threading

            threading.Event().wait()
        except KeyboardInterrupt:
            return 0

    with audio.MicStream() as mic:
        assistant, model = build_assistant(mic)
        word = assistant.keywords[0]
        print(f"✓ wake model: {model}  — say “Hey {word.title()}”  (Ctrl+C to quit)")
        if not assistant.speaker or not assistant.speaker.enrolled:
            print("ℹ voice not enrolled — anyone can wake Romeo. Run `romeo voice enroll`.")
        try:
            assistant.run(mic)
        except KeyboardInterrupt:
            pass
    if server:
        server.stop()
    return 0


def enroll(count: int = 5) -> int:
    from romeo.voice.speaker import SpeakerVerifier
    from romeo.voice.wakeword import default_model, keywords_for

    word = keywords_for(default_model())[0].title()
    clips = []
    with audio.MicStream() as mic:
        for i in range(count):
            input(f"[{i + 1}/{count}] กด Enter แล้วพูด “Hey {word}” …")
            mic.flush()
            clips.append(mic.record(2.0))
            chime("done")
    verifier = SpeakerVerifier()
    verifier.enroll(clips)
    print(f"✓ saved your voice profile → {verifier.path}")
    return 0


def live_test(seconds: float = 60.0) -> int:
    from romeo.voice.vad import VoiceActivity
    from romeo.voice.wakeword import WakeDetector, default_model, openwakeword_scorer

    model = default_model()
    det, vad = WakeDetector(openwakeword_scorer(model)), VoiceActivity()
    print(f"model {model} · VAD {vad.backend} · candidate ≥{det.candidate_threshold} "
          f"confirm ≥{det.confirm_threshold} — speak now (Ctrl+C to stop)")
    with audio.MicStream() as mic:
        try:
            for i, frame in enumerate(mic):
                event = det.process(frame)
                bar = "█" * int(det.last_score * 40)
                speech = "🗣" if vad.is_speech(frame) else "  "
                sys.stdout.write(f"\r{speech} {det.last_score:0.2f} {bar:<40}")
                if event:
                    sys.stdout.write(f"  ← WAKE ({event.score:.2f})\n")
                sys.stdout.flush()
                if i * audio.FRAME_SECONDS >= seconds:
                    break
        except KeyboardInterrupt:
            pass
    print()
    return 0

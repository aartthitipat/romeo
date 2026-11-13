# แผน: ปลุก Romeo ด้วยเสียง "Hey Romeo" (เลียนแบบสถาปัตยกรรม "Hey Siri")

## Context
ผู้ใช้อยากให้ Romeo ตื่นเมื่อได้ยินคำปลุก แล้วรับคำสั่งเสียงต่อได้ทันทีแบบ Siri ไม่ต้องพิมพ์หรือกดปุ่ม
ตอนนี้ OpenJarvis มีแค่ **กดแล้วพูด** (`speech/voice_io.py: record_until_silence`, `cli/_voice_chat.py`)
และ**ไม่มีระบบจับคำปลุกเลย** (grep หา wake word/hotword/porcupine/openwakeword ไม่เจอ)

ผู้ใช้เลือก:
- คำปลุก **"Hey Romeo"** (ภาษาอังกฤษ ส่วนคำสั่งหลังจากนั้นพูดภาษาไทยได้)
- ฟังจาก **ไมค์คอม Windows** และ **iPhone ผ่าน Siri**

## ผลการค้นคว้า: Siri ทำงานอย่างไร (นำมาใช้เป็นแม่แบบ)
จากบทความ Apple ML Research "Hey Siri" (2017) และ "Personalized Hey Siri" (2018):
1. **ด่าน 1 ใช้พลังงานต่ำ ฟังตลอดเวลา** — DNN เล็กมาก (5 ชั้น × 32 หน่วย) บนชิปเสริม (Always-On Processor)
   ไม่ปลุก CPU หลัก ตั้ง threshold หลวม เพื่อไม่พลาดคำปลุกจริง
2. **ด่าน 2 ตรวจซ้ำด้วยโมเดลใหญ่กว่า** — เมื่อด่าน 1 สงสัย จึงปลุก CPU หลักและรันโมเดล 5 ชั้น × 192 หน่วย
   ตัดสินด้วย threshold เข้มกว่า (ลด false trigger)
3. **ยืนยันตัวผู้พูด** — แปลงเสียงเป็น "speaker vector" เทียบกับเสียงที่ลงทะเบียนตอนตั้งค่า
   ต้องเป็นเสียงเจ้าของเครื่องเท่านั้น
4. ตรวจซ้ำอีกชั้นฝั่งเซิร์ฟเวอร์ด้วย speech recognition ตัวเต็ม ก่อนประมวลผลคำสั่ง
5. คำปลุกกับคำสั่งพูดต่อกันในประโยคเดียวได้ ("Hey Siri ตั้งปลุก 7 โมง") เพราะมีการเก็บเสียงย้อนหลังไว้ในบัฟเฟอร์

เครื่องมือ open-source ที่เหมาะกับเรา:
- **openWakeWord** — ฟรี รันบน Windows ผ่าน onnxruntime ได้ ฝึกคำปลุกใหม่จาก**เสียงสังเคราะห์ 100%**
  ไม่ต้องอัดเสียงเอง มีเครื่องมือฝึกที่ใช้ได้บน Windows/WSL2 ด้วย `openwakeword-trainer` และ HAwake
- Porcupine (Picovoice) — แม่นมาก แต่ใช้ไลเซนส์เชิงพาณิชย์ และไม่พบหลักฐานว่ารองรับภาษาไทย → ไม่ใช้
- Silero VAD — ตรวจว่ามีเสียงคนพูดหรือไม่ ใช้แทนชิปพลังงานต่ำของ Siri (กรองก่อนเพื่อประหยัด CPU)
- ยืนยันผู้พูด: **SpeechBrain ECAPA-TDNN** (`speechbrain/spkrec-ecapa-voxceleb`) สร้าง speaker embedding

## สถาปัตยกรรม (เทียบกับ Siri ทีละด่าน)
```
ไมค์ ─► ring buffer 2 วิ (เก็บเสียงย้อนหลัง)
  │
  ├─ ด่าน 0  Silero VAD ............ มีเสียงคนพูดไหม? (≈ ชิป AOP ของ Siri — ถูก, รันตลอด)
  ├─ ด่าน 1  openWakeWord "hey_romeo" ทุก 80ms, threshold 0.5 (หลวม)
  ├─ ด่าน 2  ตรวจซ้ำ: คะแนนสูงสุดในหน้าต่าง ≥ 0.7 ติดกัน ≥ 2 เฟรม
  │          + faster-whisper ถอดเสียง 1.5 วิ ต้องได้คำที่คล้าย "romeo" (≈ ด่าน 2 + เซิร์ฟเวอร์ของ Siri)
  ├─ ด่าน 3  ยืนยันผู้พูด ECAPA cosine ≥ 0.55 กับเสียงที่ลงทะเบียน (≈ Personalized Hey Siri)
  ▼
เสียงติ๊ง ► อัดคำสั่งจนเงียบ (ต่อจากบัฟเฟอร์ จึงพูดรวดเดียวได้)
  ► faster-whisper (th) ► router ► Jarvis(engine, model).ask() ► TTS พูดตอบ
  ► รอฟังคำสั่งต่อ 6 วิ โดยไม่ต้องพูดคำปลุกซ้ำ
```
- **"Romeo หยุด" / "Romeo stop"** → ใช้ `KillSwitch.engage()` ทันที โดยไม่ผ่าน LLM
- คำสั่งที่เสี่ยงยังต้องกดอนุญาตในหน้าต่างบนจอเหมือนเดิม เสียงอย่างเดียวไม่พอ (กันคนอื่นหรือเสียงจาก TV/YouTube สั่งแทน)

## iPhone ผ่าน Siri
iOS ไม่ให้แอปอื่นฟังไมค์เบื้องหลังตลอดเวลา จึงใช้ Siri เป็นด่านคำปลุกแทน:
- สร้าง Shortcut ชื่อ **"Romeo"** มีขั้นตอน: Dictate Text (ไทย) → Get Contents of URL `POST http://<คอม>:8766/ask`
  (header `X-Romeo-Token`, body `{"text": …}`) → Speak Text ผลลัพธ์
- พูด **"Hey Siri, Romeo"** → Siri ถามว่าจะสั่งอะไร → พูดคำสั่ง → คอมทำงาน → iPhone พูดตอบ
- ฝั่งคอมเปิด endpoint `/ask` (มี token, ฟังเฉพาะ LAN/Tailscale) ใน daemon ตัวเดียวกับที่ฟังไมค์ ใช้ pipeline เดียวกันตั้งแต่ router เป็นต้นไป

## ไฟล์ที่จะเพิ่ม/แก้ใน repo romeo
```
src/romeo/voice/
├── __init__.py
├── audio.py        # MicStream (sounddevice 16kHz mono, เฟรม 80ms) + RingBuffer
├── vad.py          # Silero VAD (onnx) — is_speech(frame)
├── wakeword.py     # WakeDetector: openWakeWord ด่าน 1 + ด่าน 2 (ยืนยันด้วยคะแนน + whisper)
├── speaker.py      # SpeakerVerifier: enroll(), verify() ด้วย ECAPA; เก็บ ~/.romeo/voice/owner.npy
├── assistant.py    # VoiceAssistant: state machine IDLE→AWAKE→LISTENING→THINKING→SPEAKING→FOLLOW_UP
├── runner.py       # handle_text(text) → router → Jarvis(engine_key, model).ask() (ใช้ร่วมกับ /ask)
├── ask_server.py   # HTTP /ask สำหรับ Siri Shortcut (token, ใช้รูปแบบเดียวกับ shortcuts_bridge.py)
└── sounds/         # wake.wav, done.wav
models/README.md    # วิธีฝึก hey_romeo.onnx ด้วย openwakeword-trainer + ที่วางไฟล์
shortcuts/README.md # + หัวข้อ "Hey Siri, Romeo"
src/romeo/cli.py    # + romeo listen | romeo voice enroll | romeo voice test
pyproject.toml      # + extra [voice]: openwakeword, onnxruntime, sounddevice, numpy, speechbrain
tests/test_voice.py
```

ของเดิมที่ใช้ซ้ำ:
- `openjarvis.speech._discovery.get_speech_backend(config)` → STT (faster-whisper, ส่ง `language="th"`)
- `openjarvis.speech._tts_discovery.get_tts_backend` + `voice_io.play_wav` → พูดตอบ
- `openjarvis.speech.voice_io._rms` / แนวคิดของ `record_until_silence` → ตรวจว่าเงียบแล้ว
  (เขียนตัวอัดใหม่ที่อ่านจาก ring buffer ไม่ได้เปิดไมค์ใหม่ เพื่อไม่ให้เสียงที่พูดต่อจากคำปลุกหาย)
- `openjarvis.sdk.Jarvis(engine_key=…, model=…).ask(text, agent="native_react")` — **ทำให้ router
  เลือกโมเดลให้อัตโนมัติได้แล้ว** (ปิดงานค้าง M7 "auto-routing")
- `romeo.agent.router.route`, `romeo.common.safety.KillSwitch`, `romeo.common.audit.record`
- รูปแบบ HTTP + token จาก `romeo/iphone_mcp/shortcuts_bridge.py`

## ขั้นตอนการทำ
1. **V1 วงจรพื้นฐาน** — audio + VAD + openWakeWord โมเดลสำเร็จรูป `hey_jarvis` (ทดสอบได้ทันที) → ติ๊ง → STT → ask → TTS
2. **V2 ฝึก "hey_romeo"** — ใช้ openwakeword-trainer (Piper TTS สร้างตัวอย่างเสียงสังเคราะห์ ~5,000 ตัวอย่าง,
   negative phrases เช่น "hey Siri", "โรงหนัง", "romance") บน Colab หรือ WSL2 แล้ววาง `models/hey_romeo.onnx`
   ระบุ path ได้ด้วย `ROMEO_WAKE_MODEL`
3. **V3 ด่าน 2 + ยืนยันผู้พูด** — `romeo voice enroll` (พูด "Hey Romeo" 5 ครั้ง) และการตรวจด้วย whisper
4. **V4 Siri bridge** — `/ask` + Shortcut "Romeo" + คู่มือ
5. **V5 ปรับจูน** — `romeo voice test` แสดงคะแนนสด, log trigger ทุกครั้ง (รวมครั้งที่ถูกปฏิเสธ) ใน audit,
   ปรับ threshold ผ่าน env (`ROMEO_WAKE_THRESHOLD`, `ROMEO_SPEAKER_THRESHOLD`); เป้าหมาย false trigger ≤ 1 ครั้ง/วัน
6. รันเป็น background ตอน login (Task Scheduler) และเพิ่มไอคอน tray เพื่อปิดเสียง/ปิดไมค์

## Verification
- `uv run pytest` — ทดสอบ state machine ด้วยเฟรมเสียงปลอม, ring buffer, คำสั่ง "Romeo หยุด" ต้องเปิด kill switch,
  `/ask` ต้องปฏิเสธเมื่อ token ผิด, speaker verify ทั้งกรณีผ่านและไม่ผ่าน (ใช้ embedding ปลอม)
- ทดสอบออฟไลน์: ส่งไฟล์ WAV ที่มี "hey jarvis/hey romeo" กับไฟล์ที่ไม่มี เข้าไปใน `WakeDetector` → ต้องจับได้/ไม่จับ
- บน Windows จริง: `romeo voice test` (ดูคะแนน) → `romeo listen` → พูด "Hey Romeo เปิด Notepad" ต้องเห็น Notepad เปิด
  และได้ยินเสียงตอบ; เปิด YouTube ทิ้งไว้ 1 ชม. แล้วนับ false trigger
- iPhone: "Hey Siri, Romeo" → "ตอนนี้เปิดหน้าต่างอะไรอยู่" → iPhone อ่านรายการหน้าต่างให้ฟัง
- หมายเหตุ: cloud container นี้ไม่มีไมค์ ทดสอบได้แค่ unit test และการป้อนไฟล์ WAV

## ความเสี่ยงที่ต้องบอกผู้ใช้
- โมเดลที่ฝึกจากเสียงสังเคราะห์อาจจับสำเนียงไทยพูดคำอังกฤษได้ไม่ดีนัก → ใน V5 เพิ่มเสียงจริงของผู้ใช้ ~50 คลิป
  มาฝึกเสริม
- ยืนยันผู้พูดยังโดนเสียงอัดหลอกได้ → จึงยังต้องให้กดอนุญาตบนจอสำหรับ action เสี่ยง
- ข้อมูลฝึกบางชุดของ openWakeWord (ACAV100M) เป็นไลเซนส์ non-commercial → ใช้ส่วนตัวได้ ถ้าจะขายต้องฝึกด้วยชุดข้อมูลอื่น

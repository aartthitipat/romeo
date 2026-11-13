# ฝึกคำปลุก "Hey Romeo"

ก่อนจะมีโมเดล `hey_romeo` ของเราเอง Romeo จะใช้ **"Hey Jarvis"** ที่ openWakeWord มีให้อยู่แล้ว
จึงลองระบบได้ทันที (`romeo voice test` แล้วพูด "Hey Jarvis")

## วิธีฝึก (ใช้เสียงสังเคราะห์ ไม่ต้องอัดเสียงเอง)
openWakeWord ฝึกโมเดลจาก**เสียงสังเคราะห์ 100%** (Piper TTS สร้างคำว่า "hey romeo" หลายพันแบบ
แล้วผสมกับเสียงรบกวน) ต้องใช้ GPU NVIDIA หรือ Google Colab

เลือกทางใดทางหนึ่ง:
1. **Google Colab (ง่ายสุด)** — notebook "automatic model training" ใน repo
   [dscripka/openWakeWord](https://github.com/dscripka/openWakeWord) (โฟลเดอร์ `notebooks/`)
2. **บนเครื่อง (Windows + WSL2 + GPU)** — [openwakeword-trainer](https://github.com/lgpearson1771/openwakeword-trainer)
   หรือ [HAwake WakeWord Training](https://github.com/IT-BAER/hawake-wakeword) (มี PowerShell + หน้าเว็บ)

ค่าที่แนะนำ:

| ค่า | แนะนำ |
|---|---|
| target phrase | `hey romeo` |
| จำนวนตัวอย่าง | 5,000 ขึ้นไป |
| training steps | 5,000–10,000 |
| negative phrases (คำที่ห้ามติด) | `hey siri`, `hey google`, `romance`, `remote`, `hey ramen`, `โรงหนัง`, `โรงเรียน`, `เฮ้ย` |
| export | `.onnx` |

## ติดตั้งโมเดล
วางไฟล์ไว้ที่ `%USERPROFILE%\.romeo\voice\hey_romeo.onnx` แล้ว Romeo จะใช้ให้อัตโนมัติ
หรือระบุ path เองด้วย:
```powershell
setx ROMEO_WAKE_MODEL "D:\models\hey_romeo.onnx"
```

## ปรับจูน
```powershell
romeo voice test
```
พูด "Hey Romeo" หลาย ๆ แบบ ดูคะแนนที่ขึ้น แล้วปรับค่า:

| ตัวแปร | ค่าเริ่มต้น | ผล |
|---|---|---|
| `ROMEO_WAKE_CANDIDATE` | 0.5 | ด่าน 1: ต่ำ = ไม่ค่อยพลาด |
| `ROMEO_WAKE_THRESHOLD` | 0.7 | ด่าน 2: สูง = ติดผิดน้อยลง |
| `ROMEO_WAKE_VERIFY_STT` | 1 | ใช้ whisper ยืนยันว่าได้ยินคำว่า romeo จริง (ตั้งเป็น 0 เพื่อปิด) |
| `ROMEO_SPEAKER_THRESHOLD` | 0.55 | ด่าน 3: ความเหมือนเสียงเจ้าของที่ยอมรับ |
| `ROMEO_VAD_THRESHOLD` | 0.5 | ความมั่นใจว่าเป็นเสียงคน |

ทุกครั้งที่ปลุกติด (รวมทั้งที่ถูกปฏิเสธ) จะถูกบันทึกใน `romeo audit` พร้อมเหตุผล
ถ้าสำเนียงไทยพูดคำอังกฤษแล้วติดยาก ให้อัดเสียงตัวเองพูด "Hey Romeo" ~50 คลิปเพิ่มเข้าไปในชุดฝึก

> ข้อมูลฝึกเสียงรบกวนบางชุดของ openWakeWord (ACAV100M) เป็นไลเซนส์ non-commercial
> โมเดลที่ได้จึงใช้ส่วนตัวได้ แต่ถ้าจะนำไปขายต้องฝึกด้วยชุดข้อมูลอื่น

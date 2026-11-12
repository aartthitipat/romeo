# Romeo — AI ที่คุมคอม Windows และ iPhone ได้

Romeo ต่อยอดจาก [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) โดยเพิ่ม **MCP server 2 ตัว**
ที่ให้ AI มองเห็นและสั่งงานเครื่องได้ แล้วใช้สมองของ OpenJarvis (agent, memory, channels, เสียง)
คุมทั้งหมด ไม่ต้องแก้โค้ด OpenJarvis เลย — แผนเต็มอยู่ที่ [docs/PLAN.md](docs/PLAN.md)

```
 iPhone / LINE / Telegram / เสียง / jarvis gui
                    │
        OpenJarvis (บนคอม Windows) — Ollama ⇄ Claude
                    │ MCP
        ┌───────────┴───────────┐
  romeo-windows            romeo-iphone
  (UI Automation,          (Shortcuts bridge +
   เมาส์/คีย์บอร์ด,          WebDriverAgent)
   PowerShell)
```

## สถานะ

| Milestone | สถานะ |
|---|---|
| M0 โครงโปรเจกต์ + ความปลอดภัย (safety gate, approval, audit, kill switch) | ✅ |
| M1–M2 romeo-windows (ดูจอ, UI tree, คลิก, พิมพ์ไทย, เปิดแอป, PowerShell) | ✅ เขียนแล้ว — ต้องทดสอบบน Windows จริง |
| M3 hybrid router + operator prompt | ✅ router + prompt (เลือก engine เองผ่าน `romeo route`) |
| M4 iPhone ระดับ A — Shortcuts bridge | ✅ ฝั่งเซิร์ฟเวอร์ — ต้องสร้าง Shortcut บน iPhone ([คู่มือ](shortcuts/README.md)) |
| M5 iPhone ระดับ B — WebDriverAgent | ✅ client — ต้องติดตั้ง WDA ลง iPhone |
| M6 สั่งผ่าน LINE/Telegram/เสียง | ใช้ channels ของ OpenJarvis (ตั้งค่าใน config) |
| V1–V4 ปลุกด้วยเสียง "Hey Romeo" (VAD → wake word 2 ด่าน → whisper ยืนยัน → เสียงเจ้าของ) + "Hey Siri, Romeo" | ✅ เขียนแล้ว — ต้องทดสอบกับไมค์จริง ([แผน](docs/VOICE_PLAN.md)) |
| ฝึกโมเดล `hey_romeo` | ต้องทำเอง ([คู่มือ](models/README.md)) — ระหว่างนี้ใช้ "Hey Jarvis" |
| auto-routing (เลือก Ollama/Claude ให้เอง) | ✅ สำหรับคำสั่งเสียงและ Siri |
| M7 รันเป็น service ตอนเปิดเครื่อง + ไอคอน tray | ยังไม่ทำ |

## ติดตั้ง (บน Windows)

1. ติดตั้ง OpenJarvis + Ollama:
   ```powershell
   irm https://open-jarvis.github.io/OpenJarvis/install.ps1 | iex
   ```
   ```powershell
   ollama pull qwen3:8b
   ```
2. ติดตั้ง Romeo:
   ```powershell
   git clone https://github.com/aartthitipat/romeo; cd romeo
   ```
   ```powershell
   uv pip install -e ".[iphone,jarvis]"
   ```
3. ติดตั้ง prompt และรายชื่อ MCP server ให้ OpenJarvis:
   ```powershell
   romeo setup
   ```
   จากนั้นรวม `configs/config.toml` เข้ากับ `%USERPROFILE%\.openjarvis\config.toml`
4. ใส่ API key ของ Claude (สำหรับงานคุมหน้าจอ) ใน environment หรือ `~/.openjarvis/credentials.toml`:
   ```powershell
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
5. ลองใช้:
   ```powershell
   jarvis ask "ตอนนี้เปิดหน้าต่างอะไรอยู่บ้าง"
   ```
   ```powershell
   jarvis ask --engine cloud --model claude-sonnet-5-5 "เปิด Notepad แล้วพิมพ์ว่า สวัสดีครับ"
   ```

iPhone: ดู [shortcuts/README.md](shortcuts/README.md)

## สั่งด้วยเสียง — "Hey Romeo"

ออกแบบตาม "Hey Siri" ของ Apple: ฟังตลอดด้วยด่านเล็กที่ถูก แล้วยืนยันซ้ำด้วยด่านที่แม่นกว่า

```
ไมค์ → ด่าน 0 VAD (มีเสียงคนไหม) → ด่าน 1 openWakeWord (คะแนน ≥ 0.5)
     → ด่าน 2 ยืนยันหลายเฟรม (≥ 0.7) + whisper ต้องได้ยินคำว่า "romeo"
     → ด่าน 3 ต้องเป็นเสียงเจ้าของ (ถ้าลงทะเบียนเสียงแล้ว)
     → ติ๊ง! → พูดคำสั่งต่อได้เลย → Romeo ทำงาน → พูดตอบ → ฟังคำสั่งต่อ 6 วิโดยไม่ต้องปลุกซ้ำ
```

1. ติดตั้งส่วนเสียง และ STT ภาษาไทย:
   ```powershell
   uv pip install -e ".[voice,speaker]" faster-whisper
   ```
2. ลงทะเบียนเสียงตัวเอง (พูดคำปลุก 5 ครั้ง) — ให้คนอื่นหรือเสียงจาก TV ปลุกไม่ได้:
   ```powershell
   romeo voice enroll
   ```
3. ดูคะแนนคำปลุกแบบสด:
   ```powershell
   romeo voice test
   ```
4. เริ่มฟัง:
   ```powershell
   romeo listen
   ```
5. ให้เริ่มเองตอน login:
   ```powershell
   schtasks /create /tn Romeo /sc onlogon /tr "romeo listen" /rl limited
   ```

- ยังไม่มีโมเดล `hey_romeo` ให้พูด **"Hey Jarvis"** ไปก่อน — วิธีฝึกอยู่ที่ [models/README.md](models/README.md)
- พูด **"Hey Romeo หยุด"** = หยุดฉุกเฉิน (ไม่ผ่าน AI) · "หยุดเพลง" ยังเป็นคำสั่งปกติ
- งานเสี่ยงยังต้องกดอนุญาตบนจอเสมอ เสียงอย่างเดียวไม่พอ

## ความปลอดภัย

Romeo คุมเครื่องได้จริง จึงมีด่านกั้นทุก action (`src/romeo/common/`):

- **อ่าน** (screenshot, UI tree) → ทำได้เลย
- **สั่งงานทั่วไป** (คลิก, พิมพ์, เปิดแอป) → ทำได้ และบันทึก log
- **เสี่ยง** (PowerShell, ปิดหน้าต่าง, ปิดเครื่อง, ส่งข้อความ, โทร) → **เด้งหน้าต่างถามบนจอทุกครั้ง** ไม่ตอบใน 60 วิ = ไม่อนุญาต
- **ห้ามเด็ดขาด**: แอปธนาคาร/กระเป๋าเงิน/password manager และการพิมพ์รหัสผ่าน/OTP
- **ปุ่มหยุดฉุกเฉิน**: `Ctrl+Alt+Esc` หรือ `romeo stop` (ปลดด้วย `romeo resume`) · ลากเมาส์ไปมุมจอก็หยุดได้
- ดู log ทุก action: `romeo audit`

## คำสั่ง `romeo`

| คำสั่ง | ทำอะไร |
|---|---|
| `romeo setup` | ติดตั้ง operator prompt + รายชื่อ MCP server ให้ OpenJarvis |
| `romeo route "<คำขอ>"` | ดูว่าคำขอนี้ควรใช้ local model หรือ Claude |
| `romeo stop` / `romeo resume` | เปิด/ปิด kill switch |
| `romeo audit -n 50` | ดู log ล่าสุด |
| `romeo listen [--no-mic]` | ฟัง "Hey Romeo" + เปิด endpoint ให้ Siri |
| `romeo voice enroll` / `romeo voice test` | ลงทะเบียนเสียงเจ้าของ / ดูคะแนนคำปลุกสด |
| `romeo-windows` / `romeo-iphone` | MCP server (OpenJarvis เรียกเอง; ใช้กับ Claude Desktop ได้ด้วย) |

## พัฒนา

```bash
uv venv && uv pip install -e ".[dev]"
```
```bash
uv run pytest
```

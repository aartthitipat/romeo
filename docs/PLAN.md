# แผนงาน Romeo — AI คุมคอม Windows + iPhone (ต่อยอด OpenJarvis)

## Context
ผู้ใช้ต้องการผู้ช่วย AI ที่สั่งงานคอมพิวเตอร์และโทรศัพท์ได้ทั้งเครื่อง โดยใช้ OpenJarvis (github.com/open-jarvis/openjarvis) เป็นฐาน
repo `aartthitipat/romeo` ตอนนี้ว่างเปล่า (ยังไม่มี commit) ทำงานบน branch `claude/wizardly-archimedes-jpvpgn`

การตัดสินใจที่ได้จากผู้ใช้:
- **ต่อยอด OpenJarvis** (ใช้เป็น dependency ไม่ fork)
- อุปกรณ์เป้าหมาย: **Windows** และ **iPhone**
- สมอง AI: **Hybrid** — Ollama (local) งานทั่วไป + Claude API สำหรับงานที่ต้องดูหน้าจอ/วางแผนยาก

สิ่งที่ OpenJarvis มีให้แล้ว (ไม่ต้องเขียนใหม่):
- `ToolRegistry` + `BaseTool`/`ToolSpec` (`src/openjarvis/tools/_stubs.py`) มีฟิลด์ `requires_confirmation`, `required_capabilities`
- MCP client + `MCPToolAdapter` (`src/openjarvis/tools/mcp_adapter.py`) ตั้งค่าผ่าน `[tools.mcp] servers = "<json หรือ path>"` (`core/config.py: resolve_mcp_servers`)
- เอเจนต์ `orchestrator`, `native_react`, `operative` (`src/openjarvis/agents/`)
- engine หลายตัวรวม `multi.py`, `ollama.py`, `cloud.py` → ทำ hybrid routing ได้
- ระบบความปลอดภัย: `security/capabilities.py` (RBAC), `tools/approval_store.py` (tier trivial/low/…, จำการอนุญาต), `security/audit.py`
- channels: `telegram.py`, `line_channel.py`, `webchat.py` → สั่งงานจากมือถือได้
- speech: `faster_whisper.py`, `kokoro_tts.py`, `voice_io.py` → สั่งด้วยเสียง

## สถาปัตยกรรม
```
 [iPhone / LINE / Telegram / เสียง / jarvis gui]
                    │ คำสั่ง
                    ▼
        OpenJarvis (รันบนคอม Windows)
        agent: romeo_operator  ── engine hybrid (Ollama ⇄ Claude)
                    │ MCP (stdio)
        ┌───────────┴────────────┐
        ▼                        ▼
  romeo-windows MCP        romeo-iphone MCP
  (pywinauto/UIA, mss,     (WebDriverAgent ผ่าน pymobiledevice3
   pyautogui, PowerShell)   + Shortcuts bridge)
        │                        │ USB / Wi-Fi
        ▼                        ▼
     Windows PC                 iPhone
```
เหตุผลที่ใช้ MCP server แยก: ไม่ต้องแก้โค้ด OpenJarvis, อัปเดต OpenJarvis ได้อิสระ, และ MCP server เดียวกันนำไปใช้กับ Claude Desktop/Claude Code ได้ด้วย

## ข้อจำกัดสำคัญของ iPhone (ต้องรู้ก่อนเริ่ม)
iOS ไม่อนุญาตให้แอปคุมเครื่องแบบ ADB ของ Android จึงใช้ 2 ระดับ:
1. **ระดับ A – Shortcuts bridge (ไม่ต้องมี Mac):** iPhone รัน Shortcut automation ที่ poll/รับ webhook จาก romeo แล้วทำ action ของ Shortcuts (ส่งข้อความ, โทร, เปิดแอป, ตั้งปลุก, เพลง, HomeKit, อ่านโน้ต/ปฏิทิน) — ทำได้เฉพาะสิ่งที่ Shortcuts รองรับ
2. **ระดับ B – คุมหน้าจอเต็ม (tap/swipe/พิมพ์/screenshot):** ติดตั้ง **WebDriverAgent (WDA)** ลง iPhone แล้วคุมจาก Windows ด้วย `pymobiledevice3` (รองรับ Windows, ต้องมี Apple Mobile Device driver จาก iTunes) เปิด WDA + forward port 8100
   - ต้อง build/sign WDA **ครั้งแรกบน Mac** (หรือ cloud Mac) หรือ sideload IPA ที่ build แล้วด้วย Apple ID
   - Apple ID ฟรี: ต้อง re-sign ทุก 7 วัน / Developer account ($99/ปี): 1 ปี
   - ต้องเปิด Developer Mode บน iPhone
→ เริ่มจากระดับ A ก่อน แล้วค่อยเพิ่มระดับ B

## โครงสร้าง repo `romeo`
```
romeo/
├── pyproject.toml            # uv; deps: openjarvis, mcp, pywinauto, mss, pyautogui, pymobiledevice3, httpx, pillow
├── README.md                 # วิธีติดตั้ง (ภาษาไทย)
├── configs/
│   ├── config.toml           # preset ของ OpenJarvis: engine hybrid, agent, [tools.mcp]
│   └── mcp_servers.json      # ลงทะเบียน romeo-windows / romeo-iphone
├── src/romeo/
│   ├── common/
│   │   ├── safety.py         # ระดับความเสี่ยง + allow/deny list + kill switch (hotkey Ctrl+Alt+Esc)
│   │   ├── approval.py       # ขออนุญาตผู้ใช้ (ใช้ ApprovalStore ของ OpenJarvis)
│   │   └── audit.py          # log ทุก action + screenshot ก่อน/หลัง
│   ├── windows_mcp/
│   │   ├── server.py         # MCP server (FastMCP)
│   │   ├── screen.py         # screenshot (mss), ย่อภาพ, ใส่ grid พิกัด
│   │   ├── uia.py            # อ่าน UI tree/ค้นหา element ด้วย pywinauto (UIA backend)
│   │   ├── input.py          # คลิก/พิมพ์/คีย์ลัด/scroll (pyautogui + SendInput, รองรับภาษาไทยผ่าน clipboard)
│   │   ├── apps.py           # เปิด/ปิด/สลับหน้าต่าง, จัดการ process
│   │   └── system.py         # PowerShell (sandboxed), ไฟล์, เสียง, ความสว่าง, ปิดเครื่อง
│   ├── iphone_mcp/
│   │   ├── server.py
│   │   ├── shortcuts_bridge.py   # คิวคำสั่ง HTTP ให้ Shortcut มารับ (ระดับ A)
│   │   ├── wda_client.py         # เรียก WDA HTTP API: /screenshot, /source, tap, swipe, type (ระดับ B)
│   │   └── device.py             # pymobiledevice3: list device, start WDA, port-forward, ข้อมูลแบต
│   └── agent/
│       ├── operator.py       # agent "romeo_operator" ลงทะเบียนกับ AgentRegistry ของ OpenJarvis
│       ├── router.py         # เลือก engine: งานข้อความ→Ollama, งานดูภาพ/หลายขั้น→Claude
│       └── prompts/operator.md
├── shortcuts/                # คู่มือ + ไฟล์ .shortcut สำหรับติดตั้งบน iPhone
└── tests/                    # pytest: mock pywinauto/WDA, ทดสอบ safety & router
```

## เครื่องมือ (MCP tools) ที่จะมี
**Windows:** `screenshot`, `get_ui_tree`, `find_element`, `click`, `double_click`, `type_text`, `hotkey`, `scroll`, `open_app`, `focus_window`, `list_windows`, `run_powershell`*, `file_ops`*, `system_control`* (* = ต้องขออนุญาต)
**iPhone:** `iphone_screenshot`, `iphone_ui_tree`, `iphone_tap`, `iphone_swipe`, `iphone_type`, `iphone_home`, `iphone_open_app`, `iphone_shortcut_run`, `iphone_send_message`*, `iphone_call`*, `iphone_device_info`

## Loop การคุมเครื่อง (agent)
1. รับคำสั่ง → router วางแผน (Claude สำหรับงานซับซ้อน)
2. **observe**: ดึง UI tree ก่อน (ถูก/เร็ว) ถ้าไม่พอค่อยใช้ screenshot + vision
3. **act**: เรียก tool ทีละขั้น ผ่าน safety gate
4. **verify**: screenshot/tree ใหม่เพื่อตรวจว่าสำเร็จ; ใช้ `loop_guard.py` ของ OpenJarvis กันวนไม่จบ
5. รายงานผลกลับช่องทางที่สั่งมา (LINE/Telegram/เสียง)
- ตรวจสอบ API/เวอร์ชันของ computer-use tool ของ Claude และ model ID ล่าสุดตอนเริ่ม implement (ผ่าน skill `claude-api`)

## ความปลอดภัย (สำคัญมากเพราะคุมเครื่องได้ทั้งหมด)
- ระดับความเสี่ยง: `read` (อัตโนมัติ) / `act` (อัตโนมัติ แต่ log) / `sensitive` (ขออนุญาตทุกครั้ง: ลบไฟล์, PowerShell, ส่งข้อความ, โทร, จ่ายเงิน, ติดตั้งโปรแกรม, ปิดเครื่อง)
- ปฏิเสธเสมอ: ใส่รหัสผ่าน/OTP, แอปธนาคาร (deny list ตามชื่อแอป/หน้าต่าง)
- Kill switch: hotkey บน Windows + คำสั่ง "หยุด" จากทุก channel
- ใช้ `injection_scanner.py` ของ OpenJarvis สแกนข้อความบนหน้าจอ/เว็บก่อนส่งให้ LLM (กันหน้าเว็บสั่ง AI)
- API key เก็บใน `credentials.toml` ของ OpenJarvis ไม่ commit; MCP server ฟังแค่ localhost; Shortcuts bridge ใช้ token + LAN/Tailscale เท่านั้น
- audit log ทุก action

## ลำดับการทำ (Milestones)
1. **M0 โครงโปรเจกต์**: pyproject, README, config preset, ติดตั้ง OpenJarvis + Ollama บน Windows, `jarvis doctor` ผ่าน
2. **M1 Windows MCP (อ่านอย่างเดียว)**: screenshot, ui_tree, list_windows → ต่อเข้า OpenJarvis แล้วถาม "ตอนนี้เปิดอะไรอยู่"
3. **M2 Windows MCP (สั่งงาน) + safety/approval**: click/type/hotkey/open_app/powershell
4. **M3 agent romeo_operator + hybrid router**: งานหลายขั้น เช่น "เปิด Chrome หาราคาทองแล้วจดลง Notepad"
5. **M4 iPhone ระดับ A (Shortcuts bridge)**: ส่งข้อความ/ตั้งปลุก/เปิดแอปจากคอม
6. **M5 iPhone ระดับ B (WDA)**: ติดตั้ง WDA, pymobiledevice3 บน Windows, tap/swipe/screenshot
7. **M6 ช่องทางสั่งงาน**: LINE/Telegram + เสียง (whisper ภาษาไทย + TTS)
8. **M7 ความเสถียร**: รันเป็น Windows service (`deploy/windows` ของ OpenJarvis), test, เอกสาร

## Verification
- `uv run pytest tests/` — unit test ของ safety, router, tool schema (mock pywinauto/WDA)
- ทดสอบ MCP แยก: `npx @modelcontextprotocol/inspector uv run romeo-windows` แล้วเรียก `screenshot`/`list_windows`
- ทดสอบผ่าน OpenJarvis: `jarvis init` ด้วย `configs/config.toml` → `jarvis ask "เปิด Notepad แล้วพิมพ์ สวัสดี"` ต้องเห็นผลบนจอและเห็น prompt ขออนุญาตสำหรับ action เสี่ยง
- iPhone: `pymobiledevice3 usbmux list` เห็นเครื่อง → `iphone_screenshot` ได้ภาพ → `iphone_tap` เปิดแอปได้
- ทดสอบ kill switch และ deny list (สั่งเปิดแอปธนาคารต้องถูกปฏิเสธ)
- หมายเหตุ: การทดสอบ GUI จริงต้องทำบนเครื่อง Windows/iPhone ของผู้ใช้ — cloud container นี้เป็น Linux ทำได้แค่ unit test

## สิ่งที่จะ commit ในรอบแรก (หลังอนุมัติแผน)
M0 + โครงไฟล์ทั้งหมด + เอกสารแผนนี้เป็น `docs/PLAN.md` (ภาษาไทย) → commit และ push ไป `claude/wizardly-archimedes-jpvpgn`

# ต่อ iPhone กับ Romeo

iOS ไม่ยอมให้โปรแกรมภายนอกคุมเครื่องแบบเต็ม ๆ เหมือน Android จึงมี 2 ระดับ ใช้คู่กันได้

| | ระดับ A — Shortcuts bridge | ระดับ B — WebDriverAgent |
|---|---|---|
| ทำอะไรได้ | ส่งข้อความ, โทร, เปิดแอป/URL, ตั้งปลุก, เพลง, HomeKit, คลิปบอร์ด, แบต, ตำแหน่ง | เห็นจอ, แตะ, ปัด, พิมพ์ — ทำได้ทุกอย่างที่นิ้วทำได้ |
| ต้องมี Mac | ไม่ต้อง | ต้องใช้ Mac (หรือ cloud Mac) build/sign ครั้งแรก |
| การเชื่อมต่อ | Wi-Fi เดียวกัน หรือ Tailscale | สาย USB (หรือ Wi-Fi หลังจับคู่) |

---

## ระดับ A — Shortcuts bridge

### 1) เปิด bridge บนคอม
ตั้ง token สุ่มยาว ๆ (อย่างน้อย 16 ตัว) แล้วเปิด OpenJarvis ใหม่:
```powershell
setx ROMEO_BRIDGE_TOKEN "เปลี่ยนเป็นข้อความสุ่มยาวๆ-อย่างน้อย16ตัว"
```
bridge จะฟังที่พอร์ต `8765` (เปลี่ยนด้วย `ROMEO_BRIDGE_PORT`) — อนุญาตพอร์ตนี้ใน Windows Firewall
**เฉพาะเครือข่าย Private** และแนะนำให้ใช้ [Tailscale](https://tailscale.com) แทนการเปิดออกอินเทอร์เน็ต

### 2) สร้าง Shortcut ชื่อ "Romeo Listener" บน iPhone
1. **Repeat** 1000 ครั้ง
   1. **Get Contents of URL** `http://<IP คอม>:8765/next` · Method GET · Header `X-Romeo-Token` = token
   2. **If** ผลลัพธ์ *has any value*
      1. **Get Dictionary Value** `action` → ตัวแปร `Action`
      2. **If** `Action` is `send_message` → **Send Message** (`text` ถึง `to`)
      3. **If** `Action` is `call` → **Call** (`number`)
      4. **If** `Action` is `open_app` → **Open App** (เลือกจาก `app`) หรือ **Open URLs** สำหรับ URL scheme
      5. **If** `Action` is `set_alarm` → **Create Alarm** (`time`, `label`)
      6. **If** `Action` is `notify` → **Show Notification** (`text`)
      7. …เพิ่ม action อื่นตามตารางใน `src/romeo/iphone_mcp/shortcuts_bridge.py`
      8. **Get Contents of URL** `http://<IP คอม>:8765/result` · Method POST · Header เดิม ·
         JSON body `{"id": <id>, "ok": true, "output": <ผลลัพธ์>}`
   3. **Otherwise** → **Wait** 2 วินาที
2. รัน Shortcut นี้ค้างไว้ (iOS จะหยุดเมื่อจอล็อกนาน) — ถ้าต้องการรันเบื้องหลังตลอด ใช้แอปอย่าง
   Pushcut (Automation Server) ให้รัน Shortcut แทน

### 3) ทดสอบ
```powershell
jarvis ask --engine cloud --model claude-sonnet-5-5 "แจ้งเตือนบนไอโฟนว่า ทดสอบ Romeo"
```

---

## ระดับ B — WebDriverAgent (คุมหน้าจอเต็ม)

### 1) ติดตั้ง WDA ลง iPhone (ครั้งเดียว ต้องมี Mac)
```bash
git clone https://github.com/appium/WebDriverAgent && cd WebDriverAgent
```
เปิด `WebDriverAgent.xcodeproj` ใน Xcode → target **WebDriverAgentRunner** → Signing เลือก Apple ID ของคุณ
→ เปลี่ยน Bundle ID ให้ไม่ซ้ำ → Product ▸ Test ลง iPhone ที่เสียบสาย

- Apple ID ฟรี: ใบรับรองหมดอายุทุก **7 วัน** ต้องทำซ้ำ · Apple Developer ($99/ปี): อยู่ได้ 1 ปี
- iPhone: เปิด **Settings ▸ Privacy & Security ▸ Developer Mode** และ trust developer ใน **General ▸ VPN & Device Management**

### 2) เตรียม Windows
1. ติดตั้ง **Apple Devices** (Microsoft Store) หรือ iTunes เพื่อให้มีไดรเวอร์ USB
2. เสียบ iPhone กด Trust แล้วตรวจ:
   ```powershell
   pymobiledevice3 usbmux list
   ```
3. iOS 17 ขึ้นไป: เปิด PowerShell **แบบ Administrator** ค้างไว้:
   ```powershell
   pymobiledevice3 remote tunneld
   ```
4. เปิด WDA และ forward พอร์ต (ถ้า bundle id ไม่ใช่ค่าเริ่มต้น ให้ตั้ง `ROMEO_WDA_BUNDLE`):
   ```powershell
   pymobiledevice3 developer dvt xcuitest com.facebook.WebDriverAgentRunner.xctrunner
   ```
   ```powershell
   pymobiledevice3 usbmux forward 8100 8100
   ```
5. ตรวจว่าใช้ได้:
   ```powershell
   curl http://127.0.0.1:8100/status
   ```

### 3) ทดสอบ
```powershell
jarvis ask --engine cloud --model claude-sonnet-5-5 "เปิดแอปการตั้งค่าบนไอโฟนแล้วบอกว่าเวอร์ชัน iOS อะไร"
```

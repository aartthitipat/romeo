"""Minimal WebDriverAgent HTTP client (level B: full screen control).

WDA runs on the iPhone; `pymobiledevice3 usbmux forward 8100 8100` exposes it
on http://127.0.0.1:8100 of the Windows PC.
"""

from __future__ import annotations

import base64
import os
from typing import Any, Optional

import httpx


class WDAError(RuntimeError):
    pass


class WDAClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or os.environ.get("ROMEO_WDA_URL", "http://127.0.0.1:8100")).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._sid: Optional[str] = None

    # -------------------------------------------------------------- basics --
    def _req(self, method: str, path: str, json: Any = None) -> Any:
        try:
            resp = self._http.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise WDAError(
                f"cannot reach WebDriverAgent at {self.base_url} ({exc}). "
                "Is WDA running and port 8100 forwarded? See shortcuts/README.md"
            ) from exc
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise WDAError(f"{method} {path} -> {resp.status_code}: {data}")
        return data.get("value", data)

    def status(self) -> Any:
        return self._req("GET", "/status")

    @property
    def sid(self) -> str:
        if self._sid is None:
            value = self._req("POST", "/session", json={"capabilities": {}})
            self._sid = value.get("sessionId") if isinstance(value, dict) else None
            if not self._sid:
                raise WDAError(f"could not create WDA session: {value}")
        return self._sid

    def _s(self, method: str, path: str, json: Any = None) -> Any:
        try:
            return self._req(method, f"/session/{self.sid}{path}", json)
        except WDAError as exc:
            if "invalid session" in str(exc).lower():
                self._sid = None
                return self._req(method, f"/session/{self.sid}{path}", json)
            raise

    # ------------------------------------------------------------- observe --
    def screenshot_png(self) -> bytes:
        return base64.b64decode(self._req("GET", "/screenshot"))

    def window_size(self) -> dict[str, int]:
        return self._s("GET", "/window/size")

    def source(self) -> str:
        return self._req("GET", "/source?format=description")

    def active_app(self) -> dict[str, Any]:
        return self._req("GET", "/wda/activeAppInfo")

    # ----------------------------------------------------------------- act --
    def tap(self, x: float, y: float) -> None:
        self._s("POST", "/wda/tap", json={"x": x, "y": y})

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.3) -> None:
        self._s("POST", "/wda/dragfromtoforduration",
                json={"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": duration})

    def type_text(self, text: str) -> None:
        self._s("POST", "/wda/keys", json={"value": list(text)})

    def home(self) -> None:
        self._req("POST", "/wda/homescreen")

    def launch(self, bundle_id: str) -> None:
        self._s("POST", "/wda/apps/launch", json={"bundleId": bundle_id})

    def lock(self) -> None:
        self._req("POST", "/wda/lock")

    def unlock(self) -> None:
        self._req("POST", "/wda/unlock")

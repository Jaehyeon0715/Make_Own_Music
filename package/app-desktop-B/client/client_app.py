# -*- coding: utf-8 -*-
"""AI Composer - desktop thin client (layout B).

Opens the GPU PC backend (:8080) in a pywebview window on the local PC.
All heavy generation runs on the GPU PC; this app only handles the UI window,
connection settings, and Wake-on-LAN.

backend/frontend code is served by the GPU PC, so it is not duplicated here.
"""
from __future__ import annotations

import json
import os
import sys
import threading

import requests
import webview  # pip install pywebview

from wol import send_magic_packet

APP_NAME = "MOM"
CONFIG_DIR = os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "AIComposer")
CONFIG_PATH = os.path.join(CONFIG_DIR, "client.json")
DEFAULTS = {"gpu_host": "", "port": 8080, "mac": ""}


# ── Resource path (PyInstaller bundle support) ────────────────────────
def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ── Config load/save ──────────────────────────────────────────────────
def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_config(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    merged = {**DEFAULTS, **cfg}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


# ── Connectivity check ────────────────────────────────────────────────
def base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    if not host:
        return False
    try:
        r = requests.get(f"{base_url(host, port)}/health", timeout=timeout)
        return r.status_code < 500
    except requests.RequestException:
        return False


# ── JS <-> Python bridge (called by the settings page) ────────────────
class Api:
    def __init__(self) -> None:
        self.window = None

    def get_config(self) -> dict:
        return load_config()

    def test_connection(self, host: str, port) -> dict:
        ok = reachable(host, int(port))
        return {"ok": ok, "url": base_url(host, int(port))}

    def save_and_open(self, host: str, port, mac: str) -> dict:
        host = (host or "").strip()
        port = int(port or 8080)
        save_config({"gpu_host": host, "port": port, "mac": (mac or "").strip()})
        if reachable(host, port):
            if self.window:
                self.window.load_url(base_url(host, port))
            return {"ok": True}
        # User-facing message (shown in settings UI) kept in Korean.
        return {"ok": False, "msg": f"{base_url(host, port)} 응답 없음 — GPU PC 켜짐·주소·방화벽 확인"}

    def wake(self, mac: str) -> dict:
        mac = (mac or "").strip()
        if not mac:
            return {"ok": False, "msg": "MAC 주소를 입력하세요"}
        try:
            send_magic_packet(mac)
            return {"ok": True, "msg": "Wake-on-LAN 매직패킷 전송됨 — 부팅까지 대기 후 [연결]"}
        except Exception as e:
            return {"ok": False, "msg": f"전송 실패: {type(e).__name__}: {e}"}


# ── Entry point ───────────────────────────────────────────────────────
def main() -> None:
    cfg = load_config()
    api = Api()

    # If configured and reachable, open the main UI directly; otherwise the settings page.
    if reachable(cfg["gpu_host"], int(cfg["port"])):
        start_url = base_url(cfg["gpu_host"], int(cfg["port"]))
        window = webview.create_window(APP_NAME, start_url, width=1200, height=820)
    else:
        window = webview.create_window(
            APP_NAME, resource_path("settings.html"),
            js_api=api, width=520, height=560,
        )
    api.window = window

    # Optional tray icon when pystray is available.
    try:
        from tray import run_tray
        threading.Thread(
            target=run_tray, args=(window, resource_path("icon.png")), daemon=True
        ).start()
    except Exception as e:  # pystray/Pillow missing, etc. - run without tray
        print(f"[tray] disabled: {e}")

    webview.start()  # Windows: uses the WebView2 (Edge Chromium) runtime


if __name__ == "__main__":
    main()

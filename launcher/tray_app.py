# -*- coding: utf-8 -*-
"""AI Composer system tray launcher.

Runs ACE-Step + Ollama + FastAPI as hidden subprocesses.
Tray icon menu controls open browser / view logs / restart / quit.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import config, services


# ── Icon ──────────────────────────────────────────────────────────────────────

def _make_icon(state: str = "loading") -> Image.Image:
    """Generate a simple status-colored circular icon."""
    color = {
        "loading": (255, 180, 50),  # orange
        "ready": (40, 124, 116),    # accent green
        "error": (180, 73, 50),     # red
    }.get(state, (120, 120, 120))

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 4, size - 4), fill=color, outline=(255, 255, 255, 230), width=3)
    # Letter "M" centered
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    text = "M"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 2), text, fill="white", font=font)
    return img


# ── Tray controller ─────────────────────────────────────────────────────────

class TrayController:
    def __init__(self) -> None:
        self.acestep = services.make_acestep()
        self.ollama = services.make_ollama()
        self.fastapi = services.make_fastapi()
        self.icon: pystray.Icon | None = None
        self.state = "loading"
        self.status_text = "초기화 중..."
        self._startup_thread: threading.Thread | None = None

    # ── Status helpers ──
    def set_state(self, state: str, text: str) -> None:
        self.state = state
        self.status_text = text
        if self.icon:
            self.icon.icon = _make_icon(state)
            self.icon.title = f"AI Composer — {text}"
            self.icon.update_menu()

    # ── Startup sequence ──
    def startup_sequence(self) -> None:
        try:
            self.set_state("loading", "Ollama 실행 중...")
            self.ollama.start()

            self.set_state("loading", "ACE-Step 실행 중...")
            self.acestep.start()

            self.set_state("loading", "ACE-Step 응답 대기...")
            if not services.wait_for_http(f"{config.ACESTEP_URL}/health", timeout=120):
                self.set_state("error", "ACE-Step 미응답 (logs/acestep.log 확인)")
                return

            self.set_state("loading", "ACE-Step 모델 로드 중 (수 분 소요)...")
            if not services.init_acestep_model():
                self.set_state("error", "ACE-Step 모델 초기화 실패")
                return

            self.set_state("loading", "FastAPI 실행 중...")
            self.fastapi.start()

            if not services.wait_for_http(f"{config.FASTAPI_URL}/health", timeout=30):
                self.set_state("error", "FastAPI 미응답 (logs/fastapi.log 확인)")
                return

            self.set_state("ready", "준비 완료")
            webbrowser.open(config.FASTAPI_URL)
        except Exception as e:
            self.set_state("error", f"오류: {type(e).__name__}: {e}")

    # ── Tray actions ──
    def on_open_browser(self, _icon=None, _item=None) -> None:
        webbrowser.open(config.FASTAPI_URL)

    def on_open_logs(self, _icon=None, _item=None) -> None:
        os.startfile(str(config.LOG_DIR))

    def on_restart(self, _icon=None, _item=None) -> None:
        self.stop_all()
        time.sleep(1)
        self._startup_thread = threading.Thread(target=self.startup_sequence, daemon=True)
        self._startup_thread.start()

    def on_quit(self, _icon=None, _item=None) -> None:
        self.stop_all()
        if self.icon:
            self.icon.stop()

    def stop_all(self) -> None:
        for svc in (self.fastapi, self.acestep, self.ollama):
            try:
                svc.stop()
            except Exception:
                pass

    # ── Menu builder ──
    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"● {self.status_text}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("브라우저 열기", self.on_open_browser, default=True),
            pystray.MenuItem("로그 폴더 열기", self.on_open_logs),
            pystray.MenuItem("재시작", self.on_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", self.on_quit),
        )

    def run(self) -> None:
        self.icon = pystray.Icon(
            "ai_composer",
            _make_icon("loading"),
            title="AI Composer — 초기화 중...",
            menu=self.build_menu(),
        )
        self._startup_thread = threading.Thread(target=self.startup_sequence, daemon=True)
        self._startup_thread.start()
        self.icon.run()


def main() -> None:
    TrayController().run()


if __name__ == "__main__":
    main()

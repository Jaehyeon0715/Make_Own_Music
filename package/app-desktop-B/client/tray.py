# -*- coding: utf-8 -*-
"""System tray icon (optional) - only when pystray + Pillow are installed.

Menu: Open / Reconnect / Quit. If missing, client_app proceeds without a tray.
"""
from __future__ import annotations

import os


def run_tray(window, icon_path: str) -> None:
    import pystray
    from PIL import Image

    if icon_path and os.path.exists(icon_path):
        image = Image.open(icon_path)
    else:  # No icon file: generate a solid 16x16 image
        image = Image.new("RGB", (16, 16), (40, 124, 116))

    def on_open(icon, item):
        try:
            window.show()
        except Exception:
            pass

    def on_reload(icon, item):
        try:
            window.evaluate_js("location.reload()")
        except Exception:
            pass

    def on_quit(icon, item):
        icon.stop()
        try:
            window.destroy()
        except Exception:
            pass
        os._exit(0)

    # Menu labels are user-facing (Korean).
    menu = pystray.Menu(
        pystray.MenuItem("열기", on_open, default=True),
        pystray.MenuItem("재연결", on_reload),
        pystray.MenuItem("종료", on_quit),
    )
    pystray.Icon("AIComposer", image, "MOM", menu).run()

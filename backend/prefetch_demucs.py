# -*- coding: utf-8 -*-
"""Pre-download Demucs model weights.

The first /generate/separated request otherwise stalls while Demucs fetches a
multi-hundred-MB checkpoint into the torch hub cache. Run this once after
installing requirements-demucs.txt:

    python -m backend.prefetch_demucs
    # or pick a model:  DEMUCS_MODEL=htdemucs_ft python -m backend.prefetch_demucs
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    model = os.getenv("DEMUCS_MODEL", "htdemucs")
    try:
        from demucs.pretrained import get_model
    except ModuleNotFoundError:
        print("demucs not installed. Run: pip install -r requirements-demucs.txt", file=sys.stderr)
        return 1

    print(f"Fetching Demucs model '{model}' ...", flush=True)
    try:
        get_model(model)  # downloads + caches weights, no separation performed
    except Exception as e:
        print(f"Failed to fetch '{model}': {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"Done. '{model}' is cached and ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

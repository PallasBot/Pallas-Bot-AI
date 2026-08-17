#!/usr/bin/env python3
"""CLI：fairseq hubert_base.pt → Transformers hubert_base/。

实现见 ``app.workers.sing.rvc_launcher.hubert_assets``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.workers.sing.rvc_launcher.hubert_assets import convert_hubert  # noqa: E402


def main() -> None:
    default_src = REPO / "resource/sing/models/pretrain/rvc/hubert_base/hubert_base.pt"
    default_out = REPO / "resource/sing/models/pretrain/rvc/hubert_base"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=default_src)
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--skip-sanity", action="store_true")
    args = parser.parse_args()
    path = convert_hubert(args.src, args.out, skip_sanity=args.skip_sanity)
    print(f"ok {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""社区 RVC 薄推理入口。

适配常见发放形态：
  - *.pth（v1 / v2，从 checkpoint 元数据识别）
  - 可选 *.index（同 stem 优先）

引擎代码来自子模块 ``app/workers/sing/RVC``（Retrieval-based-Voice-Conversion-WebUI）。
共享资产默认：
  resource/sing/models/pretrain/rvc/hubert_base/
  resource/sing/models/pretrain/rvc/rmvpe.pt
并软链到 RVC/assets/（若不存在）。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    # …/app/workers/sing/rvc/infer_rvc.py → 仓根
    return Path(__file__).resolve().parents[4]


def _rvc_root() -> Path:
    env = (os.environ.get("PALLAS_RVC_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_repo_root() / "app/workers/sing/RVC").resolve()


def _pretrain_rvc_dir() -> Path:
    env = (os.environ.get("PALLAS_RVC_PRETRAIN") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_repo_root() / "resource/sing/models/pretrain/rvc").resolve()


def _ensure_link(src: Path, dest: Path) -> None:
    if dest.is_symlink():
        try:
            if dest.resolve() == src.resolve():
                return
        except OSError:
            pass
        dest.unlink()
    elif dest.exists():
        # 旧布局：assets/hubert_base 实目录仅有 fairseq .pt，无法满足 Transformers 加载
        if dest.is_dir() and not (dest / "config.json").is_file() and src.is_dir():
            import shutil  # noqa: PLC0415

            shutil.rmtree(dest)
        else:
            return
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        # Windows 无权限软链时跳过；调用方仍可把资产直接放进 RVC/assets
        pass


def prepare_rvc_assets(rvc_root: Path) -> None:
    """把 pretrain/rvc 接到 RVC/assets，并设置 rmvpe_root。"""
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    pretrain = _pretrain_rvc_dir()
    assets = rvc_root / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    from app.workers.sing.rvc.hubert_assets import ensure_hubert_transformers  # noqa: PLC0415

    hubert_src = ensure_hubert_transformers(pretrain)
    hubert_dst = assets / "hubert_base"
    _ensure_link(hubert_src, hubert_dst)

    rmvpe_src = pretrain / "rmvpe.pt"
    rmvpe_dir = assets / "rmvpe"
    rmvpe_dir.mkdir(parents=True, exist_ok=True)
    rmvpe_dst = rmvpe_dir / "rmvpe.pt"
    _ensure_link(rmvpe_src, rmvpe_dst)
    if rmvpe_dst.is_file():
        os.environ["rmvpe_root"] = str(rmvpe_dir)
    elif rmvpe_src.is_file():
        os.environ["rmvpe_root"] = str(pretrain)
    else:
        # 兼容官方布局 assets/rmvpe/rmvpe.pt 已手动放置
        if (rmvpe_dir / "rmvpe.pt").is_file():
            os.environ["rmvpe_root"] = str(rmvpe_dir)


@dataclass
class InferConfig:
    device: str
    is_half: bool
    x_pad: int = 3
    x_query: int = 10
    x_center: int = 60
    x_max: int = 65
    cuda_graph: bool = False


def build_infer_config() -> InferConfig:
    import torch  # noqa: PLC0415

    if torch.cuda.is_available():
        device = "cuda:0"
        # 小显存强制 fp32，避免 OOM；其余半精度
        mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        is_half = mem_gb >= 5.5
        if is_half:
            return InferConfig(device=device, is_half=True)
        return InferConfig(
            device=device,
            is_half=False,
            x_pad=1,
            x_query=6,
            x_center=38,
            x_max=41,
        )
    return InferConfig(
        device="cpu",
        is_half=False,
        x_pad=1,
        x_query=6,
        x_center=38,
        x_max=41,
    )


def load_rvc_net(model_path: Path, config: InferConfig):
    import torch  # noqa: PLC0415
    from infer.module.models import (  # noqa: PLC0415
        SynthesizerTrnMs256NSFsid,
        SynthesizerTrnMs256NSFsid_nono,
        SynthesizerTrnMs768NSFsid,
        SynthesizerTrnMs768NSFsid_nono,
    )

    cpt = torch.load(str(model_path), map_location="cpu", weights_only=False)
    tgt_sr = cpt["config"][-1]
    cpt["config"][-3] = cpt["weight"]["emb_g.weight"].shape[0]
    if_f0 = cpt.get("f0", 1)
    version = cpt.get("version", "v1")
    synthesizer_class = {
        ("v1", 1): SynthesizerTrnMs256NSFsid,
        ("v1", 0): SynthesizerTrnMs256NSFsid_nono,
        ("v2", 1): SynthesizerTrnMs768NSFsid,
        ("v2", 0): SynthesizerTrnMs768NSFsid_nono,
    }
    net_g = synthesizer_class.get((version, if_f0), SynthesizerTrnMs256NSFsid)(
        *cpt["config"],
        is_half=config.is_half,
    )
    del net_g.enc_q
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval().to(config.device)
    if config.is_half:
        net_g = net_g.half()
    else:
        net_g = net_g.float()
    return net_g, tgt_sr, if_f0, version


def write_audio(path: Path, sr: int, audio) -> None:
    import numpy as np  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415

    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(audio)
    suffix = path.suffix.lower()
    if suffix == ".flac":
        sf.write(str(path), audio, sr, format="FLAC")
    elif suffix in {".wav", ".wave"}:
        sf.write(str(path), audio, sr, format="WAV")
    else:
        # 默认 flac，与 registry output_format 对齐
        out = path.with_suffix(".flac")
        sf.write(str(out), audio, sr, format="FLAC")
        if out != path:
            out.replace(path)


def run_infer(
    *,
    input_path: Path,
    model_path: Path,
    output_path: Path,
    f0_up_key: int,
    index_path: Path | None,
    f0_method: str,
    index_rate: float,
    protect: float,
    sid: int,
    resample_sr: int,
    rms_mix_rate: float,
) -> None:
    rvc_root = _rvc_root()
    if not (rvc_root / "infer").is_dir():
        raise FileNotFoundError(f"RVC 引擎未就绪: {rvc_root}（请 git submodule update --init app/workers/sing/RVC）")
    prepare_rvc_assets(rvc_root)
    # 保证 `import infer.*` / `import tools.*` 可用
    root_s = str(rvc_root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    if "rmvpe_root" not in os.environ and f0_method == "rmvpe":
        raise FileNotFoundError(
            "缺少 rmvpe.pt：放到 resource/sing/models/pretrain/rvc/rmvpe.pt 或 RVC/assets/rmvpe/rmvpe.pt"
        )

    import numpy as np  # noqa: PLC0415
    from infer.audio import load_audio  # noqa: PLC0415
    from infer.hubert import load_hubert_model  # noqa: PLC0415
    from infer.vc.pipeline import Pipeline  # noqa: PLC0415

    config = build_infer_config()
    net_g, tgt_sr, if_f0, version = load_rvc_net(model_path, config)
    hubert = load_hubert_model(config.device, config.is_half)
    pipeline = Pipeline(tgt_sr, config)

    audio = load_audio(str(input_path), 16000)
    audio_max = np.abs(audio).max() / 0.95
    if audio_max > 1:
        audio /= audio_max

    file_index = str(index_path) if index_path and index_path.is_file() else ""
    use_rate = float(index_rate) if file_index else 0.0
    times = [0, 0, 0]
    audio_opt = pipeline.pipeline(
        hubert,
        net_g,
        sid,
        audio,
        times,
        int(f0_up_key),
        f0_method,
        file_index,
        use_rate,
        if_f0,
        tgt_sr,
        int(resample_sr),
        float(rms_mix_rate),
        version,
        float(protect),
    )
    out_sr = int(resample_sr) if int(resample_sr) >= 16000 and int(resample_sr) != tgt_sr else tgt_sr
    write_audio(output_path, out_sr, audio_opt)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pallas RVC thin infer")
    p.add_argument("-i", "--input", required=True, help="输入人声音频")
    p.add_argument("-m", "--model", required=True, help="社区 RVC .pth")
    p.add_argument("-o", "--output", required=True, help="输出音频路径")
    p.add_argument("-k", "--key", type=int, default=0, help="变调半音")
    p.add_argument("--index", default="", help="可选 .index")
    p.add_argument("--f0method", default="rmvpe", help="rmvpe|harvest|crepe|pm|fcpe")
    p.add_argument("--index-rate", type=float, default=0.55)
    p.add_argument("--protect", type=float, default=0.4)
    p.add_argument("--sid", type=int, default=0, help="多说话人 id，单说话人通常 0")
    p.add_argument("--resample-sr", type=int, default=0)
    p.add_argument("--rms-mix-rate", type=float, default=0.25)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    index_path = Path(args.index).expanduser().resolve() if str(args.index).strip() else None
    if not input_path.is_file():
        print(f"input not found: {input_path}", file=sys.stderr)
        return 2
    if not model_path.is_file():
        print(f"model not found: {model_path}", file=sys.stderr)
        return 2
    try:
        run_infer(
            input_path=input_path,
            model_path=model_path,
            output_path=output_path,
            f0_up_key=int(args.key),
            index_path=index_path,
            f0_method=str(args.f0method),
            index_rate=float(args.index_rate),
            protect=float(args.protect),
            sid=int(args.sid),
            resample_sr=int(args.resample_sr),
            rms_mix_rate=float(args.rms_mix_rate),
        )
    except Exception as exc:
        print(f"rvc infer failed: {exc}", file=sys.stderr)
        raise
    if not output_path.is_file():
        print(f"output missing after infer: {output_path}", file=sys.stderr)
        return 1
    print(f"ok {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

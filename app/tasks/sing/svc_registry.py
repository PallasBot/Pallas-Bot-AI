"""SVC 模型后端注册表。

设计目标:把"哪个模型族用哪个脚本、用什么命令行参数、怎么找模型文件"从
Python 核心代码里剥离到 YAML 配置(见 `resource/sing/registry.yaml`)。
加一个新模型族(如 RVC、DDSP-7)只需要在 YAML 加一段,无需改 Python。

CLI 参数风格分类:
  - ddsp:   -i input -m model -o output -k key      (DDSP-SVC 6.1/6.2/6.3 共用)
  - sovits: -f input -m model -c config -t key -o output  (SoVITS 4.0/4.1 共用)

新加风格(如 rvc)只需在 `build_command` 里加一个 elif 分支。
"""

from __future__ import annotations

import os
import platform
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.core.logger import logger


class ArgStyle(str, Enum):
    DDSP = "ddsp"
    SOVITS = "sovits"


class ModelBackend(BaseModel):
    """单个模型族后端描述。

    注:`name` 字段由 SvcRegistry 从 dict key 注入,YAML 里不用写。
    """

    name: str = ""
    script: Path = Field(description="子模块入口 .py 绝对/相对路径")
    arg_style: ArgStyle
    model_glob: str = Field(description="在 speaker_dir 下用于 glob 模型文件的模式,如 *.pt / G_*.pth")
    required_files: list[str] = Field(
        default_factory=list,
        description="判定该 backend 适用于某个 speaker 必须存在的文件(空=只要有 model_glob 命中即可)",
    )
    extra_args: list[str] = Field(
        default_factory=list,
        description="所有调用都要追加的固定参数,如 ['-shd'] 开启浅扩散",
    )
    output_suffix: str = Field(default="", description="输出文件名后缀,如 '_ddsp' / '_sovits'")
    output_format: str = "flac"
    enabled: bool = True

    @field_validator("script", mode="before")
    @classmethod
    def _resolve_script(cls, v: str | Path) -> Path:
        # YAML 里写的是相对项目根的路径(如 app/tasks/sing/DDSP-SVC-6.3/main_reflow.py)
        # 这里把它绝对化;这样 build_command 拿到的是绝对路径,subprocess 行为可预测
        p = Path(v)
        if not p.is_absolute():
            p = (Path.cwd() / p).absolute()
        return p

    def find_output(self, output_path: Path, *, since_mtime: float = 0.0) -> Path | None:
        """根据后端约定,定位本次推理产生的实际产物文件路径;没找到返回 None。

        不同 arg_style 写出策略不同:
          - DDSP:`-o <file>`,脚本直接写文件,output_path 就是产物。
          - SoVITS:`-o <dir>`,文件名由脚本内部决定,我们只能 glob 同目录
            找 mtime > since_mtime 的最新目标格式文件。

        since_mtime:调用方传入的"调用前 output_dir 中目标格式文件的最大 mtime",
                     用于过滤掉上次推理的残留文件(避免误认)。
        """
        if self.arg_style is ArgStyle.DDSP:
            if not output_path.exists():
                return None
            # DDSP 缓存命中路径在 inference() 里已处理,这里再核一次 mtime 防 TOCTOU
            if since_mtime and output_path.stat().st_mtime <= since_mtime:
                return None
            return output_path
        # SoVITS 等以目录为 -o 的后端:取 output_path.parent 下 mtime > since_mtime
        # 的目标格式文件中 mtime 最大的那一个
        candidates = [p for p in output_path.parent.glob(f"*.{self.output_format}") if p.stat().st_mtime > since_mtime]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)


class SvcRegistry(BaseModel):
    """注册表根对象。"""

    backends: dict[str, ModelBackend]
    fallback_order: list[str] = Field(description="回退顺序,前者优先")

    @model_validator(mode="after")
    def _inject_backend_names(self) -> SvcRegistry:
        """把 dict key 注入到每个 backend 的 name 字段(YAML 不用重复写)。"""
        for key, backend in self.backends.items():
            if backend.name and backend.name != key:
                logger.warning("backend {} 的 name 字段 '{}' 与 dict key 不一致,优先用 dict key", key, backend.name)
            backend.name = key
        return self

    @field_validator("fallback_order")
    @classmethod
    def _validate_order(cls, v: list[str], info) -> list[str]:
        backends = info.data.get("backends", {})
        for name in v:
            if name not in backends:
                raise ValueError(f"fallback_order 引用了未定义的 backend: {name}")
        return v

    def compatible_backends(self, speaker_dir: Path) -> list[ModelBackend]:
        """按 fallback_order 顺序,返回在给定 speaker 目录下资源齐备的 backend 列表。

        判定"齐备":该 backend 的 `model_glob` 至少命中 1 个文件 + `required_files` 全在。
        """
        result: list[ModelBackend] = []
        for name in self.fallback_order:
            backend = self.backends[name]
            if not backend.enabled:
                continue
            if not next(speaker_dir.glob(backend.model_glob), None):
                continue
            missing = [f for f in backend.required_files if not (speaker_dir / f).is_file()]
            if missing:
                logger.debug(
                    "backend {} 跳过: speaker={} 缺文件 {}",
                    name,
                    speaker_dir.name,
                    missing,
                )
                continue
            result.append(backend)
        return result


# ── 加载与单例 ─────────────────────────────────────────────

_REGISTRY: Optional[SvcRegistry] = None


def load_registry(path: Path | str) -> SvcRegistry:
    """从 YAML 文件加载注册表。文件不存在或解析失败抛 ValueError。"""
    p = Path(path)
    if not p.is_file():
        msg = f"registry 文件不存在: {p}"
        raise FileNotFoundError(msg)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        msg = f"registry YAML 解析失败: {e}"
        raise ValueError(msg) from e
    if not isinstance(data, dict):
        msg = f"registry 根必须是 mapping,实际是 {type(data).__name__}"
        raise ValueError(msg)
    return SvcRegistry.model_validate(data)


def get_registry() -> SvcRegistry:
    """获取注册表单例(懒加载,首次调用时读 settings.svc_registry_path)。

    YAML 缺失 / 解析失败时不抛异常,而是返回一个空注册表(空 backends + 空
    fallback_order),让服务仍可启动。后续 inference() 调用会因
    `compatible_backends` 返回空列表而直接报"无可用 backend",不会让
    SVC 整个模块在配置错误时崩溃。
    """
    global _REGISTRY
    if _REGISTRY is None:
        try:
            _REGISTRY = load_registry(settings.svc_registry_path)
            logger.info(
                "svc registry 已加载: backends={} fallback={}",
                list(_REGISTRY.backends),
                _REGISTRY.fallback_order,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.error(
                "svc registry 加载失败,降级为空注册表(后续 SVC 推理会全部失败): {}",
                e,
            )
            _REGISTRY = SvcRegistry(backends={}, fallback_order=[])
    return _REGISTRY


def reset_registry_cache() -> None:
    """测试/热重载场景下手动清空单例。"""
    global _REGISTRY
    _REGISTRY = None


# ── 命令构造 ──────────────────────────────────────────────


def build_command(
    backend: ModelBackend,
    speaker_dir: Path,
    song_path: Path,
    output_path: Path,
    key: int,
    model_path: Path,
) -> list[str]:
    """根据 backend 风格构造 subprocess 命令(list[str],绝不 shell=True)。

    返回的命令形如:
      ddsp:   ["python", "<script>", "-i", song, "-m", model, "-o", out, "-k", str(key), ...extra]
      sovits: ["python", "<script>", "-f", song, "-m", model, "-c", config, "-t", str(key),
              "-o", out_dir, "-s", speaker, ...extra]
    """
    cmd: list[str] = ["python", str(backend.script)]

    if backend.arg_style is ArgStyle.DDSP:
        cmd += [
            "-i",
            str(song_path.absolute()),
            "-m",
            str(model_path.absolute()),
            "-o",
            str(output_path.absolute()),
            "-k",
            str(key),
        ]
    elif backend.arg_style is ArgStyle.SOVITS:
        # SoVITS 需要 config.json,缺了就当不兼容(在 compatible_backends 已过滤)
        config_path = speaker_dir / "config.json"
        # SoVITS 的 -o 是输出目录,不是文件
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd += [
            "-f",
            str(song_path.absolute()),
            "-m",
            str(model_path.absolute()),
            "-c",
            str(config_path.absolute()),
            "-t",
            str(key),
            "-s",
            speaker_dir.name,
            "-o",
            str(output_dir.absolute()),
        ]
    else:
        msg = f"未实现的 arg_style: {backend.arg_style}"
        raise NotImplementedError(msg)

    cmd += list(backend.extra_args)
    return cmd


# ── 子进程运行辅助(供 svc_inference 调用) ─────────────────


def build_env() -> dict[str, str]:
    """构造带 CUDA_VISIBLE_DEVICES 的环境变量,跨平台兼容。

    注意:`cuda_device = 0` 是合法的 GPU 0 设备,**不是**"未配置"。
    只有 `None` 才视作未配置,跳过设置,以避免在默认部署下静默关闭 CUDA。
    (settings.sing_cuda_device 类型是 int,默认 0,这里 `is None` 等价于"未设置"。)
    """
    env = os.environ.copy()
    cuda_device = settings.sing_cuda_device
    if cuda_device is None:
        return env
    key = "CUDA_VISIBLE_DEVICES"
    if platform.system() == "Windows":
        # Windows cmd 不支持 export 语法,需要 set,但 subprocess 不经 shell 时直接放 env 即可
        env[key] = str(cuda_device)
    else:
        env[key] = str(cuda_device)
    return env


def run_subprocess(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """统一封装 subprocess.run:不 shell、捕获 stderr、加超时。"""
    return subprocess.run(  # noqa: S603
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=build_env(),
    )

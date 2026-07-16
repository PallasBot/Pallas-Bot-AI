# 开发日志 · Pallas-Bot-AI

> 📓 这里按日期倒序记录开发过程中的关键决策、改动和踩坑。
> 想知道"为什么这么写" / "那次改动到底干了啥",来这里翻。

---

## 2026-07-09 · 评审回合:3 个真 bug + 1 个误报 🧯

> **TL;DR**: Sourcery-AI 在 [PR #11](https://github.com/PallasBot/Pallas-Bot-AI/pull/11) 留了
> 4 条评审意见,其中 3 条是实打实的 bug,1 条是误报。逐条处理完顺手记一下:
> - `build_env` 把 `0` 当成"未配置",默默关掉 CUDA → 区分 `None` 才是真·未配置
> - `get_registry` YAML 坏了直接抛,SVC 推理整个崩 → 优雅降级到空注册表
> - SoVITS 用 `-o <dir>` 不是文件,`output_path.exists()` 永远 False → 给 backend 加
>   `find_output()` 方法,按约定去找产物
> - (误报)`mp3_to_wav` "不返回 wav 路径" → 实际 HEAD 代码有 `return Path(wav_file_path)`,
>   函数签名返回类型也是 `Path`,评审看走眼了

### 🎯 起因

[Sourcery-AI 在 PR #11](https://github.com/PallasBot/Pallas-Bot-AI/pull/11) 留了 2 条
inline 评论 + 2 条总体评论。评审内容主要是鲁棒性问题:

- `build_env` 的 `if cuda_device in (None, 0, "")` → `0` 是合法 GPU 设备,不是"未配置"
- `_try_backend` 一刀切 `output_path.exists()`,但 SoVITS 的 `-o` 是目录不是文件
- `get_registry` 直接传播 `FileNotFoundError` / `ValueError`,YAML 配错就崩整个服务
- 误报: `mp3_to_wav` 没返回值 → 实际是 `return Path(wav_file_path)`,评审看岔了

### 🛠️ 改动

#### 修改 2 个文件

**`app/tasks/sing/svc_registry.py`**

1. **`build_env()`** — 把 0 从"未配置"名单里摘掉

```python
# 之前
if cuda_device in (None, 0, ""):
    return env

# 之后
if cuda_device is None:
    return env
```

`sing_cuda_device: int = 0` 是默认 GPU 0,以前在 `bool(0) == False` 的"truthy 检查"下
被一并跳过——现在只有显式 `None` 才算未配置。

2. **`get_registry()`** — YAML 加载失败优雅降级

```python
try:
    _REGISTRY = load_registry(settings.svc_registry_path)
    logger.info(...)
except (FileNotFoundError, ValueError) as e:
    logger.error("svc registry 加载失败,降级为空注册表(...): {}", e)
    _REGISTRY = SvcRegistry(backends={}, fallback_order=[])
```

服务照样起,SVC 推理会因 `compatible_backends` 返回空列表而走"无可用 backend"分支,
**不会让配置错误拖垮整个 Celery worker**。

3. **新增 `ModelBackend.find_output()`** — 按约定定位产物

```python
def find_output(self, output_path, *, since_mtime: float = 0.0) -> Path | None:
    if self.arg_style is ArgStyle.DDSP:
        # DDSP: -o 是文件,直接 exists + mtime 校验
        ...
        return output_path
    # SoVITS: -o 是目录,glob 取目录里 mtime > since_mtime 的最新目标格式文件
    candidates = [p for p in output_path.parent.glob(f"*.{self.output_format}")
                  if p.stat().st_mtime > since_mtime]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
```

**`app/tasks/sing/svc_inference.py`**

1. **`_try_backend()`** — 快照 pre_max_mtime + 委托 backend 找产物

```python
# 子进程前:记下 output_dir 里目标格式文件的最大 mtime
pre_max_mtime = max(
    (p.stat().st_mtime for p in output_path.parent.glob(f"*.{backend.output_format}")),
    default=0.0,
)
# ...
actual_output = backend.find_output(output_path, since_mtime=pre_max_mtime)
```

2. **`inference()` 缓存命中检查**也改用 `find_output`,避免 SoVITS 产物文件名跟预测不
   一致时漏判。

### 🐛 修了的 bug(细节)

#### Bug 1: 默认部署默默关 CUDA

`sing_cuda_device` 默认 0,意味着 GPU 0。但 `if cuda_device in (None, 0, "")` 把 0 也
当"未配置"跳过,导致环境变量里没有 `CUDA_VISIBLE_DEVICES`——Torch 默认行为会去抢
GPU 0,但在多卡机器 + 多 worker 场景下行为不可预测。

修法: 只判 `None` 算未配置。烟测 `build_env()` 默认 → `env["CUDA_VISIBLE_DEVICES"] == "0"` ✓

#### Bug 2: 配置错误拖垮整个 SVC

YAML 路径写错 / 文件不存在 / YAML 解析失败 → `load_registry` 抛 `FileNotFoundError`
或 `ValueError` → `get_registry` 直接传播 → 任何调用方(`inference()`)都崩。

修法: `get_registry()` 用 try/except 包住,失败时缓存一个 `SvcRegistry(backends={},
fallback_order=[])`。服务能起,SVC 推理会清晰报错"无可用 backend",而不是爆栈。

#### Bug 3: SoVITS 成功却误判失败

`_try_backend` 老逻辑: `if not output_path.exists(): return None`。

问题: `build_command` 给 SoVITS 传的 `-o` 是 `output_path.parent`(目录),SoVITS
脚本(`inference_main.py:152`)自己决定文件名,跟预测的 `output_path` 完全无关。
SoVITS 跑成功之后 `output_path.exists()` 永远是 False,**每个 SoVITS 调用都被误判
为失败**。

修法:
- 给 `ModelBackend` 加 `find_output()` 方法,DDSP 和 SoVITS 各按自己的约定找产物
- `_try_backend` 在子进程跑前快照 `output_dir` 里目标格式文件的最大 mtime,跑完
  用 `since_mtime=pre_max_mtime` 让 `find_output` 过滤掉上次推理的残留
- `inference` 的缓存命中检查也改走 `find_output`,避免 SoVITS 漏命中

烟测:
- DDSP backend,产物文件存在 → `find_output` 返回该文件 ✓
- SoVITS backend,产物文件名 ≠ 预测名 → `find_output` glob 出新文件 ✓

### 🚫 没动的(误报)

**Comment 1: "mp3_to_wav 不再返回 wav 路径,Windows 上会变 None"**

读 HEAD 实际代码确认 [svc_inference.py:199](app/tasks/sing/svc_inference.py#L199) 已经有:

```python
def mp3_to_wav(mp3_file_path: Path) -> Path:
    ...
    sound.export(wav_file_path, format="wav")
    return Path(wav_file_path)  # ← 已经有!
```

函数签名返回类型也是 `Path`,实际行为没问题。**评审看走眼了,不改**。

### 🎯 最终验证结果

| 项 | 期望 | 结果 |
| --- | --- | --- |
| `build_env(0)` | `CUDA_VISIBLE_DEVICES=0` | ✅ |
| `get_registry` YAML 缺失 | 返回空注册表,不抛 | ✅ |
| `find_output` DDSP 风格 | 返回产物文件 | ✅ |
| `find_output` SoVITS 风格 | glob 目录返回最新匹配 | ✅ |
| `ruff format --check` 两个文件 | already formatted | ✅ |
| `import app.tasks.sing.svc_*` | 无 ImportError | ✅ |

---

## 2026-07-09 · SVC 推理兼容层重构 🦾

> **TL;DR**: 把 `app/tasks/sing/svc_inference.py` 从"硬编码 if 链"
> 重构成"配置驱动注册表",修了 5+ 个隐藏 bug,加新模型族改 YAML 即可。
> **架构决策**:详见 [ADR-001](decisions/2026-07-09-svc-inference-registry.md)

### 🎯 起因

用户说:"这个兼容层能不能重构一下,现在这个很臃肿,
而且后续换新模型还要改。"

一读 `svc_inference.py` 现状,问题清单立刻列出来:

| 问题 | 现状 |
| --- | --- |
| 加模型成本 | 必须改 Python 代码,塞一段 `if ret != 0` |
| GPU 锁 | `locker` 收下但**从未加锁**!多 worker 同时跑会 OOM |
| subprocess | `subprocess.call(shell=True)` 拼字符串,无 stderr、无超时 |
| 死代码 | SoVITS 分支 `speaker_models[speaker]` 必 `KeyError`(初始化 `{}` 后没填过) |
| 路径拼接 | SoVITS 分支用 `f'{output_dir}\\{stem}'`,Linux 上是真反斜杠字符 |
| 日志 | 全是 `print(...)`,没走 logger |
| 全局状态 | `global svc_edition` 定义又赋值,**0 处读取** |

### 🛠️ 改动

#### 新增 2 个文件

**`app/core/svc_registry.py`** (~190 行)
- `ArgStyle` 枚举:`DDSP` / `SOVITS`,新风格必须显式扩展
- `ModelBackend` pydantic 模型:`name` / `script` / `arg_style` / `model_glob` /
  `required_files` / `extra_args` / `output_suffix` / `output_format` / `enabled`
- `SvcRegistry` 根对象:用 `model_validator(mode="after")` 把 dict key 注入到
  `ModelBackend.name`,这样 YAML 里**不用重复写 name**
- `load_registry(path)` / `get_registry()` / `reset_registry_cache()`
- `compatible_backends(speaker_dir)` 按 `fallback_order` 过滤出"该 speaker 资源齐备"的
- `build_command(...)` 按 `arg_style` 分支构造 `list[str]`(给 subprocess.run 用,**绝不 shell=True**)
- `build_env()` 跨平台 CUDA_VISIBLE_DEVICES 注入
- `run_subprocess(cmd, timeout)` 统一封装:capture_output=True + timeout

**`resource/sing/registry.yaml`**
- 4 个 backend:DDSP 6.3 / 6.2 / 6.1 / SoVITS 4.1
- `fallback_order` 按优先级排列
- 每段都带中文注释说明字段含义

#### 修改 2 个文件

**`app/core/config.py`** — 加 3 字段(放在 sing 相关字段后面):

```python
svc_models_root: str = "resource/sing/models"
svc_registry_path: str = "resource/sing/registry.yaml"
svc_inference_timeout: int = 600
```

**`app/tasks/sing/svc_inference.py`** — 从 129 行重写为 ~140 行

新的核心流程:

```python
def inference(song_path, output_dir, key=0, speaker="pallas", locker=None):
    # 1. Windows 转 wav、找 speaker_dir、查 registry
    # 2. registry.compatible_backends(speaker_dir) → 拿"这 speaker 能跑的"列表
    # 3. for backend in candidates:  # 按 fallback_order
    #    3a. _find_speaker_model() 选 step 最大的模型文件
    #    3b. output_path 已存在? → 直接返回(不进 GPU 锁,不打 subprocess)
    #    3c. _try_backend(backend, ..., locker) → 真正跑
    #    3d. 成功 → return output_path;失败 → continue
    # 4. 全失败 → logger.error + return None
```

### 🐛 修了的 bug(细节)

#### Bug 1: GPU 锁形同虚设

老代码:
```python
def inference(..., locker=None):
    # ... 完全没用 locker
    subprocess.call(ddsp63cmd, shell=True)
```

新代码:
```python
@contextmanager
def _maybe_lock(locker):
    if locker is None:
        yield
    else:
        with locker.acquire():
            yield

# 在 _try_backend 里:
with _maybe_lock(locker):
    result = run_subprocess(cmd, timeout=settings.svc_inference_timeout)
```

锁真正用上了!多 Celery worker 跑也不会争 GPU。

#### Bug 2: subprocess 现代化

老代码:
```python
ret = subprocess.call(f'python {DDSP} -i ...', shell=True)  # 无超时、无 stderr、shell 注入风险
```

新代码(抄 `app/core/ollama_runtime.py:120` 的模板):
```python
result = subprocess.run(
    cmd,                              # list[str],绝不用 shell
    shell=False,
    capture_output=True,              # stderr 截前 500 字符进日志
    text=True,
    timeout=settings.svc_inference_timeout,  # 600 秒
    env=build_env(),                  # 显式 CUDA_VISIBLE_DEVICES
)
```

#### Bug 3: SoVITS 死代码删除

老代码里的 SoVITS 分支**永远不可能成功**:
```python
speaker_models = {}  # 永远空字典
# ... 然后一堆 if speaker not in speaker_models 都被注释掉了
model = speaker_models[speaker].absolute()  # ← KeyError 必崩
```

新版直接由配置驱动:`sovits_4.1` backend 用 `G_*.pth` glob + `config.json` 校验,
在 `compatible_backends()` 阶段就过滤掉资源不齐的 speaker。

#### Bug 4: Linux 路径字面反斜杠

老代码:
```python
result = output_dir / f'{output_dir}\\{stem}_{key}key_{speaker}_sovits_pm.{SVC_OUPUT_FORMAT}'
#          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#          Linux 上 output_dir 被 {output_dir} 字符串化,文件名里含字面反斜杠
```

新代码(平台无关):
```python
output_path = output_dir / f"{stem}_{key}key_{speaker}{backend.output_suffix}.{backend.output_format}"
```

`Path / str` 拼接,Windows/Linux 都对。

### 🧪 验证过程(踩过的坑也算踩坑)

#### 第一次验证:registry 加载炸了

**症状**: `pydantic_core.ValidationError: name Field required`

**原因**: YAML 里我把 backend 名当 dict key(`ddsp_6.3:`),但 `ModelBackend.name`
是 required,YAML 里没写。

**修法**: 加 `model_validator(mode="after")` 把 dict key 注入到 `name` 字段,
YAML 不用重复写。

**学到**:pydantic 字段对齐 YAML 结构要提前想清楚。

#### 第二次验证:dry-run mock 失效(经典坑)

**症状**: `unittest.mock.patch.object(svc_registry, "run_subprocess", ...)` 没生效,
subprocess **真的跑了**——3 个 DDSP 都报 `Unknown Model: Diffusion`,SoVITS 报
`ModuleNotFoundError: No module named 'faiss'`。

**原因**: `svc_inference.py` 用 `from app.core.svc_registry import run_subprocess`,
patch 原模块属性不会影响**已经导入到目标模块命名空间的名字**。

**修法**: 改成 `patch.object(svc_inference, "run_subprocess", ...)`,patch 命名空间
所在的模块。

**学到**: mock 永远 patch **使用方**模块,不是 **定义方** 模块。

#### 第三次验证:塞翁失马

那次 mock 失效反而触发了**真·端到端集成测试**——虽然模型文件不匹配(DDSP 喂了
SoVITS 的 .pth)导致失败,但从日志能看出:

- ✅ Registry 单例加载
- ✅ 3 个 DDSP 按 fallback_order 顺序被尝试(6.3 → 6.2 → 6.1)
- ✅ 命令构造正确(`-i -m -o -k` 完整)
- ✅ stderr 正确捕获并截断
- ✅ DDSP 全失败自动切到 SoVITS
- ✅ 全失败返 None,logger 输出"用尽所有 backend 仍未成功"

**学到**: 出错时别慌,日志可能是你最好的老师。

### 🎯 最终验证结果(干净 mock 版)

| 测试 | 期望 | 结果 |
| --- | --- | --- |
| 1. fallback 链 + 首个成功即返回 | 前 3 个失败 + 第 4 个成功 → 停 | ✅ |
| 2. cache hit 短路 | 输出已存在 → 不调任何 backend | ✅ |
| 3. 全失败返 None | 4 个 backend 都试 → None | ✅ |
| 4. 资源筛选 | silverash 只跑 sovits | ✅ |

加 ruff format + py_compile + import 冒烟,全绿。

### 🚀 后续怎么加新模型(教学)

假设要加 RVC,改 2 处:

**1. `resource/sing/registry.yaml`** 加一段:

```yaml
backends:
  # ... 已有 4 个 ...
  rvc_main:
    script: app/tasks/sing/rvc/infer.py
    arg_style: rvc        # 新风格
    model_glob: "*.pth"
    required_files: ["rmvpe.pt"]
    output_suffix: "_rvc"

fallback_order:
  - ddsp_6.3
  # ... 已有 ...
  - rvc_main
```

**2. `app/core/svc_registry.py` 加一个 elif**:

```python
class ArgStyle(str, Enum):
    DDSP = "ddsp"
    SOVITS = "sovits"
    RVC = "rvc"   # ← 新增

# build_command 里加:
elif backend.arg_style is ArgStyle.RVC:
    cmd += ["--input", str(song_path.absolute()), "--model", ...]
    # ... RVC 自己的参数模板
```

核心循环 0 改动。

### 📌 待办 / 留给未来的事

- [ ] `tests/` 加 1-2 个 SVC registry 单元测试(项目历史就没 test 目录,留个钩子)
- [ ] 加 RVC(看社区有没有热门模型可以集成)
- [ ] Registry 加 schema 版本号字段,以后改 YAML 字段名能平滑迁移
- [ ] GPU 锁的"等待队列长度"监控,锁太久能报警

---

> 📖 相关: [ADR-001: SVC 推理注册表架构决策](decisions/2026-07-09-svc-inference-registry.md)
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.core.config import Settings, settings
from app.core.logger import logger
from app.providers.local_backend import complete_local_message
from app.providers.moe import MoeTier, categorize_request_tier, minimum_tier_for_tools, resolve_inference_tier
from app.providers.operator_lookup import is_self_identity_question

_NO_TOOL_TASKS = frozenset({"repeater_fallback", "repeater_polish", "repeater_polish_lite", "repeater_select", "drunk"})

_TOOL_HINTS = (
    "干员",
    "技能",
    "天赋",
    "敌人",
    "关卡",
    "活动",
    "方舟",
    "明日方舟",
    "arknights",
    "查一下",
    "查询",
    "资料",
    "档案",
    "立绘",
    "是谁",
    "谁是",
    "你知道",
    "介绍一下",
    "介绍下",
    "什么角色",
    "哪个干员",
    "画画",
    "抽卡",
    "忘掉",
    "清空",
    "clear",
    "卸模型",
    "换模型",
)

_COMMAND_TOOL_PREFIXES = (
    "llm_chat.",
    "draw.",
)

ClassificationSource = Literal["heuristic", "model", "metadata"]

_CATEGORIZER_SYSTEM = (
    "你是请求分类器。根据用户最后一句话输出一行 JSON："
    '{"needs_tools":true/false,"tier":"simple|medium|complex","needs_vision":true/false}。'
    "needs_tools：是否需要游戏数据查询或执行命令类工具。"
    "tier：simple=短闲聊，medium=一般，complex=分析/长文/多问题。"
    "needs_vision：是否必须理解图片内容（含图消息为 true）。"
    "只输出 JSON。"
)

_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


@dataclass(frozen=True)
class RequestClassification:
    needs_tools: bool
    tier: MoeTier
    source: ClassificationSource
    needs_vision: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_classification(classification: RequestClassification) -> RequestClassification:
    tier = minimum_tier_for_tools(classification.tier, classification.needs_tools)
    if tier == classification.tier:
        return classification
    return RequestClassification(
        needs_tools=classification.needs_tools,
        tier=tier,
        source=classification.source,
        needs_vision=classification.needs_vision,
    )


def categorizer_model_name(cfg: Settings | None = None) -> str:
    c = cfg or settings
    explicit = (c.llm_categorizer_model or "").strip()
    if explicit:
        return explicit
    return (c.llm_moe_model_simple or "").strip()


def categorizer_enabled(cfg: Settings | None = None) -> bool:
    c = cfg or settings
    if not c.llm_categorizer_enabled:
        return False
    return bool(categorizer_model_name(c))


def needs_vision_for_request(
    user_text: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> bool:
    meta = metadata if isinstance(metadata, dict) else {}
    if meta.get("vision_required") is True:
        return True
    if meta.get("vision_required") is False:
        return False
    if meta.get("has_image") is True:
        return True
    classified = classification_from_metadata(meta)
    if classified is not None:
        return classified.needs_vision
    text = user_text or ""
    lower = text.casefold()
    if "[cq:image" in lower or "[cq:mface" in lower:
        return True
    return False


def classify_request_heuristic(
    user_text: str,
    *,
    task: str,
    metadata: dict[str, Any] | None = None,
) -> RequestClassification:
    meta = metadata if isinstance(metadata, dict) else {}
    needs_tools = needs_tools_for_request(user_text, task=task, metadata=meta)
    tier = categorize_request_tier(user_text, meta)
    needs_vision = needs_vision_for_request(user_text, metadata=meta)
    return normalize_classification(
        RequestClassification(
            needs_tools=needs_tools,
            tier=tier,
            source="heuristic",
            needs_vision=needs_vision,
        )
    )


def parse_categorizer_payload(raw: str) -> RequestClassification | None:
    text = (raw or "").strip()
    if not text:
        return None
    candidates = [text]
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        needs_tools = data.get("needs_tools")
        tier = str(data.get("tier") or "").strip().lower()
        needs_vision = data.get("needs_vision")
        if not isinstance(needs_tools, bool):
            continue
        if tier not in ("simple", "medium", "complex"):
            tier = "medium"
        vision_flag = bool(needs_vision) if isinstance(needs_vision, bool) else False
        return normalize_classification(
            RequestClassification(
                needs_tools=needs_tools,
                tier=tier,  # type: ignore[arg-type]
                source="model",
                needs_vision=vision_flag,
            )
        )
    return None


async def classify_request_async(
    user_text: str,
    *,
    task: str,
    metadata: dict[str, Any] | None = None,
    cfg: Settings | None = None,
) -> RequestClassification:
    meta = metadata if isinstance(metadata, dict) else {}
    normalized_task = str(task or "").strip().lower()

    if meta.get("tools_required") is True:
        tier = categorize_request_tier(user_text, meta)
        return normalize_classification(
            RequestClassification(
                needs_tools=True,
                tier=tier,
                source="metadata",
                needs_vision=needs_vision_for_request(user_text, metadata=meta),
            )
        )
    if meta.get("tools_required") is False:
        tier = categorize_request_tier(user_text, meta)
        return normalize_classification(
            RequestClassification(
                needs_tools=False,
                tier=tier,
                source="metadata",
                needs_vision=needs_vision_for_request(user_text, metadata=meta),
            )
        )

    if normalized_task in _NO_TOOL_TASKS:
        return RequestClassification(needs_tools=False, tier="simple", source="heuristic", needs_vision=False)

    c = cfg or settings
    if not categorizer_enabled(c):
        return classify_request_heuristic(user_text, task=task, metadata=meta)

    model = categorizer_model_name(c)
    provider_id = (c.llm_categorizer_provider or "local").strip() or "local"
    prompt_user = f"task={normalized_task or 'llm_chat'}\nuser={(user_text or '').strip()[:500]}"

    try:
        message = await complete_local_message(
            [
                {"role": "system", "content": _CATEGORIZER_SYSTEM},
                {"role": "user", "content": prompt_user},
            ],
            model=model,
            options={
                "temperature": 0.0,
                "num_predict": int(c.llm_categorizer_num_predict),
            },
            provider_id=provider_id,
        )
        parsed = parse_categorizer_payload(str(message.get("content", "") or ""))
        if parsed is not None:
            return normalize_classification(parsed)
        logger.warning("categorizer 解析失败，回退启发式 model={} body={}", model, message.get("content"))
    except Exception as exc:
        logger.warning("categorizer 调用失败，回退启发式 model={} err={}", model, exc)

    return classify_request_heuristic(user_text, task=task, metadata=meta)


def classification_from_metadata(metadata: dict[str, Any] | None) -> RequestClassification | None:
    meta = metadata if isinstance(metadata, dict) else {}
    raw = meta.get("classification")
    if not isinstance(raw, dict):
        return None
    needs_tools = raw.get("needs_tools")
    tier = str(raw.get("tier") or "").strip().lower()
    source = str(raw.get("source") or "heuristic").strip().lower()
    needs_vision = raw.get("needs_vision")
    if not isinstance(needs_tools, bool):
        return None
    if tier not in ("simple", "medium", "complex"):
        tier = "medium"
    if source not in ("heuristic", "model", "metadata"):
        source = "heuristic"
    vision_flag = bool(needs_vision) if isinstance(needs_vision, bool) else False
    return RequestClassification(
        needs_tools=needs_tools,
        tier=tier,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        needs_vision=vision_flag,
    )


def needs_tools_for_request(
    user_text: str,
    *,
    task: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    normalized_task = str(task or "").strip().lower()
    if normalized_task in _NO_TOOL_TASKS:
        return False

    meta = metadata if isinstance(metadata, dict) else {}
    classified = classification_from_metadata(meta)
    if classified is not None:
        return classified.needs_tools

    if meta.get("tools_required") is True:
        return True
    if meta.get("tools_required") is False:
        return False

    text = (user_text or "").strip().lower()
    if not text:
        return False
    if is_self_identity_question(user_text):
        return False
    if any(hint.lower() in text for hint in _TOOL_HINTS):
        return True

    schemas = meta.get("tool_schemas")
    if isinstance(schemas, list):
        for item in schemas:
            if not isinstance(item, dict):
                continue
            fn = item.get("function") if isinstance(item.get("function"), dict) else {}
            name = str(fn.get("name") or "").strip().lower()
            if any(name.startswith(prefix) for prefix in _COMMAND_TOOL_PREFIXES):
                if any(token in text for token in ("画", "抽", "忘掉", "清空", "clear", "模型")):
                    return True
    return False


def request_tier_for_metadata(
    user_text: str,
    metadata: dict[str, Any] | None = None,
) -> MoeTier:
    meta = metadata if isinstance(metadata, dict) else {}
    task = str(meta.get("task") or "llm_chat").strip().lower()
    classified = classification_from_metadata(meta)
    if classified is not None:
        return resolve_inference_tier(
            task=task,
            tier=classified.tier,
            needs_tools=classified.needs_tools,
        )
    tier = categorize_request_tier(user_text, meta)
    needs_tools = needs_tools_for_request(user_text, task=task, metadata=meta)
    return resolve_inference_tier(task=task, tier=tier, needs_tools=needs_tools)

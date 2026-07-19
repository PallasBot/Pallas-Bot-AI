# Persona 情感 Refine · API 契约

> **状态：已落地**（`POST /api/persona/affect-refine`）。  
> Bot 负责统计基线与合并；本仓做 JSON-only 批次分析（不走接话热路径、无需 Celery 回调）。

## 职责

| 层 | Bot | AI |
| --- | --- | --- |
| 词表 / civility、warmth / assertiveness 基线 | ✅ | — |
| 批次 LLM 微调 delta | 调用 + merge | ✅ 推理 + JSON 校验 |
| 接话 scorer | ✅ 读合并后 persona | — |

实现：`app/api/endpoints/persona_affect.py`、`app/services/persona_affect.py`。Bot 侧路径约为 `pallas/product/persona/group_style_refresh.py`（以主仓为准）。

## `POST /api/persona/affect-refine`

同步 JSON。`message_samples`：Bot 脱敏后最多 **12** 条、每条 ≤ **120** 字符；不含 QQ / 群号。本仓 **不**回写整份 profile。

### Request（示例）

```json
{
  "group_id": 123456789,
  "profile": {
    "sample": { "message_count": 420, "answer_count": 85, "window_hours": 168 },
    "raw": {
      "affect_tone": {
        "civility_score": -0.12,
        "harsh_msg_ratio": 0.08,
        "polite_msg_ratio": 0.05,
        "punct_aggression_avg": 0.11
      }
    },
    "derived": {
      "warmth_bias": 0.05,
      "assertiveness_bias": 0.12
    }
  },
  "hints": ["群消息偏短", "复读链与短句常见"],
  "message_samples": ["草这也太离谱了", "谢谢大佬", "？？？"]
}
```

### Response（200）

```json
{
  "warmth_delta": 0.03,
  "assertiveness_delta": 0.08,
  "confidence": 0.65,
  "summary": "语气偏直接、短句复读多",
  "triggers": []
}
```

| 字段 | 范围 | 说明 |
| --- | --- | --- |
| `warmth_delta` / `assertiveness_delta` | [-0.5, 0.5] | 叠加到 Bot `derived.*_bias` |
| `confidence` | [0, 1] | 过低时 Bot 可忽略 delta |
| `summary` | ≤ 256 字 | debug / WebUI |
| `triggers` | 可选 | 热路径命中由 Bot 侧处理 |

失败时 Bot **回退** delta=0，refresh 仍应成功。

## 配置（本仓）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `PERSONA_AFFECT_REFINE_ENABLED` | `true` | AI 侧开关 |
| `PERSONA_AFFECT_REFINE_MODEL` | 空 → 全局 LLM 默认 | 分析模型 |
| `PERSONA_AFFECT_REFINE_TIMEOUT_SEC` | `25` | 同步超时 |
| `PERSONA_AFFECT_REFINE_MAX_SAMPLES` | `12` | 与 Bot 对齐 |

Bot 侧另有 `LLM_AFFECT_REFINE_ENABLED`（总闸关时不调用）。

## 相关

- [platform-roadmap.md](platform-roadmap.md) · [runtime.md](runtime.md)

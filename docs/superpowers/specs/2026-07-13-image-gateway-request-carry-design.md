# 画画网关请求携带（多 Bot → 单 AI）

日期：2026-07-13  
状态：已批准（方案 A + 备线 B；拓展仓 draw 为源，同步 local）

## 问题

`ai_service_runtime` 下 Bot 的 `PALLAS_IMAGE_*` 与 AI `.env` 的 `IMAGE_*` 互不同步。多台 Bot 共用一台 AI 时，不能靠写 AI 配置文件。

## 决策

- Bot 在画图请求中携带 `payload.gateway.backends[]`（主网关 + 备线，顺序与插件一致）。
- AI 按该列表尝试；未携带时回退本地 `IMAGE_*`。
- 不把 Bot 配置同步进 AI `.env`。
- 改动以 `Pallas-Plugin-Draw` 为准，相关文件同步到 Bot `local/plugins/draw`（保留 local 独有 afdian 等文件）。

## 契约（摘要）

```json
"payload": {
  "prompt": "...",
  "reference_urls": [],
  "gateway": {
    "backends": [
      {
        "base_url": "https://...",
        "api_key": "...",
        "model": "...",
        "omit_response_format": false,
        "name": "optional"
      }
    ]
  }
}
```

- 密钥不写 INFO 日志全文（可打 host / backend 序号）。
- 请求携带 backends 时：不套用 AI 进程内默认 IMAGE 熔断（Bot 侧已有 circuit）；本地缺省路径仍用原熔断。
- `image_enabled`：有可用请求网关时允许执行；否则仍要求 `IMAGE_ENABLED` + 本地配置。

## 验收

1. Bot 主网关 aigateway、AI `.env` 仍为 packy → 实际上游为 aigateway。  
2. 无 gateway 旧请求 → 仍走 AI `.env`。  
3. 两 Bot 不同网关交替 → 互不污染。  
4. 备线：主网关失败时 AI 内按序尝试下一条。

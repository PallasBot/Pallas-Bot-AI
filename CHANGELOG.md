# Changelog

## [4.1.0] - 2026-08-05

### 更新公告

- 新增 `pallas-ai` 统一运维入口，可管理 API 与 media worker 的启动、状态、重启和遗留任务清理。
- API、健康检查与 API/media 启动摘要统一显示当前版本，发布时会校验 tag 与包版本一致。
- TTS 的 g2pW 改用 CPU ONNX provider，空闲时不再留下 CUDA 显存常驻。

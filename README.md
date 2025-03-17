<div align="center">

<img alt="LOGO" src="https://github.com/user-attachments/assets/fe654813-bf37-4e5f-9c7d-98d867016618" width=427 height=276/>

# Pallas-Bot-AI

<br>

Pallas-Bot AI Backend, 与 Pallas-Bot 本体解耦的 AI 功能服务端。

</div>

## 简介

使用 FastAPI HTTP Server 提供 Pallas-Bot 所需的 AI 服务接口，并使用 Celery(Redis) 创建后台任务，立即返回 `task_id`，当任务完成时，通过回调的方式推送结果。

部署方式请参考 [部署指南](./docs/Deployment.md)。

## 项目结构

- app: 项目代码
  - api: API 接口
  - core: 核心配置
  - schemas: 请求/响应模型
  - services: 业务逻辑
  - tasks: 后台任务与定时任务
  - utils: 工具
- docs: 文档
- tests: 测试

## 开发指南

TODO

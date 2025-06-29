<div align="center">

<img alt="LOGO" src="https://github.com/user-attachments/assets/fe654813-bf37-4e5f-9c7d-98d867016618" width=427 height=276/>

# Pallas-Bot-AI

<br>

Pallas-Bot AI Backend, 与 Pallas-Bot 本体解耦的 AI 功能服务端。

</div>

## 简介

使用 FastAPI HTTP Server 提供 Pallas-Bot 所需的 AI 服务接口，并使用 Celery(Redis) 创建后台任务，立即返回 `task_id`，当任务完成时，通过回调的方式推送结果。

部署方式请参考 [部署指南](./docs/Deployment.md)。

## 🚀 快速开始

### 使用预构建镜像（推荐）

```bash
# 使用最新预构建镜像
./deploy.sh --prebuilt

# 使用特定版本
./deploy.sh --prebuilt --tag v1.0.0

# 使用生产配置
./deploy.sh --prebuilt --prod
```

### 本地构建

```bash
# 本地构建并部署
./deploy.sh

# 或使用 make
make deploy
```

## 📦 Docker 镜像

项目提供了多个预构建的 Docker 镜像：

- `your-dockerhub-username/pallas-bot-ai:latest` - 最新稳定版
- `your-dockerhub-username/pallas-bot-ai:v1.0.0` - 特定版本
- `your-dockerhub-username/pallas-bot-ai:cuda12.4-latest` - 特定 CUDA 版本

### 镜像特性

- ✅ 基于 CUDA 12.4，完整 GPU 支持
- ✅ 包含所有 AI 功能（聊天、唱歌、TTS）
- ✅ 自动下载和配置模型文件
- ✅ 生产就绪的配置
- ✅ 多架构支持（AMD64）

## 🔄 CI/CD 流水线

项目配置了简化的 GitHub Actions 工作流：

### 自动化功能

- **代码质量检查**: Ruff 代码风格检查，Dockerfile 语法检查，安全扫描
- **测试构建**: Pull Request 和推送时测试 Docker 构建
- **自动推送**: 推送到主分支时自动构建并推送到 Docker Hub

### 工作流说明

1. **`ci.yml`** - 代码质量检查和测试构建
   - 在 PR 和所有分支推送时运行
   - 执行代码检查、Dockerfile 检查、测试构建、安全扫描
   
2. **`docker-build.yml`** - 构建和推送镜像
   - 仅在推送到 `main` 或 `develop` 分支时运行
   - 构建 Docker 镜像并推送到 Docker Hub

### 工作流状态

![CI Status](https://github.com/your-username/pallas-bot-ai/workflows/CI%20-%20Code%20Quality%20and%20Test%20Build/badge.svg)
![Docker Build](https://github.com/your-username/pallas-bot-ai/workflows/Docker%20Build%20and%20Push/badge.svg)

详细信息请查看：
- [GitHub Actions 使用指南](./docs/GitHub-Actions-Guide.md) 
- [Docker Hub 设置指南](./docs/DockerHub-Setup.md)

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

# Docker 部署检查清单

## 本地测试

- [ ] 运行 `docker build -t cyber-ai-festival-backend:latest .` 成功
- [ ] 运行 `docker-compose up -d` 启动所有服务
- [ ] 检查 `docker-compose logs backend` 无错误
- [ ] 执行 `curl http://localhost:8848/health` 返回 200
- [ ] 执行 `docker-compose exec backend alembic upgrade head` 数据库迁移成功
- [ ] 测试 API 端点正常工作
- [ ] 运行 `docker-compose down` 清理资源

## AWS ECR 部署

- [ ] 创建 AWS ECR 仓库
- [ ] 配置 AWS CLI 凭证
- [ ] 登录到 ECR：`aws ecr get-login-password | docker login ...`
- [ ] 构建并推送镜像：`docker build -t ...` 和 `docker push ...`
- [ ] 验证镜像在 ECR 中可见

## AWS RDS 设置

- [ ] 创建 RDS PostgreSQL 实例
- [ ] 记录 RDS 端点、用户名、密码
- [ ] 创建数据库（例如 cyber_ai_festival）
- [ ] 配置安全组允许访问
- [ ] 测试本地连接：`psql -h <rds-endpoint> -U <user> -d <database>`

## AWS ECS/Fargate 配置

### 集群设置
- [ ] 创建 ECS 集群
- [ ] 选择合适的启动类型（EC2 或 Fargate）

### 任务定义
- [ ] 创建任务定义
- [ ] 设置容器镜像（来自 ECR）
- [ ] 分配合适的 CPU 和内存
  - 最小推荐：256 CPU，512 内存
  - 生产推荐：512-1024 CPU，1024-2048 内存
- [ ] 配置环境变量：
  - [ ] DATABASE_URL
  - [ ] LOG_LEVEL
  - [ ] OPENAI_API_KEY
  - [ ] DEEPSEEK_API_KEY
- [ ] 配置日志驱动为 CloudWatch
- [ ] 设置任务角色允许访问 Secrets Manager

### 服务配置
- [ ] 创建 ECS 服务
- [ ] 设置期望的任务数量
- [ ] 配置负载均衡器（ALB）
- [ ] 配置目标组指向端口 8848
- [ ] 设置健康检查路径为 `/health`

### 网络配置
- [ ] 配置 VPC 和子网
- [ ] 配置安全组：
  - [ ] ECS 安全组允许来自 ALB 的 8000 端口
  - [ ] RDS 安全组允许来自 ECS 的 5432 端口
  - [ ] ALB 安全组允许来自互联网的 80/443 端口

## 密钥管理

- [ ] 在 AWS Secrets Manager 中创建密钥
- [ ] 更新任务定义的 valueFrom 指向 Secrets Manager
- [ ] 测试任务定义能够访问密钥

## 监控和日志

- [ ] 创建 CloudWatch 日志组：`/ecs/cyber-ai-festival-backend`
- [ ] 设置日志保留期（推荐 7-30 天）
- [ ] 创建 CloudWatch 告警：
  - [ ] 高 CPU 使用率
  - [ ] 高内存使用率
  - [ ] 任务失败
  - [ ] 错误日志

## 数据库迁移和初始化

- [ ] 连接到 ECS 任务：`aws ecs execute-command ...`
- [ ] 运行迁移：`alembic upgrade head`
- [ ] 验证数据库表已创建
- [ ] （可选）导入初始数据

## 安全检查

- [ ] 所有敏感信息都在 Secrets Manager 中
- [ ] .env 文件包含在 .gitignore 中
- [ ] Dockerfile 使用非 root 用户
- [ ] 镜像基础层是最小的（python:3.12-slim）
- [ ] 没有在镜像中包含开发依赖（仅生产依赖）
- [ ] 安全组遵循最小权限原则

## 性能优化

- [ ] 启用 ECS 任务级别的 CPU/内存自动扩展
- [ ] 配置 ALB 的连接复用
- [ ] （可选）配置 CloudFront CDN 缓存 API 响应

## 备份和灾难恢复

- [ ] 启用 RDS 自动备份（保留 7-30 天）
- [ ] 启用 RDS 多可用区部署
- [ ] 创建定期的数据库快照
- [ ] 测试从快照恢复

## 测试和验证

- [ ] 通过 ALB 端点访问 `/health` 端点
- [ ] 测试主要 API 端点
- [ ] 测试数据库连接
- [ ] 验证日志正确输出到 CloudWatch
- [ ] 进行负载测试确保性能

## 部署后清理

- [ ] 删除测试用的本地 Docker 镜像：`docker rmi cyber-ai-festival-backend:test`
- [ ] 清理 docker-compose 资源：`docker-compose down -v`
- [ ] 验证不再有本地开发资源

## 回滚计划

- [ ] 记录当前工作的镜像 SHA
- [ ] 记录当前的任务定义版本
- [ ] 如需回滚，更新 ECS 服务使用之前的任务定义版本

## 文档更新

- [ ] 更新团队文档中的 API 端点
- [ ] 记录部署配置和密钥位置
- [ ] 创建故障排查指南
- [ ] 文档化日常维护任务

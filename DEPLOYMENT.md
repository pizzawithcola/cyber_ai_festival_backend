# Cyber AI Festival Backend - Deployment Guide

## 本地 Docker 开发

### 快速启动

```bash
# 构建和启动所有服务
docker-compose up -d

# 访问应用
curl http://localhost:8848/health

# 查看日志
docker-compose logs -f backend

# 停止所有服务
docker-compose down
```

### 数据库迁移

```bash
# 执行 Alembic 迁移
docker-compose exec backend alembic upgrade head

# 创建新迁移
docker-compose exec backend alembic revision --autogenerate -m "migration description"
```

### 环境变量

复制 `.env.example` 为 `.env` 并修改相应的值：

```bash
cp .env.example .env
```

## AWS 部署指南

### 前置条件

- AWS 账户
- AWS CLI 已配置
- Docker 和 Docker Compose
- ECR 仓库已创建

### 1. 构建和推送 Docker 镜像到 ECR

```bash
# 登录到 ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.us-east-1.amazonaws.com

# 构建镜像
docker build -t cyber-ai-festival-backend:latest .

# 标记镜像
docker tag cyber-ai-festival-backend:latest <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/cyber-ai-festival-backend:latest

# 推送到 ECR
docker push <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/cyber-ai-festival-backend:latest
```

### 2. 设置 RDS PostgreSQL

1. 在 AWS Console 创建 RDS PostgreSQL 实例
2. 记录 RDS 端点和凭证
3. 更新 `.env` 中的 `DATABASE_URL`：
   ```
   DATABASE_URL=postgresql://username:password@your-rds-endpoint:5432/cyber_ai_festival
   ```

### 3. 部署到 ECS（推荐）或 Fargate

#### 使用 ECS

1. 创建 ECS 集群
2. 定义任务定义（Task Definition），指向 ECR 镜像
3. 在集群中创建服务
4. 配置负载均衡器（ALB）

#### 环境变量配置

在 ECS 任务定义中添加以下环境变量：

```json
{
  "name": "DATABASE_URL",
  "value": "postgresql://username:password@rds-endpoint:5432/cyber_ai_festival"
},
{
  "name": "LOG_LEVEL",
  "value": "INFO"
},
{
  "name": "OPENAI_API_KEY",
  "valueFrom": "arn:aws:secretsmanager:region:account:secret:openai-key"
},
{
  "name": "DEEPSEEK_API_KEY",
  "valueFrom": "arn:aws:secretsmanager:region:account:secret:deepseek-key"
}
```

### 4. 使用 AWS Secrets Manager 存储敏感信息

```bash
# 创建 OpenAI API Key 密钥
aws secretsmanager create-secret \
  --name openai-api-key \
  --secret-string "your-openai-api-key"

# 创建 DeepSeek API Key 密钥
aws secretsmanager create-secret \
  --name deepseek-api-key \
  --secret-string "your-deepseek-api-key"
```

### 5. 数据库迁移

在部署后运行迁移：

```bash
# 使用 ECS Exec（如果启用）
aws ecs execute-command \
  --cluster your-cluster-name \
  --task your-task-id \
  --container cyber-ai-festival-backend \
  --interactive \
  --command "/bin/bash"

# 在容器内运行
alembic upgrade head
```

### 6. 网络和安全配置

#### 安全组规则

**RDS 安全组**：
- Inbound: Port 5432 from ECS 安全组

**ECS/Fargate 安全组**：
- Inbound: Port 8848 from ALB 安全组
- Outbound: All traffic（或限制到特定服务）

**ALB 安全组**：
- Inbound: Port 80, 443 from 0.0.0.0/0
- Outbound: Port 8848 to ECS 安全组

#### VPC 和子网

- 将 ECS 和 RDS 部署在同一 VPC
- 使用私有子网运行数据库
- 使用公有或私有子网运行 ECS（推荐私有 + NAT Gateway）

### 7. 监控和日志

#### CloudWatch 日志

配置 ECS 任务定义的日志驱动：

```json
{
  "logDriver": "awslogs",
  "options": {
    "awslogs-group": "/ecs/cyber-ai-festival-backend",
    "awslogs-region": "us-east-1",
    "awslogs-stream-prefix": "ecs"
  }
}
```

#### 创建日志组

```bash
aws logs create-log-group --log-group-name /ecs/cyber-ai-festival-backend --region us-east-1
```

### 8. 自动扩展（可选）

```bash
# 注册可扩展目标
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/your-cluster/your-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 10

# 创建扩展策略
aws application-autoscaling put-scaling-policy \
  --policy-name cpu-scaling \
  --service-namespace ecs \
  --resource-id service/your-cluster/your-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

### 9. CI/CD 集成（GitHub Actions 示例）

创建 `.github/workflows/deploy.yml`：

```yaml
name: Build and Deploy to AWS

on:
  push:
    branches: [main]

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: cyber-ai-festival-backend
  ECS_SERVICE: cyber-ai-festival-service
  ECS_CLUSTER: cyber-ai-festival-cluster
  ECS_TASK_DEFINITION: cyber-ai-festival-task

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        run: |
          aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.$AWS_REGION.amazonaws.com

      - name: Build Docker image
        run: docker build -t $ECR_REPOSITORY:${{ github.sha }} .

      - name: Push to ECR
        run: |
          docker tag $ECR_REPOSITORY:${{ github.sha }} ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:${{ github.sha }}
          docker push ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:${{ github.sha }}

      - name: Update ECS service
        run: |
          aws ecs update-service \
            --cluster $ECS_CLUSTER \
            --service $ECS_SERVICE \
            --force-new-deployment
```

## 故障排查

### 检查服务状态

```bash
# 检查 ECS 任务
aws ecs list-tasks --cluster your-cluster-name

# 查看任务详情
aws ecs describe-tasks --cluster your-cluster-name --tasks <task-id>

# 查看日志
aws logs tail /ecs/cyber-ai-festival-backend --follow
```

### 常见问题

1. **数据库连接失败**
   - 检查 RDS 安全组规则
   - 验证 DATABASE_URL 格式
   - 检查 RDS 实例状态

2. **镜像拉取失败**
   - 验证 ECR 仓库权限
   - 检查 ECS 任务角色权限

3. **应用无法启动**
   - 查看 CloudWatch 日志
   - 验证环境变量配置
   - 检查数据库迁移是否完成

## 健康检查

应用提供 `/health` 端点用于健康检查：

```bash
curl http://localhost:8848/health
```

## 性能优化

1. **使用 RDS 多可用区部署**提高可靠性
2. **启用 RDS 自动备份**
3. **配置 CloudFront CDN**加速 API 响应
4. **使用 ElastiCache**缓存热门数据（可选）
5. **启用 ALB 连接复用**减少延迟

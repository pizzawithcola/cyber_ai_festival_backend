# Cyber AI Festival Backend - AWS Architecture

## Overview

This document describes the AWS infrastructure architecture for the Cyber AI Festival Backend application, deployed using AWS ECS Fargate with Application Load Balancer (ALB) and RDS PostgreSQL.

## Architecture Diagram

```mermaid
graph TB
    subgraph Internet["🌐 Internet"]
        Client[用户浏览器 / 客户端]
    end

    subgraph AWS["AWS ap-south-1 (孟买, 亚太-孟买)"]
        subgraph VPC["VPC (vpc-0dda76b286c45fc27)"]
            subgraph PublicSubnet["公有子网 (负载均衡器)"]
                ALB[ALB<br/>cyber-ai-festival-alb<br/>Port: 80, 443]
            end
            
            subgraph PrivateSubnet["私有子网 (2个可用区)"]
                ECS[ECS Fargate Task<br/>FastAPI + Uvicorn<br/>Container Port: 8848<br/>CPU: 512, Memory: 1024]
            end
        end
        
        RDS[(RDS PostgreSQL 16.13<br/>db.t3.micro<br/>20GB SSD<br/>cyber-ai-festival-db)]
        
        ECR["ECR Registry<br/>cyber-ai-festival-backend<br/>866730904414.dkr.ecr.ap-south-1.amazonaws.com"]
        
        Secrets["Secrets Manager<br/>cyber-ai-festival/db-password<br/>cyber-ai-festival/deepseek-api-key"]
        
        CloudWatch["CloudWatch Logs<br/>/ecs/cyber-ai-festival-backend"]
    end

    subgraph SecurityGroups["安全组 (Security Groups)"]
        ECS_SG["ECS SG (sg-0917a0a8d60605c64)<br/>Port 8848 入站 ← ALB"]
        RDS_SG["RDS SG (sg-00d621014ad070b66)<br/>Port 5432 入站 ← ECS SG"]
    end

    Client -->|"HTTPS :443"| ALB
    ALB -->|"HTTP :8848"| ECS
    ECS -->|"SSL :5432"| RDS
    ECS -->|"读取密码"| Secrets
    ECS -->|"日志"| CloudWatch
    ECR -->|"Docker Image"| ECS
    
    ALB --- ECS_SG
    ECS --- ECS_SG
    ECS_SG --> RDS_SG
    RDS --> RDS_SG
```

## AWS Resources Summary

| Resource Type | Resource Name | Details |
|--------------|---------------|---------|
| **Region** | ap-south-1 | 亚太-孟买 (Asia Pacific - Mumbai) |
| **VPC** | vpc-0dda76b286c45fc27 | 虚拟私有云 |
| **ECS Cluster** | cyber-ai-festival-cluster | Fargate 集群 |
| **ECS Service** | cyber-ai-festival-service | 托管服务 |
| **ECS Task Definition** | cyber-ai-festival-task:6 | 最新版本 |
| **ALB** | cyber-ai-festival-alb | 应用负载均衡器 |
| **Target Group** | cyber-ai-festival-tg | ALB 目标组 |
| **RDS** | cyber-ai-festival-db | PostgreSQL 16.13 |
| **ECR** | cyber-ai-festival-backend | Docker 镜像仓库 |
| **Secrets Manager** | cyber-ai-festival/* | 密码存储 |
| **CloudWatch** | /ecs/cyber-ai-festival-backend | 日志组 |

## Component Details

### 1. Application Load Balancer (ALB)

| Property | Value |
|----------|-------|
| DNS Name | `cyber-ai-festival-alb-2006617150.ap-south-1.elb.amazonaws.com` |
| Type | Application (Layer 7) |
| VPC | vpc-0dda76b286c45fc27 |
| Ports | 80 (HTTP), 443 (HTTPS) |
| Target Group | cyber-ai-festival-tg |
| Health Check Path | `/health` |
| Health Check Interval | 30 seconds |
| Healthy Threshold | 5 consecutive successes |
| Unhealthy Threshold | 2 consecutive failures |

**作用**：ALB 是用户流量的唯一入口，负责：
- 将请求分发到 ECS 任务
- 自动健康检查，自动剔除不健康的容器
- 提供高可用性（多个可用区）

### 2. ECS Fargate

| Property | Value |
|----------|-------|
| Cluster | cyber-ai-festival-cluster |
| Service | cyber-ai-festival-service |
| Task Definition | cyber-ai-festival-task:6 |
| Launch Type | FARGATE |
| Platform Version | LATEST |
| Desired Count | 1 |
| CPU | 512 (0.5 vCPU) |
| Memory | 1024 MB (1 GB) |
| Container Port | 8848 |
| Network Mode | awsvpc |
| Docker Image | 866730904414.dkr.ecr.ap-south-1.amazonaws.com/cyber-ai-festival-backend:latest |

**容器配置**：
- 非 root 用户运行 (`appuser`, UID 1000)
- 环境变量：
  - `DATABASE_URL`: PostgreSQL 连接字符串
  - `DEEPSEEK_API_KEY`: LLM API 密钥
  - `LOG_LEVEL`: 日志级别
- 健康检查：HTTP GET `/health`

### 3. RDS PostgreSQL

| Property | Value |
|----------|-------|
| Instance ID | cyber-ai-festival-db |
| Engine | PostgreSQL 16.13 |
| Instance Class | db.t3.micro |
| Storage | 20 GB (SSD) |
| VPC | vpc-0dda76b286c45fc27 |
| Publicly Accessible | No (私有) |
| Multi-AZ | No |
| SSL Required | Yes |
| Master Username | postgres |
| Database Name | postgres |
| Port | 5432 |

**连接字符串格式**：
```
postgresql://postgres:{password}@cyber-ai-festival-db.ctao8iuy2toz.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require
```

### 4. ECR Repository

| Property | Value |
|----------|-------|
| Repository Name | cyber-ai-festival-backend |
| Registry ID | 866730904414 |
| URI | 866730904414.dkr.ecr.ap-south-1.amazonaws.com/cyber-ai-festival-backend |
| Image Tag | latest |

### 5. Secrets Manager

| Secret Name | Description |
|-------------|-------------|
| `cyber-ai-festival/db-password` | RDS 数据库密码 |
| `cyber-ai-festival/deepseek-api-key` | DeepSeek LLM API 密钥 |

### 6. CloudWatch Logs

| Property | Value |
|----------|-------|
| Log Group | /ecs/cyber-ai-festival-backend |
| Retention | Never expire (默认) |

**日志格式**：
```
{timestamp} | {level} | app | {message}
2026-03-24 15:09:48 | INFO | app | Database tables ready
```

## Security Groups

### ECS Security Group (sg-0917a0a8d60605c64)
| Type | Protocol | Port | Source |
|------|----------|------|--------|
| Custom TCP | TCP | 8848 | ALB (通过 SG reference) |

### RDS Security Group (sg-00d621014ad070b66)
| Type | Protocol | Port | Source |
|------|----------|------|--------|
| Custom TCP | TCP | 5432 | ECS SG (sg-0917a0a8d60605c64) |

**流量方向**：用户 → ALB → ECS (8848) → RDS (5432)

## Data Flow

```
1. 用户请求
   Client → ALB DNS → ALB

2. 负载均衡
   ALB → 健康检查 /health → ECS Task

3. 应用处理
   ECS Task → 读取 Secrets Manager → 连接 RDS

4. 数据库操作
   ECS Task → SSL Connection → RDS PostgreSQL

5. 日志记录
   ECS Task → CloudWatch Logs
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | 健康检查 |
| POST | `/users/login` | 用户登录 |
| POST | `/users/` | 创建用户 |
| GET | `/users/` | 列出所有用户 |
| GET | `/users/{id}` | 获取用户详情 |
| PUT | `/users/{id}` | 更新用户 |
| DELETE | `/users/{id}` | 删除用户 |
| GET | `/users/userscores` | 获取所有用户及分数 |
| GET | `/scores/` | 列出所有分数 |
| POST | `/scores/` | 创建/更新分数 |
| GET | `/scores/{id}` | 获取分数详情 |
| GET | `/rankings/` | 获取排行榜 |
| POST | `/llm/chat` | LLM 对话 |

**Swagger UI**: `http://{ALB_DNS}/docs`

## Deployment Commands

### 构建并推送 Docker 镜像

```bash
# 1. 构建镜像 (Apple Silicon Mac 需要指定 amd64)
docker buildx build \
  --platform linux/amd64 \
  --no-cache \
  --load \
  -t cyber-ai-festival-backend:latest .

# 2. 打标签
docker tag cyber-ai-festival-backend:latest \
  866730904414.dkr.ecr.ap-south-1.amazonaws.com/cyber-ai-festival-backend:latest

# 3. 推送到 ECR
docker push 866730904414.dkr.ecr.ap-south-1.amazonaws.com/cyber-ai-festival-backend:latest
```

### 更新 ECS 服务

```bash
# 1. 注册新的 task definition
aws ecs register-task-definition \
  --cli-input-json file:///tmp/td_user.json \
  --region ap-south-1

# 2. 更新服务使用新版本
aws ecs update-service \
  --cluster cyber-ai-festival-cluster \
  --service cyber-ai-festival-service \
  --task-definition cyber-ai-festival-task:6 \
  --region ap-south-1
```

### 查看日志

```bash
# 最近 100 行
aws logs tail /ecs/cyber-ai-festival-backend --region ap-south-1

# 实时监控
aws logs tail /ecs/cyber-ai-festival-backend --follow --region ap-south-1

# 按时间过滤
aws logs filter-log-events \
  --log-group-name /ecs/cyber-ai-festival-backend \
  --start-time $(date -v-1H +%s000) \
  --region ap-south-1
```

### 查看服务状态

```bash
# ECS 服务状态
aws ecs describe-services \
  --cluster cyber-ai-festival-cluster \
  --services cyber-ai-festival-service \
  --region ap-south-1

# ALB 目标健康状态
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:ap-south-1:866730904414:targetgroup/cyber-ai-festival-tg/1b3727dc0db8460f \
  --region ap-south-1
```

## Troubleshooting

### 常见问题

1. **任务启动失败**
   - 检查 CloudWatch 日志是否有启动错误
   - 确认 DATABASE_URL 格式正确
   - 确认 RDS 安全组允许 ECS 访问

2. **ALB 健康检查失败**
   - 确认容器端口是 8848
   - 确认 `/health` 路径返回 200
   - 检查任务是否在 30 秒内启动完成

3. **数据库连接失败**
   - 确认密码正确（在 Secrets Manager 中查看）
   - 确认用户名是 `postgres` 而非 `postgre`
   - 确认连接字符串包含 `sslmode=require`

### 调试命令

```bash
# 查看任务详情
aws ecs describe-tasks \
  --cluster cyber-ai-festival-cluster \
  --tasks {task_id} \
  --region ap-south-1

# 查看 RDS 密码
aws secretsmanager get-secret-value \
  --secret-id cyber-ai-festival/db-password \
  --region ap-south-1

# 测试 RDS 连接 (从 ECS 环境)
nc -zv cyber-ai-festival-db.ctao8iuy2toz.ap-south-1.rds.amazonaws.com 5432
```

## Cost Estimation

| Resource | Configuration | Estimated Monthly Cost (USD) |
|----------|---------------|----------------------------|
| ECS Fargate | 0.5 vCPU, 1 GB | ~$15-20 |
| ALB | Application LB | ~$20-25 |
| RDS db.t3.micro | 20 GB | ~$15-20 |
| Data Transfer | Varies | ~$5-10 |
| **Total** | | **~$55-75/month** |

## Future Improvements

- [ ] 启用 RDS Multi-AZ 以提高可用性
- [ ] 配置 RDS 自动备份
- [ ] 添加 CloudFront CDN 加速
- [ ] 启用 WAF 防护
- [ ] 配置自动扩缩容
- [ ] 使用 Parameter Store 替代部分环境变量

---

*Last Updated: 2026-03-24*

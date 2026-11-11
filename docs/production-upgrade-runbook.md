# 生产升级 Runbook

面向熟悉 Docker、PostgreSQL 和本仓库部署流程的运维人员。

本文用于把已经验证过的应用版本安全切换到已有生产数据库。首次建库请先看 README 的“切换生产环境”章节。

## 0. 硬边界

- 生产不使用 `SEED_ON_STARTUP=true`。
- 多副本部署时只允许一个迁移任务执行 `alembic upgrade head`。
- 数据库备份和附件存储备份必须成对处理。
- 不执行 `docker compose down -v`；这会删除 PostgreSQL 和附件数据卷。
- 业务库、应用更新与本 runbook 的技术步骤分开审批；迁移失败时停止，不靠重启掩盖。

## 1. 升级前确认

```bash
git fetch origin main
git rev-parse origin/main
git show --stat --oneline origin/main
docker compose --profile full config --quiet
docker compose --profile full ps
docker compose logs --tail 100 api
docker compose logs --tail 100 worker
```

记录目标提交、当前应用版本、数据库、UTC 变更窗口、执行人与回退负责人。

生产 `.env` 至少确认：

```dotenv
SECRET_KEY=<随机强密钥>
ALLOW_DEV_SECRET=false
SEED_ON_STARTUP=false
AUTO_MIGRATE=false
POSTGRES_PASSWORD=<强口令>
CORS_ORIGINS=https://pms.example.com
```

确认当前没有另一个迁移任务、持续 5xx、数据库连接失败或高风险批量写入。

## 2. 备份

### 2.1 PostgreSQL

```bash
mkdir -p backups
pg_dump --format=custom \
  --file="backups/logix-pms-$(date -u +%Y%m%dT%H%M%SZ).dump" \
  "$DATABASE_URL"
```

或从 Compose 数据库容器执行：

```bash
docker compose exec -T db pg_dump \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "backups/logix-pms-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

确认备份文件存在、大小合理，并在独立临时数据库抽查恢复；不要将恢复操作指向生产库。

### 2.2 附件

本地附件卷按当前部署方式备份，例如：

```bash
docker run --rm \
  --volumes-from logix-pms-api \
  -v "$PWD/backups:/backup" \
  alpine sh -c 'tar czf /backup/logix-pms-attachments-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /app/var attachments'
```

对象存储按其版本化/复制策略备份，并记录时间点。数据库元数据和附件对象必须成对保留。

## 3. 停写与构建

```bash
docker compose --profile full stop api worker
```

保留数据库容器运行；必要时由反向代理切换维护页。

切换到目标提交并构建不可变镜像：

```bash
git checkout <target-commit-or-release-tag>
docker compose --profile full build api worker
docker compose --profile full config --images
```

多副本环境不要让多个 API 实例同时执行迁移。

## 4. 单独执行迁移

先确认数据库健康：

```bash
docker compose ps db
docker compose exec db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

只由一个发布任务执行：

```bash
docker compose run --rm --no-deps api python -m alembic upgrade head
docker compose run --rm --no-deps api python -m alembic check
```

应看到：

```text
No new upgrade operations detected.
```

把完整输出和退出码保存到发布记录。即使本次无迁移，也必须执行检查。

## 5. 启动与健康检查

```bash
docker compose --profile full up -d api worker
docker compose --profile full ps
docker compose logs --tail 100 api
docker compose logs --tail 100 worker
curl --fail --silent --show-error http://127.0.0.1:8123/health
```

确认 API/worker 使用目标版本、数据库连接成功、没有迁移异常或持续 5xx，附件存储可读写。

## 6. 最小业务验收

使用低风险流程和只读账号检查：

1. 管理员登录；
2. 打开已发布流程和“绑定”页；
3. 打开执行“上线准备”；
4. 打开岗位责任书历史版本；
5. 打开员工手册预览/固定版本；
6. 点击固定原依据，确认版本与组织范围正确；
7. 用 viewer 验证只能读，不能生成、审批或修改；
8. 验证缺 RACI-A 的流程可发布模型，但不能通过正式使用门禁；
9. 检查关键 API 无 500、页面无 JS 异常。

验收失败时保留日志、响应和镜像身份，进入回滚判断，不反复重启掩盖问题。

## 7. 回滚

### 7.1 应用回滚

如果数据库结构与上一应用兼容：

```bash
docker compose --profile full stop api worker
# 切换到上一版本代码或不可变镜像
docker compose --profile full up -d api worker
```

先核对旧应用支持当前数据库版本。

### 7.2 数据库回滚

不要未经批准直接执行：

```bash
alembic downgrade -1
```

稳妥流程：停止写入，保留升级后数据库与日志，用升级前 dump 恢复到独立数据库，核对窗口内新增数据，再按批准方案切换。数据库和附件必须按同一时间点恢复。

### 7.3 回滚验收

重复健康检查和最小业务验收，确认 API/worker 版本、数据库版本、文档/手册/附件读取和 viewer 权限均正常。

## 8. 完成记录

```text
目标提交/镜像：
迁移前版本：
迁移后版本：
数据库备份：
附件备份/对象版本：
迁移输出：
健康检查：
业务验收：
异常与处理：
执行人：
完成时间（UTC）：
```

不要把数据库连接串、密码、token 或备份内容写入仓库、PR、普通日志或聊天记录。

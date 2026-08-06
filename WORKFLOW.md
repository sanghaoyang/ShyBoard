# Workbench · 长期任务工作流协议（Agent 接入标准）

> 目的：让任何 AI Agent（Hermes / Claude / 其他）都能把"CLI 下达的长期任务"
> 自动纳入工作台管理——创建、更新进展、改状态，全程可追溯。
> 这套协议只依赖工作台的本地 REST API，不依赖任何特定 Agent。

---

## 一、前提

工作台服务在运行（双击 Workbench.exe 或 `pythonw app.py`），监听 127.0.0.1。
实际端口写在 `data/port.txt`（默认 17890）。

```
BASE=http://127.0.0.1:$(cat data/port.txt)    # 或直接 http://127.0.0.1:17890
```

### 快速检查服务是否在运行

```bash
curl -s http://127.0.0.1:17890/api/health
# 期望: {"ok":true,"service":"workbench"}
```

服务没起来 → 先启动（工作台目录下）：

```bash
# 打包版：双击 Workbench.exe
# 源码版：
pythonw app.py          # 或 python app.py（会自动后台化）
```

### 我的 AI 怎么发现这份文档？（关键）

文档本身不会自动跑到 AI 脑子里。按你的 AI 类型选择：

- **Hermes**：把 `workbench` skill（productivity 类）装到目标 profile——skill 加载即自动遵循本协议；或把 WORKFLOW.md 路径写进任务的 context
- **Claude Code / Codex / Cursor 等**：把 WORKFLOW.md 放进项目根目录（如 `AGENTS.md` / `CLAUDE.md` 引用它），AI 读项目文档时自动发现
- **通用做法**：用户在下达长期任务时，顺口说一句"按 WORKFLOW.md 记到工作台"；或把文档内容直接贴给 AI 作为上下文

## 二、哪些任务该入账（判断标准）

满足**任一**条件即自动创建到工作台：

| 条件 | 例子 |
|------|------|
| 用户明确要求跟踪 | "记到工作台"、"建个任务" |
| 需要跨会话/跨天完成 | "完善工作台（长期）" |
| 多步骤、需要记录进展 | "迁移服务器 + 配置 + 验证" |
| 非临时性的长期事项 | 任何"以后还要做"的事 |

不满足（一次性请求）不入账：查信息、改个配置、回答个问题。

## 三、接口速查（任务相关）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/tasks | 创建任务 |
| GET  | /api/tasks | 列表（?status=todo\|doing\|done 过滤） |
| GET  | /api/tasks/{id} | 详情（含 events 时间线） |
| PATCH | /api/tasks/{id} | 更新 title/description/status/priority/due_date/tags |
| DELETE | /api/tasks/{id} | 删除 |

创建字段：title(必填), description, status(todo/doing/done), priority(low/medium/high),
due_date(YYYY-MM-DD), tags(数组或逗号串), source(**agent**——UI 会显示 🤖 标记)

## 四、标准流程（四步）

### 1. 创建任务
```bash
curl -s -X POST $BASE/api/tasks -H "Content-Type: application/json" -d '{
  "title": "完善工作台",
  "description": "长期任务：持续迭代功能、UI、稳定性、可移植性。",
  "priority": "high",
  "tags": ["长期", "项目"],
  "source": "agent"
}'
```
响应里有 `id`，后续用它。

### 2. 开始做 → 标记进行中
```bash
curl -s -X PATCH $BASE/api/tasks/<id> -H "Content-Type: application/json" -d '{"status":"doing"}'
```

### 3. 更新进展 → 修改描述追加进展行
```bash
curl -s -X PATCH $BASE/api/tasks/<id> -H "Content-Type: application/json" -d '{
  "description": "长期任务：持续迭代工作台。\n\n📌 当前进展：\n- [2026-08-06] 完成了X\n- [2026-08-07] 处理了Y"
}'
```
约定：描述分两部分——第一段是任务目标（保持不变），第二段 `📌 当前进展：` 后面按时间追加。
每次 PATCH 都会在时间线上自动记录"描述：旧值 → 新值"（UI 悬停可看红绿对比）。

### 4. 完成 → 标记已完成
```bash
curl -s -X PATCH $BASE/api/tasks/<id> -H "Content-Type: application/json" -d '{"status":"done"}'
```

### 状态流转全景
```
todo ──▶ doing ──▶ done
  ▲                  │
  └──── 恢复 ◀───────┘
```
每次流转自动记录事件与时间戳，UI 时间线完整可见。

## 五、进展记录为什么用"改描述"

- PATCH description 触发系统级 update 事件，**自动保存旧值→新值**，天然形成变更日志
- 无需单独"评论"接口，零额外设计，时间线 + hover 细节已经覆盖
- 状态流转有独立事件，和进展更新不混淆

## 六、验证是否成功

```bash
curl -s $BASE/api/tasks/<id>    # 详情：应包含你设置的字段 + events 时间线
```
- 创建：返回 201 + id；失败返回 4xx + {"error": "..."}
- 状态流转/更新：返回 200 + 任务对象
- 时间线 events 里应有：create → status(doing) → update(描述) 等记录

## 七、错误处理

| 现象 | 原因 | 处理 |
|------|------|------|
| 连接拒绝 / 超时 | 服务没启动或端口不对 | 先跑 health 检查；看 data/port.txt 实际端口 |
| 404 任务不存在 | id 打错 | GET /api/tasks 看真实 id |
| 400 参数错误 | title 为空 / status 非法 | 检查字段名（title/description/status/priority/due_date/tags/source） |
| 中文变空 / 乱码 | shell 编码问题 | 用 Python urllib（见下节） |

## 八、中文发送注意事项

**不要**用 shell 直接拼中文 JSON（MSYS/bash 会乱码导致 title 为空）。
用 Python（推荐）：
```python
import json, urllib.request
body = json.dumps({"title": "中文任务"}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(BASE + "/api/tasks", data=body,
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as r:
    print(r.status, r.read().decode("utf-8"))
```
或把中文写成 `\uXXXX` 转义后放 JSON 里。

## 九、给非 Hermes Agent 的提示

- 协议就是上面四步，HTTP 接口通用，任何能发 HTTP 请求的 agent 都能实现
- 判断"要不要入账"的标准见第二节，建议写进你自己 agent 的系统提示词/skill
- 工作台侧栏会实时显示 🤖 标记的任务；时间线是 agent 行为的完整审计记录
- 想重置演示数据：`./.venv/Scripts/python scripts/seed_demo.py`

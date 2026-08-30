# ShyBoard · 长期任务工作流协议（Agent 接入标准）

> 目的：让任何 AI Agent（Hermes / Claude / 其他）都能把"CLI 下达的长期任务"
> 自动纳入工作台管理——创建、更新进展、改状态，全程可追溯。
> 这套协议优先使用目录内置的标准 MCP Bridge；REST API 仍可作为通用备用方案，均不依赖特定 Agent。

---

## 一、前提

工作台服务在运行（双击 ShyBoard.exe 或 `pythonw app.py`），监听 127.0.0.1。
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
# 打包版：双击 ShyBoard.exe
# 源码版：
pythonw app.py          # 或 python app.py（会自动后台化）
```

### 我的 AI 怎么发现这份文档？（关键）

文档本身不会自动跑到 AI 脑子里。按你的 AI 类型选择：

- **Hermes**：把 `ShyBoard` skill（productivity 类）装到目标 profile——skill 加载即自动遵循本协议；或把 WORKFLOW.md 路径写进任务的 context
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

## 三、MCP 首次接入（推荐）

在 ShyBoard 左侧打开“AI 接入”，复制 MCP 安装提示词，让 Agent 自动识别安装目录并按当前产品的规范完成配置。手动配置时，将 `mcp-config.example.json` 中的命令改为便携包内 `ShyBoard-MCP.exe` 的绝对路径。Bridge 使用 stdio 启动，不需要端口。

在项目根目录调用一次 `shyboard_link_project`，随后每次会话先调用
`shyboard_get_project_context`。项目根目录的 `.shyboard/project.json` 是跨 Agent、跨会话的
轻量身份文件；任务和进度仍统一存储在 ShyBoard 的 `data/workbench.db`。

MCP 工具与下方 REST 步骤一一对应：`shyboard_create_task`、`shyboard_set_task_status`、
`shyboard_append_progress`、`shyboard_edit_progress`、`shyboard_delete_progress`。Agent 可在
`append_progress` 中填写 `agent_id`、`run_id`，并使用稳定的 `record_id` 保证重试幂等。

## 四、接口速查（任务相关）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/tasks | 创建任务 |
| GET  | /api/tasks | 列表（?status=todo\|doing\|done 过滤） |
| GET  | /api/tasks/{id} | 详情（含 events 时间线） |
| PATCH | /api/tasks/{id} | 更新 title/description/status/priority/due_date/tags |
| DELETE | /api/tasks/{id} | 删除 |
| GET | /api/tasks/{id}/progress | 获取进度记录 |
| POST | /api/tasks/{id}/progress | 创建进度记录 |
| PATCH | /api/progress/{id} | 编辑进度记录 |
| DELETE | /api/progress/{id} | 删除进度记录 |

创建字段：title(必填), description, status(todo/doing/done), priority(low/medium/high),
due_date(YYYY-MM-DD), tags(数组或逗号串), source(**agent**——UI 会显示 🤖 标记)

## 五、标准流程（四步）

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

### 3. 更新进展 → 创建独立进度记录
```bash
curl -s -X POST $BASE/api/tasks/<id>/progress -H "Content-Type: application/json" -d '{
  "content": "完成了设置页面重构，并通过界面验证。",
  "source": "agent",
  "agent_id": "codex",
  "run_id": "session-20260827",
  "record_id": "session-20260827-step-1"
}'
```
`record_id` 是幂等键：Agent 重试同一个请求不会生成重复进度。任务描述继续只保存任务目标，进度记录可单独编辑或删除。

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

## 六、进展记录为什么使用独立接口

- 打开任务时描述区域保持为空，不会把历史进展重新塞进输入框
- 每条进度可单独编辑、删除，并记录 Agent 与会话来源
- `record_id` 支持安全重试，避免网络重连造成重复写入
- 系统字段修改时间线与人工/Agent 进度历史相互独立，更容易阅读

## 七、验证是否成功

```bash
curl -s $BASE/api/tasks/<id>    # 详情：应包含你设置的字段 + events 时间线
```
- 创建：返回 201 + id；失败返回 4xx + {"error": "..."}
- 状态流转/更新：返回 200 + 任务对象
- `events` 中包含任务字段与状态变更；`GET /api/tasks/<id>/progress` 返回独立进度历史

## 八、错误处理

| 现象 | 原因 | 处理 |
|------|------|------|
| 连接拒绝 / 超时 | 服务没启动或端口不对 | 先跑 health 检查；看 data/port.txt 实际端口 |
| 404 任务不存在 | id 打错 | GET /api/tasks 看真实 id |
| 400 参数错误 | title 为空 / status 非法 | 检查字段名（title/description/status/priority/due_date/tags/source） |
| 中文变空 / 乱码 | shell 编码问题 | 用 Python urllib（见下节） |

## 九、中文发送注意事项

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

## 十、给非 Hermes Agent 的提示

- 协议就是上面四步，HTTP 接口通用，任何能发 HTTP 请求的 agent 都能实现
- 判断"要不要入账"的标准见第二节，建议写进你自己 agent 的系统提示词/skill
- 工作台侧栏会实时显示 🤖 标记的任务；时间线是 agent 行为的完整审计记录

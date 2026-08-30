# ShyBoard

ShyBoard 是一个面向 Windows 的本地个人工作台，把任务、进度记录、日历、日记、便签和常用链接放在同一个桌面应用里。

它不需要注册账号，主要数据保存在应用目录内的 SQLite 数据库中。整个便携目录可以直接复制、压缩和迁移。

## 当前功能

- 任务看板：待办、进行中、已完成三种状态
- 任务信息：优先级、截止日期、标签、描述和来源标记
- 进度记录：为每个任务单独追加、编辑或删除历史进度
- 操作确认：删除任务、切换完成状态等确认项可在设置中控制
- 日历：公历、农历、节气、常见节假日和自定义纪念日
- 每日记录：在日历中编辑并查看每天的内容
- 便签与快捷方式
- 天气、番茄钟和多套界面主题
- 定时任务：每周/每月重复规则、提前提醒、日历投射和完成历史
- 独立设置页面
- Agent 接入：标准 MCP Bridge 和本地 REST API

## 下载

在 GitHub 仓库的 [Releases](../../releases) 页面下载最新的 `ShyBoard-Portable.zip`。便携版不需要安装，解压后直接运行即可。

如果暂时没有可用的 Release，也可以在仓库右侧选择 **Code → Download ZIP** 获取源码，再按“从源码运行”一节启动；源码包不包含任何个人数据库或运行时数据。

下载并解压后：

1. 保持 `ShyBoard.exe`、`ShyBoard-MCP.exe` 和 `_internal/` 位于同一个目录。
2. 双击 `ShyBoard.exe` 启动桌面工作台。
3. 首次使用 Agent 时，打开左侧“AI 接入”，复制安装提示词交给你的 Agent；如果只使用桌面功能，可以跳过这一步。

便携目录可以直接移动到另一台 Windows 电脑。升级时替换程序文件即可，`data/` 目录应当保留。

## 直接使用

便携版目录结构如下：

```text
ShyBoard/
├── ShyBoard.exe
├── _internal/
├── data/                 # 首次运行后生成，用于保存本机数据
├── ShyBoard-MCP.exe
└── update.ps1
```

解压完整目录后双击 `ShyBoard.exe` 即可运行。

不要只复制 `ShyBoard.exe`。程序运行还需要同目录下的 `_internal` 等文件。如果要放到桌面，请为 `ShyBoard.exe` 创建快捷方式，或把整个目录一起复制过去。

个人数据保存在：

```text
data/workbench.db
```

备份或迁移时，复制整个 ShyBoard 目录即可。

## MCP Agent 接入

ShyBoard 提供“直接连接”和 MCP 两种 Agent 接入方式，选择一种即可。普通用户可以在应用左侧打开“AI 接入”，复制提示词让 Agent 自动完成发现或配置，不需要手动查找端口。

便携包内置独立的 `ShyBoard-MCP.exe`。支持 MCP 的 Agent 可以通过它创建任务、更新状态和写入进度；完成首次配置后，不要求 ShyBoard 窗口保持打开。

通用 Windows 配置形式：

```json
{
  "mcpServers": {
    "shyboard": {
      "command": "<ShyBoard 安装目录>\\ShyBoard-MCP.exe",
      "args": []
    }
  }
}
```

应用内的安装提示词会让 Agent 从正在运行的 ShyBoard 自动识别实际路径，并根据当前 Agent 产品的配置规范安全地添加该服务。

首次关联一个项目时，Agent 调用：

```text
shyboard_link_project
```

该操作会在目标项目根目录创建：

```text
.shyboard/project.json
```

这个文件只保存项目 ID 和项目名称。之后无论更换 Agent、开启新会话还是重新打开项目，都可以先调用 `shyboard_get_project_context`，一次读取该项目的任务和最近进度。

主要 MCP 工具：

| 工具 | 用途 |
| --- | --- |
| `shyboard_link_project` | 登记并关联项目 |
| `shyboard_get_project_context` | 获取项目任务和最近进度 |
| `shyboard_list_tasks` | 查询项目任务 |
| `shyboard_create_task` | 创建任务 |
| `shyboard_update_task` | 修改任务字段 |
| `shyboard_set_task_status` | 切换状态，可同时追加进度 |
| `shyboard_append_progress` | 新增进度记录 |
| `shyboard_edit_progress` | 编辑进度记录 |
| `shyboard_delete_progress` | 删除进度记录 |

`record_id` 可用于幂等写入，防止 Agent 重试时生成重复进度；`agent_id` 和 `run_id` 可用于区分 Agent 与会话来源。

MCP Bridge 使用 stdio 与 Agent 通信，最终仍然读写 ShyBoard 的本地 `data/workbench.db`。桌面界面、MCP 和 REST API 看到的是同一份数据。

更完整的 Agent 工作流见 [WORKFLOW.md](WORKFLOW.md)。

## 从源码运行

需要 Python 3.11，推荐使用 `uv`：

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.\start.bat
```

仅启动本地服务：

```powershell
.\.venv\Scripts\python.exe app.py --no-window
```

默认监听 `127.0.0.1:17890`。如果端口被占用，会自动选择后续可用端口，并写入 `data/port.txt`。

## 构建便携版

运行：

```powershell
.\build_portable.bat
```

构建结果位于：

```text
dist/ShyBoard-Portable/
```

分发时应压缩整个 `ShyBoard-Portable` 目录，而不是单独发送 EXE。

## 测试

检查 Python 文件：

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py server.py db.py mcp_server.py
```

验证 MCP 工具：

```powershell
.\.venv\Scripts\python.exe scripts\test_mcp.py
```

MCP 测试使用临时数据库，不会修改用户数据。

## 数据和隐私

- 数据默认只保存在本机
- Web 服务只监听 `127.0.0.1`
- MCP 使用本地子进程通信，不开放网络端口
- `data/`、`.venv/`、构建缓存和个人数据库不会提交到 Git
- 天气功能需要访问天气数据源；其他核心功能可离线使用

## 仓库结构

```text
ShyBoard-source/
├── app.py                    # 桌面窗口和启动入口
├── server.py                 # 本地 REST API 与静态页面服务
├── db.py                     # SQLite 数据层和迁移
├── mcp_server.py             # MCP Bridge
├── run_mcp.bat               # MCP 启动脚本
├── static/                   # 前端页面、样式和交互
├── services/                 # 天气、图标和更新服务
├── scripts/                  # API/MCP 测试和城市表生成器
├── build_portable.bat        # 便携版构建入口
├── ShyBoardPortable.spec     # PyInstaller 配置
└── requirements.txt
```

当前版本：`0.1.0`

# ShyBoard

一个简单好用的本地个人工作台：任务管理（待办 / 进行中 / 已完成）+ 天气 + 便签 + 快捷方式 + 番茄钟。
纯本地运行，数据存在你自己的电脑上，无需注册、无广告、无网络依赖（天气除外）。

欢迎使用！有任何想法、建议或 bug 反馈，欢迎提 Issue。

> 📖 日常使用见 [USAGE.md](USAGE.md)（按模块分类的使用手册）；
> 🤖 Agent 长期任务接入协议见 [WORKFLOW.md](WORKFLOW.md)；
> 以下是开发者 / Agent 接入文档。

## 功能

- 任务管理：三泳道（待办 / 进行中 / 已完成），支持优先级、截止日期、标签、描述、编辑、删除
- 任务日志：点击任务卡片查看完整时间线（创建 / 每次进度更新 / 完成时间）
- 番茄钟：25 分钟专注 + 5 分钟休息循环，今日完成计数（🍅），跨天自动归零
- 天气：当前温度 / 湿度 / 风力 / AQI / 日出日落 + 未来 7 天预报（中国天气网数据源，国内城市准确），点击顶栏天气展开预报详情
- 便签：随手记录
- 快捷方式：常用网站一键直达
- 统计：各状态任务数、今日完成数
- 自动更新：内置检查更新（右上角 ⬆），从 GitHub Release 一键升级，下载/安装解耦不卡死
- Agent 接入：REST API，agent 创建的任务自动带 🤖 标记
- 数据本地存储：data/workbench.db，纯本地、无账号

## 使用

### 源码模式（开发）

```bash
cd <项目目录>   # 例如 D:\workbench
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe flask pywebview
start.bat          # 双击即可
```

- 窗口模式：`python app.py`
- 只起服务（无窗口）：`python app.py --no-window`
- 服务默认端口 17890，被占用自动顺延（见 data/port.txt）
- 启动优化（v2）：WebView2 与 Flask 并行启动，窗口先显示占位页、服务就绪后自动导航；
  WebView2 使用持久 profile（data/webview），二次启动复用缓存，启动更快

### 下载安装（普通用户）

下载与更新历史见 **[Releases 页面](https://github.com/sanghaoyang/workbench/releases)**（每个版本含安装版/绿色版与更新说明）。

- **安装版**：`ShyBoardInstaller-vX.Y.Z.exe` —— 双击运行，选择安装目录，自动创建桌面快捷方式
- **绿色版**：`ShyBoard-vX.Y.Z.zip` —— 解压即用，双击 `ShyBoard.exe` 即可，不需要装 Python / 不需要配置任何环境
- 数据存在程序目录下 `data\`（自动创建），删除文件夹即完全卸载
- 自动更新：应用内右上角 ⬆ 从 GitHub Release 拉取新版本，下载/安装解耦不卡死

> ⚠️ **首次运行提示**：程序未购买代码签名证书，Windows SmartScreen 可能提示"已保护你的电脑"。
> 这是无签名程序的正常现象（非病毒）。点「更多信息」→「仍要运行」即可；绿色版解压后通常不会触发。

要求：Windows 10/11 64 位（需 Edge WebView2 运行时，Win11 内置，Win10 一般已随 Edge 安装；
若提示缺少 WebView2，可到微软官网下载安装一次，之后不再需要）。

### 打包发布（开发者）

1. 双击 `build.bat` → 产物 `dist\ShyBoard\`（约 32MB，自动带上 `update.ps1`）
2. `python scripts/pack_release.py <版本号>` → 打 `ShyBoard-<版本号>.zip`
3. 双击 `build_installer.bat` → 打 `ShyBoardInstaller-v<版本号>.exe`（内嵌当前版本 zip，版本号自动读取）
4. 递增 `app.py` 顶部 `APP_VERSION` → 提交 → 发 GitHub Release（上传 zip + 安装器）

## Agent 接入（REST API）

服务只监听 127.0.0.1。端口见 `data/port.txt`（默认 17890）。

### 创建任务

```bash
curl -X POST http://127.0.0.1:17890/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"写周报","priority":"high","due_date":"2026-08-07","tags":["工作"],"source":"agent"}'
```

### 完成任务

```bash
curl -X PATCH http://127.0.0.1:17890/api/tasks/12 \
  -H "Content-Type: application/json" \
  -d '{"status":"done"}'
```

### 其它接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | /api/health | 健康检查 |
| GET  | /api/stats | 统计 |
| GET  | /api/tasks?status=todo\|doing\|done | 任务列表（可过滤） |
| POST | /api/tasks | 创建任务 |
| GET  | /api/tasks/{id} | 任务详情（附带 events 事件日志时间线） |
| PATCH | /api/tasks/{id} | 更新（title/description/status/priority/due_date/tags） |
| DELETE | /api/tasks/{id} | 删除 |
| GET  | /api/notes | 便签列表 |
| POST | /api/notes | 创建便签 {"content":"..."} |
| DELETE | /api/notes/{id} | 删除便签 |
| GET  | /api/links | 快捷链接列表 |
| POST | /api/links | 创建 {"name","url","icon"} |
| DELETE | /api/links/{id} | 删除 |
| GET  | /api/weather | 当前天气 + 7 天预报（国内城市） |
| GET  | /api/weather/search?q=城市 | 城市搜索（离线表，仅国内 447 城） |
| GET  | /api/pomodoro | 今日番茄计数 |
| POST | /api/pomodoro/complete | 完成一个番茄（计数 +1，跨天归零） |
| GET/PUT | /api/settings | 设置（切城市 PUT {"city_code":"101210101","city":"杭州"}） |

任务字段：title(必填), description, status(todo/doing/done), priority(low/medium/high),
due_date(YYYY-MM-DD), tags(数组或逗号字符串), source(manual/agent)

## 项目结构

```
workbench/
├── app.py            # 入口：pywebview 窗口 + 服务启动 + 更新自愈/启动检查
├── server.py         # Flask REST API + 静态页面
├── db.py             # SQLite 数据层
├── update.ps1        # 自动更新 helper（等旧进程退出→替换 exe→重启，随包分发）
├── services/
│   ├── weather.py    # 天气（itboy 中国天气网源 + Open-Meteo 兜底）
│   └── updater.py    # GitHub Release 检查/下载（5 分钟缓存防限流 + pending 缓存）
├── static/           # 前端（HTML/CSS/JS + cities.json 城市表）
├── data/             # 运行时数据（workbench.db / port.txt / updates/）
├── scripts/
│   ├── pack_release.py  # 打包 dist → ShyBoard-<版本>.zip（相对路径，Windows 可用）
│   ├── gen_cities.py    # 重新生成城市表（上游 WeatherCode.txt）
│   ├── test_api.py      # 后端自动化测试（64 项，跑独立实例）
│   └── verify_fixes.py
├── start.bat         # 开发启动
├── build.bat         # 打包 exe（自动带上 update.ps1）
└── README.md
```

## QA 测试

后端自动化测试（跑独立实例，不碰用户数据）：

```bash
WORKBENCH_DB="<项目目录>\data\qa_test.db" ./.venv/Scripts/python app.py --no-window --port 17891
./.venv/Scripts/python scripts/test_api.py   # 64 项：CRUD 边界/错误/并发/XSS/一致性
```

测试完杀掉 17891 实例并删除 qa_test.db。

## 长期维护

- 加功能 = 后端加路由（server.py）+ 前端加区块（static/）
- 数据层集中在 db.py，字段变更注意迁移
- UI 主题色在 static/style.css 顶部 :root 变量里，改色只需改一处


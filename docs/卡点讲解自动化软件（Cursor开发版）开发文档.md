---
title: 卡点讲解自动化软件（Cursor开发版）开发文档
description: 卡点讲解自动化助手项目的整体说明与开发指引
date: 2025-11-07
---

# 💻 卡点讲解自动化软件（Cursor开发版）开发文档

## 一、项目概述

**项目名称：** 卡点讲解自动化助手  
**项目类型：** Python 桌面端 GUI 自动化控制工具  
**开发环境：** Cursor + Python + Playwright + tkinter  

**主要用途：**

为京东直播教学场景提供自动化卡点讲解功能，实现 **图片自动轮播、时间控制、端口绑定、进程管理** 等功能。

## 二、功能需求说明

| 功能模块 | 详细说明 |
| --- | --- |
| **端口绑定** | 用户输入浏览器远程调试端口（如 9222），软件通过 Playwright `connect_over_cdp` 接口连接浏览器。 |
| **任务控制** | 支持设置讲解时长（单图展示时间）与间隔延迟（两图切换时间）。 |
| **路径选择** | 浏览选择卡点讲解素材文件夹，自动加载图片资源。 |
| **卡密验证** | 输入卡密后刷新授权状态（本地 + 远程校验），卡密失效时禁用执行功能。 |
| **执行任务** | 启动自动讲解线程：按设定时间依次展示图片并控制播放。 |
| **结束进程** | 安全终止当前任务线程，断开浏览器连接。 |
| **退出程序** | 完整关闭应用并释放资源。 |
| **日志输出** | 主界面底部文本框实时输出运行状态与错误信息。 |

## 三、开发环境与依赖

### 1. 环境配置

| 项目 | 推荐配置 |
| --- | --- |
| Python 版本 | 3.10+ |
| 包管理工具 | pip / venv |
| 开发工具 | Cursor（带 GPT-5 模型） |
| 打包工具 | PyInstaller |

### 2. 安装依赖

```bash
pip install playwright
pip install requests
playwright install chromium
```

## 四、模块设计结构

```text
project_root/
│
├─ main.py                 # 主程序入口
├─ ui/
│   └─ main_window.py      # tkinter 界面布局
│
├─ core/
│   ├─ browser_control.py  # 浏览器绑定与操作逻辑（Playwright）
│   ├─ task_runner.py      # 任务线程管理
│   └─ license_manager.py  # 卡密验证模块
│
├─ assets/
│   └─ icon.ico            # 软件图标
│
├─ config/
│   └─ settings.json       # 保存端口、路径、授权信息
│
└─ logs/
    └─ runtime.log         # 运行日志文件
```

## 五、核心逻辑流程

### 1. 浏览器绑定流程

```python
from playwright.sync_api import sync_playwright


def connect_browser(port):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        page = browser.contexts[0].pages[0]
        return browser, page
```

1. 用户输入端口号并点击【连接】
2. 软件尝试 `connect_over_cdp` → 成功后返回 `Browser` 对象
3. 状态指示灯置绿，显示“已绑定端口 XXXX”

### 2. 自动讲解任务流程

```python
import threading
import time
import os


def run_task(page, folder_path, show_time, delay_time, update_log):
    images = [f for f in os.listdir(folder_path) if f.endswith((".png", ".jpg"))]
    for img in images:
        page.goto(f"file:///{folder_path}/{img}")
        update_log(f"展示图片：{img}")
        time.sleep(show_time)
        update_log(f"等待 {delay_time} 秒切换下一张")
        time.sleep(delay_time)
    update_log("任务已完成。")
```

- 独立线程执行，防止 GUI 卡顿。
- 每轮循环加载一张图片并等待设定时间。
- 使用 `update_log` 回调更新前端日志框。

### 3. 线程与状态安全机制

- 所有 Playwright 操作放入子线程。
- tkinter 主线程仅负责 UI 更新。
- 使用 `root.after(100, check_queue)` 机制从线程安全队列读取日志。
- “结束进程”按钮通过全局标志位安全停止循环。

### 4. 授权与续期逻辑（License 机制）

#### 卡密验证逻辑

```python
import requests
import json
import datetime


def check_license(key):
    resp = requests.post("https://example.com/license/check", json={"key": key})
    data = resp.json()
    if data["valid"]:
        expiry = data["expiry_date"]
        save_local_license(key, expiry)
        return True, expiry
    else:
        return False, None
```

#### 本地续期策略

- 本地保存上次验证时间和到期日。
- 每次启动软件自动检测是否过期。
- 若网络连接失败但上次验证未过期，允许离线使用。
- 到期前 7 天弹窗提醒“请续期或联系管理员更新卡密”。

## 六、业务流程（用户视角）

1. **准备阶段**
   - 用户获取《Chrome 多开 + 端口说明》文档与 tkinter 打包程序（单文件 exe）。
   - 首次使用时，根据文档复制 N 个 Chrome 快捷方式，并在“目标”尾部追加：`--remote-debugging-port=922x --user-data-dir=D:\ChromeProfiles\Profilexx`，端口 9222、9223… 递增，Profile 目录互不相同。
   - 双击各快捷方式确认浏览器正常启动。

2. **绑定阶段**
   - 启动 tkinter“浏览器绑定器”。
   - 在“调试端口”输入框填写 9222（或需要操作的窗口端口）并点击【连接】。
   - 状态灯由红变绿，提示“已绑定端口 9222”，如需切换窗口则修改端口后重新【连接】，旧连接自动断开。

3. **执行阶段**
   - 绑定成功后，主界面其他功能（跳转、截屏、填表、批量脚本、数据回传等）均对当前活跃窗口生效。
   - 用户可在浏览器内手动操作，也可完全依赖 GUI 自动化，互不干扰。
   - 未通过卡密验证时，功能按钮保持禁用状态，需先输入有效卡密完成授权。

4. **结束阶段**
   - 任务完成后，可在 GUI 点击【关闭浏览器】或直接关闭浏览器窗口。
   - 后续再次使用时，重新打开对应快捷方式并完成绑定即可，历史 Profile 保留登录态。

## 七、技术方案（开发视角）

### A. 总体架构

- **表现层：** tkinter（单文件 exe，后续可替换为 PyQt）。
- **驱动层：** Playwright Sync API，通过 CDP 远程连接现有 Chrome。
- **数据层：** 本地 JSON 文件保存常用端口与 Profile 路径列表，支持下拉选择与历史回写。
- **通信层：**
  - 绑定阶段使用 `connect_over_cdp("http://127.0.0.1:port")`。
  - 日志/状态采用 `Queue` + `tkinter.after` 轮询，保证线程安全。
- **授权层：** `core/license.py` 管理卡密校验与授权文件持久化，支持有效期检查与后续扩展远端校验。
  - 默认提供 `DEFAULT_KEY_REGISTRY` 静态卡密字典，可按项目发版时替换或改为对接服务端校验接口。

### B. 关键时序

1. 用户启动带 `--remote-debugging-port` 的 Chrome。
2. tkinter 点击【连接】后，子线程尝试 `connect_over_cdp`。
3. 成功后将 `Browser` 对象挂载全局状态并同步 GUI，失败则弹出错误并清空全局引用。
4. 后续操作（`goto` / `click` / `screenshot` 等）基于全局 `Browser` / `Page` 下发，运行在主线程外的线程，GUI 不阻塞。
5. 切换或断开时先 `browser.close()`，清理全局状态，再重新发起连接。

### C. 隔离与并发

- 每个 Chrome 实例因 `user-data-dir` 不同而独立，Cookie、缓存、插件与登录态互不影响。
- 多实例可同时打开，端口独立；当前版本一次只绑定一个端口，未来可扩展为维护 `<port, Browser>` 映射，实现多窗口并行控制。

### D. 异常与恢复

- 端口占用或连接失败时捕获异常并提示检查快捷方式参数。
- 用户手动关闭浏览器将触发 `Target closed`，界面恢复为未绑定状态。
- 网络波动导致 CDP 断链时，Playwright 抛错并提示用户重新绑定。

### E. 发布与运维

- 打包产物包含完整运行时，终端用户仅需解压并双击 `JDLiveAssistant.exe`，无需额外安装 Python 或其他依赖。
- 更新方式为覆盖 exe，配置 JSON 独立存储，升级不丢数据。
- 本地日志按日期滚动，记录绑定、断开与关键操作时间戳，便于审计与排查。

## 八、打包部署说明

### 1. 打包命令

```bash
pyinstaller --onefile --noconsole --icon=assets/icon.ico main.py
```

或直接双击 `scripts/build_exe.bat`，脚本将自动创建虚拟环境、安装依赖并生成 `dist/JDLiveAssistant.exe`。

### 2. 目录结构建议

```text
C:\卡点讲解\
│
├─ 卡点讲解.exe
├─ settings.json
├─ license.json
└─ 讲解素材\
```

### 3. 首次运行提示

- 自动生成配置文件与日志文件夹。
- 首次要求输入卡密并联网验证。
- 成功后缓存授权信息。

## 九、异常与恢复机制

| 异常类型 | 自动处理方式 |
| --- | --- |
| 端口未开启 | 弹出提示“请检查 Chrome 是否启动并带调试端口”。 |
| 浏览器断开 | 状态指示灯变红，日志提示“连接断开”。 |
| 网络中断 | 使用本地缓存授权文件离线运行。 |
| 用户强制退出 | 自动关闭线程、保存日志、防止僵尸进程。 |

## 十、运维与更新

| 操作 | 说明 |
| --- | --- |
| 软件更新 | 直接替换 `.exe` 文件即可，配置与授权不丢失。 |
| 日志清理 | 每月自动归档一次，防止占用空间。 |
| 卡密续期 | 由管理端重新生成新卡密，用户输入后自动更新授权日期。 |

## 十一、开发周期与工作计划

| 阶段 | 内容 | 预计天数 |
| --- | --- | --- |
| 第 1 天 | 环境搭建、界面原型实现 | 1 |
| 第 2 天 | Playwright 连接与任务线程开发 | 1 |
| 第 3 天 | 日志与异常处理、卡密模块 | 1 |
| 第 4 天 | 打包测试与优化 | 1 |
| 第 5 天 | 文档整理与交付 | 1 |
| **合计** | **5 天出可运行版本** |  |

## 十二、未来扩展方向

- ✅ 支持多端口同时绑定。
- ✅ 新增图片自动检测与重载机制。
- ✅ 计划迁移至 PyQt 或 Electron UI。
- ✅ 结合 WebSocket 实现远程控制。

---

## 十三、交付清单（文档类）

1. 业务流程图（见“业务流程（用户视角）”章节）。
2. 技术方案白皮书（见“技术方案（开发视角）”章节）。
3. Chrome 快捷方式制作模板（含端口与目录示例）。
4. 用户使用手册（图文版，一页 A4）。
5. 运维 FAQ（端口冲突、杀软拦截、组策略限制等常见问题）。
6. 卡密管理及续期流程说明（含授权文件示例、生命周期管理）。

若需要自动生成 Cursor Prompt 模板以快速搭建项目初版，可继续告知需求。

## 十四、Cursor 专用开发 Prompt 模板

为保证 Cursor / Copilot / Claude Dev 能准确理解“京东直播自动化助手（JD Live Assistant）”的目标与边界，建议在工程根目录新增 `prompts/JD_Live_Auto_Assistant.prompt`，内容参考下方模板：

```prompt
🧠【Cursor 专用开发 Prompt 模板】

你现在是一名资深自动化工具开发者，目标是开发一个辅助京东直播的自动化控制工具（JD Live Assistant）。

项目背景：
1. 自动打开并管理京东直播后台页面；
2. 自动执行常见运营操作（开播、切场、切商品、互动回复、弹幕关键词监控）；
3. 预留语音控制、热键触发、定时任务等扩展能力；
4. 支持嵌入自定义 Python 脚本，实现库存监控、优惠券触发、自动截图等业务逻辑；
5. 工具不涉及爬虫、不破坏系统安全、不模拟交易，仅提升直播间运营效率。

技术栈要求：
- 开发语言：Python；
- GUI：PySide6 / Tkinter / Electron（三选一，优先 PySide6）；
- 自动化模块：pyautogui、selenium、uiautomation、keyboard（按需选用）；
- 定时任务：apscheduler；
- 配置管理：YAML 或 .env；
- 日志：loguru；
- 可视化扩展：matplotlib（后续加入）。

功能模块：
1. 登录与页面控制：自动启动浏览器，打开京东直播后台，检测登录状态并提示用户完成一次登录。
2. 任务调度与热键：支持热键映射（如 F5 开播、F6 结束），并可设置定时任务（如每天 9:00 自动开播）。
3. 弹幕监控与关键词提醒：实时识别弹幕，命中关键词时触发语音播报或 UI 提示。
4. 日志与可视化：所有操作写入日志，后续提供互动统计图表。
5. 系统配置与界面：提供配置界面管理热键、定时任务、关键词，支持保存与加载。

代码风格约束：
- 遵循 PEP8；
- 每个模块文件提供中文注释；
- 功能拆分模块化，目录结构：
  JD_Live_Assistant/
  ├── main.py
  ├── core/
  │   ├── automation.py
  │   ├── hotkeys.py
  │   ├── schedule.py
  │   └── monitor.py
  ├── ui/
  │   ├── main_window.ui
  │   └── config_window.ui
  ├── config/
  │   └── settings.yaml
  └── logs/

首要开发目标：先实现“浏览器控制 + 定时开播 + 热键触发”三大基础功能，要求代码可直接运行；后续版本再集成弹幕监控、语音播报与智能提醒。

示例指令：
“为京东直播自动化助手构建基础项目架构，包含 main.py、core/automation.py、core/schedule.py、core/hotkeys.py，所有文件附中文注释，可直接运行，并生成示例配置文件 settings.yaml。”
```

## 十五、操作流程（语音稿整理版）

以下流程基于语音记录整理，适用于初次部署与日常使用：

1. **环境准备**
   - 在任意磁盘（建议 D 盘）新建 `卡点讲解` 文件夹。
   - 将新版“卡点讲解软件”（打包好的 exe）放入该文件夹。

2. **直播测试场景搭建**
   - 在京东直播后台新建一场“测试直播”。
   - 启动京东直播工具，选择刚创建的测试直播并开播，确认直播页面已开启。

3. **软件初始化与授权**
   - 打开新版卡点讲解软件。
   - 使用“浏览路径”选择刚刚创建的 `卡点讲解` 文件夹作为素材根目录。
   - 在“授权状态”区域输入卡密并点击“验证授权”，成功后界面功能解锁。
   - 点击“自动加载图片”，选择来源为电视的卡点讲解素材文件夹，导入预下载的图片。

4. **平板模型素材配置**
   - 在京东直播工具中，将“平板模型”图片添加到画面中。
   - 通过卡点软件的路径选择器定位下载的图片资源，将其拖拽到平板模型内。
   - 调整图片大小与位置，直至展示区域完整。
   - 锁定图片位置，确保后续不会误移动（每个账号仅需设置一次）。

5. **测试完成与正式使用**
   - 结束测试直播，确认设置已保存。
   - 正式直播时重复以下步骤：
     1. 打开京东直播工具并选择目标直播。
     2. 打开卡点讲解软件，加载素材并执行任务。

6. **正确退出流程**
   - 结束使用时不可直接关闭窗口（不能点击右上角叉）。
   - 必须先点击“结束进程”停止自动化任务，再点击“退出程序”安全关停。

该流程确保素材、路径和授权一次配置即可复用，后续账号只需加载相同目录即可快速进入工作状态。



---
title: JD Live Assistant 安装与使用手册
description: 适用于京东直播自动化助手的部署、安装、使用与故障处理指南
date: 2025-11-07
---

# 📘 JD Live Assistant 安装与使用手册

面向主播运营团队，指导如何部署与使用“京东直播自动化助手（JD Live Assistant）”。本文默认使用打包好的 `JDLiveAssistant.exe`。

---

## 1. 环境准备

- **操作系统**：Windows 10/11 64 位
- **必备软件**：Google Chrome（需支持远程调试模式）
- **权限要求**：首次运行建议在管理员权限下执行，以便注册热键
- **目录建议**：将软件放置在英文路径（如 `D:\JDLiveAssistant`），避免中文路径导致权限或编码问题

---

## 2. 安装流程

1. **下载文件**
   - `JDLiveAssistant.exe`
   - 配套配置目录：`config/settings.yaml`

2. **建立目录结构**
   ```text
   D:\JDLiveAssistant\
   ├── JDLiveAssistant.exe
   └── config\
       └── settings.yaml
   ```

3. **首次运行**
   - 双击 `JDLiveAssistant.exe`
   - 若防病毒软件弹窗，请选择“允许”或“信任”
   - 界面首次启动会自动创建 `logs/runtime.log`

4. **Playwright 浏览器安装提示**
   - 若提示缺少 Chromium 驱动，请按以下步骤执行一次：
     1. 打开命令提示符（管理员）
     2. 执行 `JDLiveAssistant.exe --playwright-install`
     3. 或由运维人员在原项目中运行 `playwright install chromium` 并将生成的浏览器目录随 exe 一起分发

---

## 3. 使用步骤

### 3.1 准备浏览器调试端口

1. 在桌面为 Chrome 创建快捷方式，复制多份备用
2. 右键属性，在“目标”末尾追加：
   ```text
   --remote-debugging-port=9222 --user-data-dir=D:\ChromeProfiles\JDLive
   ```
3. 双击快捷方式启动浏览器，确认能正常打开

### 3.2 绑定浏览器

1. 打开 `JDLiveAssistant.exe`
2. 在“调试端口”输入 `9222`（或自定义端口）
3. 点击【绑定浏览器】，状态栏出现“绑定成功”日志即完成

### 3.3 打开直播后台

1. 在“直播后台 URL”输入框填入地址（默认 `https://live.jd.com/#/anchor/live-list`）
2. 点击【打开直播后台】，软件会自动在绑定的 Chrome 中跳转

### 3.4 定时任务

1. 设置“每日开播时间”字段，例如 `09:00`
2. 点击【设置每日开播】，系统会在指定时间调用【打开直播后台】功能
3. 需要停用时点击【取消定时】即可

### 3.5 热键触发

- 默认热键（可在 `config/settings.yaml` 修改）：
  - `Ctrl+Alt+F5`：打开直播后台
  - `Ctrl+Alt+F6`：结束直播（占位，需按需实现）
  - `Ctrl+Alt+R`：刷新页面
- 热键生效必须保持程序运行，且首次启动建议使用管理员权限

### 3.6 日志查看

- 主界面下方“运行日志”实时展示操作状态
- 程序目录 `logs/runtime.log` 记录完整历史日志，可用于问题追踪

---

## 4. 常见问题

| 问题 | 解决方案 |
| --- | --- |
| **Hotkey 无法触发** | 以管理员身份运行软件；确认键位未被其他程序占用 |
| **绑定失败：端口不可达** | 确认 Chrome 是否使用 `--remote-debugging-port` 启动；端口是否被安全软件封锁 |
| **Playwright 报错缺少浏览器** | 运行 `JDLiveAssistant.exe --playwright-install` 或联系运维手动安装并复制浏览器目录 |
| **程序无法写入日志/配置** | 确认安装目录是否有写权限，必要时移至 `D:` 等非系统盘 |
| **退出后残留进程** | 先点击软件内【断开绑定】与【退出】，再关闭浏览器；如仍残留，可在任务管理器结束 `JDLiveAssistant.exe` |

---

## 5. 维护建议

- 每周检查 `logs/runtime.log`，必要时做归档或清理
- 配置修改后点击界面中的【保存配置】确保写入 `settings.yaml`
- 建议保留原始 exe 与配置的备份，方便快速恢复
- 若要更新版本，直接覆盖 `JDLiveAssistant.exe` 即可，配置不受影响

---

## 6. 附录：settings.yaml 示例

```yaml
app:
  default_port: 9222
  live_url: "https://live.jd.com/#/anchor/live-list"
schedule:
  daily_start_time: "09:00"
hotkeys:
  start_live: "ctrl+alt+f5"
  stop_live: "ctrl+alt+f6"
  refresh: "ctrl+alt+r"
```

如需新增热键或定时任务，可在此文件中扩展，并在界面中重新加载配置。


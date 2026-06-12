# RPA 录制工具 - 内网离线部署指南

内网环境通常无法连接互联网，无法通过 `pip install` 或 `playwright install` 在线安装依赖。本文档提供两种离线部署方案。

---

## 方案一：离线包部署

> **前提条件：内网机器已安装 Python 3.8+**
>
> 如果内网没有 Python，请直接使用 **方案二（exe）**。

**适用场景**：内网机器已有 Python 3.8+，但无法联网下载依赖。

### 外网准备（一次）

在一台能上网的电脑上，进入项目目录执行：

```cmd
cd E:\我的AI实验\hzrpa
python scripts/prepare_offline.py
```

此脚本会自动：
1. 用 `pip download` 下载所有 Python 依赖包（含依赖的依赖）
2. 下载 Playwright Chromium 浏览器二进制文件
3. 拷贝项目源码和配置模板
4. 生成内网安装脚本

执行完成后会生成 `offline_bundle/` 目录，例如：

```
offline_bundle/
├── packages/              # ~50 MB，Python wheel 包
├── playwright_cache/      # ~150 MB，Chromium 浏览器
├── scripts/
│   └── install_offline.py # 内网一键安装脚本
├── 启动录制工具.bat       # Windows 快捷启动
├── gui_recorder.py        # 主程序
├── recorder_utils.py      # 工具模块
├── config.py              # 配置
├── requirements.txt
├── .env.example           # 配置模板
└── README_OFFLINE.md      # 内网使用说明
```

### 内网安装

1. 将 `offline_bundle` 整个文件夹拷贝到内网机器（U盘/网闸/刻盘均可）
2. 在内网机器打开命令提示符，进入目录：
   ```cmd
   cd offline_bundle
   python scripts/install_offline.py
   ```
3. 脚本会自动：
   - 从 `packages/` 离线安装所有 Python 依赖
   - 将浏览器缓存复制到 `%LOCALAPPDATA%\ms-playwright\`
   - 创建 `.env` 配置文件
4. 编辑 `.env` 填入账号密码
5. 双击 `启动录制工具.bat` 运行

---

## 方案二：PyInstaller 打包为 exe（无需 Python）⭐

> **前提条件：无。内网无需 Python 即可运行。**
>
> 这是最省事的方案，推荐在内网机器没有 Python 时使用。

**适用场景**：内网机器**没有 Python**，或不允许安装任何软件。

### 外网打包

在一台有 Python 的外网机器上（已在本机完成，见下方 `dist/` 目录）：

```cmd
cd E:\我的AI实验\hzrpa
pip install pyinstaller

# 步骤 1：先打包 codegen 辅助程序（必须加 --collect-all playwright）
pyinstaller --onefile --console --name codegen_helper --collect-all playwright scripts/codegen_helper.py

# 步骤 2：打包主程序，并将 codegen_helper.exe 嵌入
pyinstaller --onefile --windowed --name RPA录制工具 --add-binary "dist/codegen_helper.exe;." gui_recorder.py
```

> **打包关键点**：
> 1. 必须先打包 `codegen_helper.exe`（独立的 PyInstaller 程序，包含完整的 playwright）
> 2. `codegen_helper` 打包时必须加 `--collect-all playwright`，否则 playwright 模块不会被包含，运行时会报 `No module named 'playwright'`
> 3. 主程序打包时必须 `--add-binary "dist/codegen_helper.exe;.` 将其嵌入
> 4. 程序运行时，冻结环境通过 `_MEIPASS` 找到内嵌的 `codegen_helper.exe`，用它来启动 codegen
> 5. 如果不嵌入 codegen_helper，程序会尝试用 `sys.executable`（即 exe 自身）来运行 `python -m playwright`，导致 exe 重复启动自己，弹出多个窗口

打包后会在 `dist/` 目录生成 `gui_recorder.exe`。

### 内网使用

**已打包完成，文件位于 `dist/` 目录：**

```
dist/
├── RPA录制工具.exe    # 主程序（约 10 MB）
├── .env.example       # 配置模板
└── README.txt         # 使用说明
```

1. 将 `dist/` 文件夹拷贝到内网任意位置
2. 将 `.env.example` 重命名为 `.env`，用记事本打开并填写账号：
   ```
   ZHYW_USERNAME=你的用户名
   ZHYW_PASSWORD=你的密码
   ```
3. 双击 `RPA录制工具.exe` 直接运行

> **注意**：exe 版本依赖内网机器已安装的 Chrome 或 Edge。如果内网没有系统浏览器，需要使用方案一（完整离线包）。

---

## 方案对比

| 方案 | 体积 | 内网需 Python | 内网需浏览器 | 适用场景 |
|------|------|-------------|------------|---------|
| **完整离线包** `offline_bundle/` | ~568 MB | ✅ 需要 | ❌ 不需要（自带 Chromium） | 内网有 Python，无系统浏览器 |
| **精简离线包** `offline_bundle_light/` | ~40 MB | ✅ 需要 | ✅ 需要 Chrome/Edge | 内网有 Python，有系统浏览器 |
| **免安装 exe** `dist/` | ~10 MB | ❌ 不需要 | ✅ 需要 Chrome/Edge | 内网无 Python，有系统浏览器 |

---

## 如何选择

```
内网有 Python？
├── 是 → 有系统浏览器（Chrome/Edge）？
│        ├── 是 → 用精简离线包（40MB）
│        └── 否 → 用完整离线包（568MB）
└── 否 → 用免安装 exe（10MB）
```

---

## 常见问题

**Q: 内网机器没有 Python，也不让装，怎么办？**
> 用方案二（PyInstaller），打包成 exe 后无需 Python 环境。

**Q: prepare_offline.py 提示 playwright install 失败？**
> 先确保外网机器已安装 playwright：`pip install playwright`，然后执行 `playwright install chromium`。

**Q: 内网安装后运行提示找不到浏览器？**
> 确保内网机器已安装 Chrome 或 Edge。程序会自动检测，如果检测失败，在 .env 中手动指定 `BROWSER_PATH`。

**Q: 如何更新到新版本？**
> 在外网机器拉取最新代码，重新运行 `prepare_offline.py`，将新的 `offline_bundle` 拷贝到内网覆盖即可。

**Q: 录制后的脚本如何自动执行？**
> GUI 界面切换到「执行脚本」标签页，选择录制的脚本 → 点击「分析参数」→ 修改需要替换的参数值 → 勾选「自动登录」→ 点击「执行脚本」。程序会自动打开浏览器、完成登录、执行录制的操作步骤。

**Q: 参数化是什么意思？**
> 录制时填写的内容（如问题描述、受理人等）在执行时可以替换成不同的值，不用重新录制。例如录制时填了"测试问题"，执行时可以改成"网络故障"，脚本会自动替换。

---

## 新增功能：执行录制的脚本

从 v2.0 开始，工具新增「执行脚本」功能，实现录制 → 执行的完整闭环：

### 执行流程

1. **录制**：切换到「录制」标签页，输入目标地址 → 点击「开始录制」→ 在弹出的浏览器中完成操作 → 点击「停止录制」
2. **执行**：切换到「执行脚本」标签页，选择刚录制的脚本 → 点击「分析参数」
3. **参数化**：在参数表格中双击修改需要替换的值（留空表示使用原始值）
4. **自动登录**：勾选「自动登录」，程序会使用 `.env` 中的账号密码自动完成登录
5. **运行**：点击「执行脚本」，程序自动打开浏览器、登录、执行录制的操作

### 执行标签页功能

| 区域 | 功能 |
|------|------|
| 脚本列表 | 显示所有已录制的 `.py` 脚本，点击选择 |
| 参数配置 | 自动分析脚本中的输入值，支持双击修改 |
| 脚本预览 | 只读显示脚本源代码 |
| 执行日志 | 实时显示执行过程中的输出和错误 |

### 自动登录原理

执行器会在脚本运行前自动：
1. 加载 `.env` 中的 `ZHYW_USERNAME` 和 `ZHYW_PASSWORD`
2. 访问登录页面（可配置地址）
3. 尝试填充常见的用户名/密码字段
4. 点击登录按钮
5. 等待页面加载完成后继续执行录制的操作

### 参数化原理

录制脚本中的 `page.fill("selector", "value")` 和 `locator.fill("value")` 操作会被自动识别。
- 执行时，如果参数表格中的「替换值」与「原始值」不同
- 执行器会在运行前将脚本中的原始值全局替换为新值
- 这样同一个脚本可以重复执行，每次填入不同的内容

---

## 快速命令速查

```bash
# 外网准备离线包
python scripts/prepare_offline.py

# 内网安装
python scripts/install_offline.py

# 内网启动
python gui_recorder.py
# 或双击：启动录制工具.bat

# 打包 exe（外网）
pip install pyinstaller
pyinstaller --onefile --windowed gui_recorder.py
```

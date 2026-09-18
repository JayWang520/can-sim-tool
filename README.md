# CAN 模拟收发工具（J1939）

Web 界面的 CAN 调试工具：同一套代码在 **Windows 与 Ubuntu（含虚拟机）** 上运行，支持多品牌 USB-CAN 硬件与无硬件虚拟总线，内置 J1939 发动机故障（DM1）模拟，单包/多包（TP.BAM）自动切换。

> **v1.1.1（2026-09-17）**：新增离线文件分析、中英文界面切换与版本图标。详细更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 功能

- **总线**：多后端运行时切换（virtual / socketcan / pcan / canalystii / slcan / kvaser），J1939 默认 250k
- **接收**：实时报文流（WebSocket），自动解析 29bit ID 的 PGN/SA/DA/优先级，DBC 信号值，单包及 TP.BAM 重组后的 DM1 DTC 解析，过滤/锁定画面/高亮；接收缓存可配置为 100～10000 帧
- **发送**：手动单帧 + 周期任务表（可启停）；递增模式支持字节区间（小端 16/32 位计数器等）；**配置保存/读取**——全部周期任务与故障模拟配置整体存为命名文件，随时恢复
- **故障模拟**：编辑 DTC 列表（SPN/FMI/OC）与故障灯状态，模拟发动机 ECU 周期广播 DM1（SAE 推荐 1s）；≤1 个 DTC 单包直发，≥2 个自动走 TP.BAM 多包；预置场景（水温过高/机油压力低/多故障并发）
- **日志**：CSV / ASC 记录、查看、下载、删除、按原始时序回放（支持倍速）
- **触发**：按 ID / PGN / 数据内容匹配 → 高亮 / 计数 / 自动回应帧；回应支持标准帧/扩展帧（含 `send_extended`），命中计数可清零
- **离线文件分析**：打开 CSV/TSV/XLSX/JSON/ASC 日志离线统计（帧数、周期、数据变化、逐字节范围等），无需连接 CAN，结果可导出
- **界面**：顶部切换中英文与深色/浅色/系统主题，偏好本地保存；显示当前版本号与应用图标

## 快速开始（一键）

**Windows**：双击 `run.bat`——首次运行自动创建环境并安装依赖（失败自动换清华镜像重试），之后自动选端口、启动并打开浏览器。也可以先双击 `install.bat` 单独安装。

**Ubuntu**：`./run.sh`（首次同样自动装依赖）；或先 `./install.sh`。

**端口策略（`run.py` 启动器）**：

- 默认 8000；启动时检测——如果本工具已在运行，不重复启动、直接打开页面
- 8000 被其他程序占用时自动向后找空闲端口（8001~8019），控制台会提示实际端口
- 20 个端口全被占时提示手动指定：`python run.py 8080`
- 虚拟机/其他电脑访问：注意 NAT 端口转发规则要对应**实际使用的端口**
- 无桌面环境（纯 SSH/无 GUI）不想自动开浏览器：`CAN_TOOL_NO_BROWSER=1 python run.py`

手动测试/开发（跳过启动器）：

```bash
.venv\Scripts\python -m pytest tests/ -q            # Windows
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # 任意平台
```

### 免安装/便携版（Windows）

已打包好的免安装版在 `dist/CanSimTool-便携版.zip`（或目录 `dist/CanSimTool/`）：

1. 解压 `dist/CanSimTool-便携版.zip`
2. 双击 `CanSimTool.exe` 即可运行，无需安装 Python 和第三方依赖

重新打包：双击 `build.bat`，会生成新的 `dist/CanSimTool/` 和 `dist/CanSimTool-便携版.zip`。

> **注意**：`CanSimTool.exe` 必须和旁边的 `_internal` 文件夹放在同一目录，不能只复制单个 exe；也不要在压缩包内直接双击运行。请先完整解压整个 `CanSimTool` 文件夹。


## 接真实硬件

| 场景 | 后端选择 | 通道示例 | 前置条件 |
|---|---|---|---|
| Windows + PCAN | `pcan` | `PCAN_USBBUS1` | 安装 [PCAN-Basic 驱动](https://www.peak-system.com/) |
| Windows + 周立功 CANalyst-II | `canalystii` | `0` | `pip install canalystii` 并装厂商驱动 |
| Windows + IXXAT USB-to-CAN V2 | `ixxat` | `0` | 安装 [IXXAT VCI 驱动](https://www.ixxat.com/)（vcinpl.dll） |
| Linux + PCAN/CANable（推荐） | `socketcan` | `can0` | 见下方 ip link 配置 |
| Linux + CANable (slcan 固件) | `slcan` | `/dev/ttyUSB0` | 见 python-can slcan 文档 |
| 无硬件 | `virtual` | 任意名 | 无 |

**Linux SocketCAN 每次插拔后需执行：**

```bash
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 up type can bitrate 250000
```

**Ubuntu 虚拟机（VirtualBox）额外两步：**

1. USB 直通：虚拟机运行中 → 菜单"设备 → USB" → 勾选你的 USB-CAN 适配器（若列表为空，先在"设置 → USB"添加筛选器并重启虚拟机）
2. 宿主机浏览器访问：设置 → 网络 → 网卡1(NAT) → 高级 → 端口转发，添加规则 `TCP 127.0.0.1:8000 → 10.0.2.15:8000`，之后 Windows 浏览器访问 `http://127.0.0.1:8000`

> 周立功 USBCAN(FD) 系列在 Linux 下无标准驱动，建议 Windows 使用或在 Linux 换 PCAN/CANable。

## 使用说明（对应界面六个标签页）

1. **总线**：选后端/通道/波特率 → 连接；加载 DBC 后接收页自动显示信号值（示例 DBC 在 `dbcs/`，含 EEC1/ET1）
2. **接收**：过滤框支持 ID/PGN 十六进制子串；黄色行 = 命中高亮触发规则
3. **发送**：周期任务适合模拟周期报文（如 EEC1 转速）配合故障模拟使用
4. **故障模拟**：填 DTC → 看预览（单包/多包、帧数）→ 启动广播；被调设备即收到周期 DM1
5. **日志**：记录 → 下载 CSV 分析；回放会把帧按原时序重发（注意先停周期任务避免混淆）。**打开文件与离线分析**：无需连接 CAN，选择 CSV/TSV/XLSX/JSON/ASC 文件 → 打开并分析，结果独立分页展示并可导出（详见 `docs/file-analysis.md`）
6. **触发**：典型用法——`PGN 65226 + 高亮` 快速定位 DM1；`自动发帧` 可做请求-应答模拟

## J1939 实现说明

- DM1 = PGN 65226（0xFECA），载荷 = 2 字节灯状态（MIL/红/黄/保护灯各 2bit）+ N×4 字节 DTC（SPN 19bit + FMI 5bit + OC 7bit + CM 1bit）
- 单包：载荷 ≤8 字节直接发送（默认补齐 8 字节）
- 多包：TP.BAM——通告帧 TP.CM（默认 PGN EC00，带节点优先级/SA → `18ECFFxx`，控制字节 0x20/总长/包数/PGN）+ 数据帧 TP.DT（默认 PGN ED00 → `18EDFFxx`，首字节序号 + 7 字节载荷）；BAM 为广播，无 EndOfMsg 响应；**两个传输帧的完整 29bit ID 可在界面分别自定义**（如复现 ETP 0x18EBFF00 或厂商私有实现）
- 模拟节点默认 SA=0x00（发动机 #1）、优先级 6，节点以完整 29bit ID 一站式设定（优先级/PGN/DA/SA 一个输入框）
- 接收方向支持标准 J1939 TP.BAM 多包重组；不支持 ETP 和点对点 RTS/CTS 会话

## 运行测试（无硬件）

```bash
.venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\pip ...
.venv/bin/python -m pytest tests/ -v            # Windows: .venv\Scripts\python -m pytest ...
```

59 个测试覆盖：J1939 ID/DTC 编解码往返、DM1 单包与 BAM 组包、TP.BAM 接收重组、virtual 总线回环、周期发送、故障模拟引擎、DBC 解析（含跨 SA 的 PGN 兜底匹配）、CSV 记录回放、触发规则、日志保护、离线文件分析、文件选择、触发器编辑、i18n 双语、版本图标、全 API + WebSocket 冒烟。

Windows 打包：推荐在 PowerShell 中运行 `.\build.ps1`，脚本会生成目录版和便携 ZIP；如只需目录版可运行 `.\build.ps1 -NoArchive`。该脚本使用 PowerShell 原生文件操作，避免中文文件名导致的批处理编码问题。

## 目录结构

```
app/         后端（FastAPI + python-can + cantools）
web/         前端单页（原生 HTML/JS/CSS，无构建：app.js/analysis.js/i18n.js/icon.*）
scenarios/   预置故障场景 JSON（可自行复制修改）
presets/     保存的配置现场（周期任务 + 故障配置）
dbcs/        示例 DBC
docs/        开发与功能文档（文件分析 / 前端工作区 / 版本与图标）
scripts/     构建辅助脚本（如 build-icon.cjs）
tests/       pytest 测试 + 前端 DOM/i18n CJS 检查
logs/        运行时生成的日志
```

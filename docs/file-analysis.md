# 文件打开与离线分析

入口：日志 → 打开文件与离线分析。选择文件后点击“打开并分析”。
实时接收和记录继续运行；分析结果独立分页，不跟随实时滚动，也不会触发发送或自动回应。

支持 CSV（UTF-8/GB18030）、TSV、XLSX、JSON、ASC。旧 XLS、BLF、MDF、CAN FD、远程帧暂不支持。
单次上限 20 MiB、10 万记录；超限整体拒绝，不返回截断统计。

表格第一行为表头。必需字段 `ts,id,data`，可选 `extended,dir,dlc,channel`。
接受别名 `timestamp/time/时间/时间戳`、`can_id/arbitration_id/帧id`、`data_hex/数据`、`ext/is_extended_id/扩展帧`、`direction/方向`、`length/长度`、`通道`。
JSON 为记录数组或含 `frames` 数组的对象。

ID 默认十六进制，包括纯数字；十进制 ID 文件请选择十进制。
时间默认秒，可选择 ms/us。ASC 固定 hex/absolute，时间为秒。
未填 extended 时仅根据 ID 范围推断；低 ID 扩展帧必须明确指定 `extended=1`。
dir 默认 rx。data 为十六进制文本（如 `12 34` 或 `1234`）；JSON 也支持整数数组 `[18,52]`。
Excel 数据列必须保存为文本，避免数字格式丢失前导零。不执行公式、不改写原文件。
多工作表可输入准确名称重新分析，成功后显示所有工作表名。

统计按通道、ID、标准/扩展、方向分别分组，包含帧数、相邻报文周期均值/最小/最大、数据变化次数、时间倒退次数和逐字节最小/最大/变化次数。
保持文件顺序；负时间间隔计入倒退，不进入周期统计。重复时间的零间隔参与统计。
无效记录显示原始行号及原因，不参与统计。字节缺失不当作零，不跨缺失字节比较变化。
这是描述性统计，不自动断言总线故障，也不推断位域信号或端序。

HTTP：`POST /api/files/analyze` multipart 字段 `file,sheet,id_base,time_unit`。
无需连接 CAN，可用于 AI 离线分析。返回 frames、stats、errors 等，页面可导出完整 JSON 报告。

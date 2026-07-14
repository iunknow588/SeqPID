# 自动化交易 work 脚本使用说明

本目录放置外部运行脚本，用于启动 `自动化交易` 项目中的 Python / Rust 分析程序。脚本本身不承载业务算法，只负责定位项目目录、拼接参数、创建输出目录并调用实际入口。

推荐在 PowerShell 中执行以下命令；如果当前系统限制 PowerShell 脚本执行，可以使用同名 `.cmd` 文件。

## 目录结构

```text
scripts\work
├─ open_analysis_gui.ps1 / .cmd          # 打开图形化分析配置界面
├─ run_level2_analysis.ps1 / .cmd        # Python 单日分析便捷入口
├─ run_ana.ps1                           # Python / Rust / 双引擎通用入口
├─ run_ana_python.cmd                    # 调用 run_ana.ps1 -Engine python
├─ run_ana_rust.cmd                      # 调用 run_ana.ps1 -Engine rust
├─ run_ana_rust_python.cmd               # 调用 run_ana.ps1 -Engine rust_python
└─ run_multi_day_analysis.ps1 / .cmd     # 多交易日批量分析入口
```

## 运行前准备

1. 确认 Python 可用：

```powershell
python --version
```

2. 如果需要运行 Rust 引擎，确认 Cargo 可用：

```powershell
cargo --version
```

3. 按默认约定放置 Level2 数据：

```text
C:\level-2-ana\data\<TradeDate>\<TradeDate>
```

例如：

```text
C:\level-2-ana\data\20260707\20260707
```

4. 默认输出目录：

```text
C:\level-2-ana\output
```

脚本会自动创建输出目录。

## 最常用命令

### 1. 打开图形化配置界面

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\open_analysis_gui.ps1
```

CMD 等价入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\open_analysis_gui.cmd
```

可选指定 Python：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\open_analysis_gui.ps1 -PythonExe python
```

### 2. Python 单日分析

适合日常跑单个交易日，默认生成 `submit.zip` 和性能报告。

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 -TradeDate 20260707
```

CMD 等价入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.cmd -TradeDate 20260707
```

默认行为：

- 输入目录：`C:\level-2-ana\data\<TradeDate>\<TradeDate>`
- 输出目录：`C:\level-2-ana\output`
- 股票列表：未指定时由主程序自动解析
- 提交包：默认生成 `submit.zip`
- 性能报告：默认生成；加 `-NoProfile` 可关闭

### 3. 小样本验证

先跑 1 只股票，快速确认数据路径、环境和输出链路是否正常。

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 `
  -TradeDate 20260707 `
  -StockLimit 1 `
  -NoProfile
```

跳过前 N 只股票后再跑指定数量：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 `
  -TradeDate 20260707 `
  -StockOffset 10 `
  -StockLimit 5 `
  -NoProfile
```

### 4. 指定输入、输出和股票清单

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 `
  -TradeDate 20260708 `
  -InputDir C:\level-2-ana\data\20260708\20260708 `
  -OutputDir C:\level-2-ana\output\manual_20260708 `
  -StockListFile C:\level-2-ana\data\百只股票样本.csv
```

注意：`-StockListFile` 必须指向已经存在的 CSV 文件。

## 通用分析入口：run_ana.ps1

`run_ana.ps1` 是更完整的调度入口，可选择 Python、Rust 或两个引擎依次运行。

### Python 引擎

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine python `
  -TradeDate 20260707
```

CMD 快捷入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_ana_python.cmd -TradeDate 20260707
```

### Rust 引擎

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine rust `
  -TradeDate 20260707
```

CMD 快捷入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_ana_rust.cmd -TradeDate 20260707
```

### Rust + Python 双引擎

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine rust_python `
  -TradeDate 20260707
```

CMD 快捷入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_ana_rust_python.cmd -TradeDate 20260707
```

### 只打印命令，不实际运行

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine python `
  -TradeDate 20260707 `
  -DryRun
```

### run_ana.ps1 的自动日期规则

`run_ana.ps1` 支持自动推断交易日：

- 如果传了 `-InputDir` 但没传 `-TradeDate`，脚本会从输入路径中提取最后一个 `20` 开头的 8 位日期。
- 如果 `-InputDir` 和 `-TradeDate` 都没传，脚本会在 `C:\level-2-ana\data` 下查找最新的 `20xxxxxx` 日期目录。

示例：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine python `
  -InputDir C:\level-2-ana\data\20260708\20260708
```

`run_level2_analysis.ps1` 不会从数据目录自动选择最新日期；未传 `-TradeDate` 时，只会尝试从 `-InputDir` 提取日期。

## 多交易日批量分析

默认会依次检查以下交易日，存在数据目录才会运行，不存在则跳过：

- `20260708`
- `20260707`
- `20260706`
- `20260130`
- `20260129`

默认引擎为 `rust_python`，即每个交易日先跑 Rust，再跑 Python。

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_multi_day_analysis.ps1
```

只跑 Python：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_multi_day_analysis.ps1 -Engine python
```

只跑 Rust：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_multi_day_analysis.ps1 -Engine rust
```

指定多日输出根目录：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_multi_day_analysis.ps1 `
  -OutputRoot C:\level-2-ana\output\multi_day_test
```

CMD 等价入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_multi_day_analysis.cmd -Engine python
```

多日输出会按以下结构组织：

```text
<OutputRoot>\<TradeDate>\<Engine>\
```

默认即：

```text
C:\level-2-ana\output\multi_day\<TradeDate>\<Engine>\
```

## 参数说明

### run_level2_analysis.ps1

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-TradeDate` | 无 | 交易日，例如 `20260707`。常规使用必须传入。 |
| `-InputDir` | `C:\level-2-ana\data\<TradeDate>\<TradeDate>` | Level2 输入数据目录。 |
| `-OutputDir` | `C:\level-2-ana\output` | 输出根目录。 |
| `-StockListFile` | 空 | 股票清单 CSV 文件路径。 |
| `-StockLimit` | `0` | 限制处理股票数量；`0` 表示不限制。 |
| `-StockOffset` | `0` | 跳过前 N 只股票。 |
| `-NoProfile` | 关闭 | 跳过性能报告。 |
| `-PythonExe` | `python` | Python 可执行程序，例如 `py` 或虚拟环境中的 `python.exe`。 |

### run_ana.ps1

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-Engine` | `python` | 可选 `python`、`rust`、`rust_python`。 |
| `-TradeDate` | 自动推断 | 交易日。未传时会尝试从 `-InputDir` 或 `C:\level-2-ana\data` 推断。 |
| `-InputDir` | `C:\level-2-ana\data\<TradeDate>\<TradeDate>` | Level2 输入数据目录。 |
| `-OutputDir` | `C:\level-2-ana\output` | 输出根目录。 |
| `-StockListFile` | 空 | 股票清单 CSV 文件路径。 |
| `-StockLimit` | `0` | 限制处理股票数量。 |
| `-StockOffset` | `0` | 跳过前 N 只股票。 |
| `-NoProfile` | 关闭 | 跳过性能报告。 |
| `-DryRun` | 关闭 | 只打印将执行的命令，不实际运行。 |
| `-PythonExe` | `python` | Python 可执行程序。 |
| `-CargoExe` | `cargo` | Cargo 可执行程序。 |
| `-Config` | `.\configs\dev.yaml` | 运行配置文件，相对路径会在分析系统目录下解析。 |
| `-LabelConfig` | `.\configs\label_dict.yaml` | 标签字典配置文件。 |

### run_multi_day_analysis.ps1

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-Engine` | `rust_python` | 可选 `python`、`rust`、`rust_python`。 |
| `-OutputRoot` | `C:\level-2-ana\output\multi_day` | 多日批量输出根目录。 |
| `-NoProfile` | 关闭 | 传给子任务，跳过性能报告。 |
| `-PythonExe` | `python` | Python 可执行程序。 |
| `-CargoExe` | `cargo` | Cargo 可执行程序。 |

### open_analysis_gui.ps1

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-PythonExe` | `python` | 用于启动 `analysis_gui.py` 的 Python 可执行程序。 |

## 输出内容

分析完成后，主程序通常会在输出目录生成：

- `submit.zip`：比赛提交包。
- 诊断 JSON / CSV：批处理诊断、标签分布等中间结果。
- 性能报告：默认开启；使用 `-NoProfile` 可关闭。
- 校验报告：若主程序启用相应校验，会输出 market PID、百股 replay 等报告。

具体文件名以运行日志打印为准。

## 常见问题

### 1. PowerShell 提示禁止运行脚本

优先使用 `.cmd` 入口，例如：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.cmd -TradeDate 20260707
```

`.cmd` 包装器内部已使用：

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass
```

### 2. 提示 InputDir does not exist

检查数据目录是否存在。默认路径必须类似：

```text
C:\level-2-ana\data\20260707\20260707
```

如果数据不在默认位置，请显式传入：

```powershell
-InputDir D:\your\data\20260707
```

### 3. 提示 Cannot find Python system directory

脚本会在 `E:\2026OPC大赛\自动化交易` 下查找同时包含 `main.py`、`configs`、`src` 的目录。当前项目中应为：

```text
E:\2026OPC大赛\自动化交易\比赛系统
```

如果移动了目录结构，需要保持上述文件和目录仍在同一个系统目录中。

### 4. Rust 引擎无法运行

确认以下目录和工具存在：

```text
E:\2026OPC大赛\自动化交易\src-rust\Cargo.toml
```

```powershell
cargo --version
```

也可以先只跑 Python：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 -Engine python -TradeDate 20260707
```

### 5. 想确认脚本会执行什么命令

使用 `run_ana.ps1 -DryRun`：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine python `
  -TradeDate 20260707 `
  -DryRun
```

## 推荐工作流

1. 先小样本验证：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 `
  -TradeDate 20260707 `
  -StockLimit 1 `
  -NoProfile
```

2. 再跑完整 Python 单日：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 -TradeDate 20260707
```

3. 需要对比 Rust / Python 时使用通用入口：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_ana.ps1 `
  -Engine rust_python `
  -TradeDate 20260707 `
  -OutputDir C:\level-2-ana\output\compare_20260707
```

4. 多日回归时使用批量入口：

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_multi_day_analysis.ps1 -Engine python
```

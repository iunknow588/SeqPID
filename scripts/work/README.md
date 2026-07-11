# Level2 Analysis Work Scripts

该目录放置外部工作脚本，不承载比赛系统业务逻辑。

## 推荐：打开配置界面

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\open_analysis_gui.ps1
```

等价 CMD 入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\open_analysis_gui.cmd
```

配置界面可以设置：

- 样本目录
- 输出目录
- 股票清单
- 是否生成性能报告

## 批处理备用：运行 100 股分析

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 -TradeDate 20260707
```

等价 CMD 入口：

```cmd
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.cmd -TradeDate 20260707
```

默认行为：

- 输入目录：`C:\level-2-ana\data\<TradeDate>\<TradeDate>`
- 输出目录：`C:\level-2-ana\output`
- 股票清单：命令行未传时由比赛系统自动发现 `C:\level-2-ana\data\百只股票样本.csv`
- 默认生成 `submit.zip`
- 默认生成性能报告

## 小样本验证

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 -TradeDate 20260707 -StockLimit 1 -NoProfile
```

## 静态检查符号口径

```powershell
cd E:\2026OPC大赛\自动化交易\比赛系统
python -m pytest tests\unit\test_static_sign_contract.py
```

检查约束：

- 正式公式字段买入为正、卖出为负。
- `CH_rule_t / Q_rule_t / R_seed_t / signed_*` 是带符号字段。
- `*_buy_amount / *_sell_amount / signal_deal_*` 是历史毛额展示字段，不作为统一公式主输入。

报告输出：

- `E:\2026OPC大赛\自动化交易\比赛系统\tests\unit\sign_static_check_report.md`

## 自定义输入目录

```powershell
E:\2026OPC大赛\自动化交易\scripts\work\run_level2_analysis.ps1 `
  -TradeDate 20260708 `
  -InputDir C:\level-2-ana\data\20260708\20260708
```

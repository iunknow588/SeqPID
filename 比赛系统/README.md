# 比赛系统

## 置顶：Python 版重构开发计划

当前优先实现 Python 版可提交链路，按“先可运行、再增强”的顺序推进：

| 阶段 | 目标 | 关键产出 |
| --- | --- | --- |
| P0 baseline_rule | Level2 schema 探针与规则兜底可运行 | 已完成：`schema_probe_report.md`、基础提交结果 |
| P1 baseline_4d | 游资强锚点 + 量化散户混合池 + 4维状态模型 | 已接入：逐笔成交窗口锚点、`c_p/c_i/eps`、`capital_ch/q/retail` 外力贡献输出 |
| P2 enhanced_5d | 加入 `D_driver` 与 `theta`，完成 5维 PID 状态估计 | 进行中：`c_p/c_i/c_d/eps`、D 项诊断、5维输入验证 |
| P3 integration | 对接 Task 1/2、market_pid 与 zip 导出 | 进行中：全链路批处理与提交包 |

当前实现原则：

1. 大额主动买入/卖出优先锚定游资。
2. 小额成交、被动成交、盘口回补和高频挂撤先进入“量化+散户”混合池。
3. 先计算一级 PID 贡献 `c_p / c_i / c_d / eps`。
4. 再由 `beta_* U_*` 计算 `capital_ch / capital_q / capital_retail`。
5. 若 5维模型或 `D_driver` 未通过验证，回退到 `baseline_4d`，不阻塞提交能力。

本目录为天池赛题一比赛交付系统首批代码骨架。

当前已实现：

- `main.py` 启动入口
- `schema_probe.py` 数据 schema 探针
- `exporter.py` 标准提交文件导出
- `config.py` 配置加载
- `schemas.py` 基础数据结构
- `scheduler.py` 批处理调度、缺失样本补全、market snapshot、提交包导出
- `pid_decomposer.py` PID 统一入口；`pid_decomposer_shared.py` + `pid_decomposer_4d.py` + `pid_decomposer_5d.py` 分别承载公共骨架、4D 与 5D 独立实现
- `capital_model.py` 基于三类资金正负号输出买入/卖出/中性
- 原始逐笔成交模式下，按 48 个 5 分钟窗口统计 `CH_rule_t / Q_rule_t / R_seed_t`，并兼容历史 `signed_large_active_amount / signed_mix_qr_amount`
- 有行情快照时，优先用成交价相对买一/卖一推断主动买卖；盘口缺失时才回退到 `BS标志`

当前推荐优先执行：

```bash
python main.py --mode probe --date 20260710 --input-dir C:\level-2-ana\data --report-dir C:\level-2-ana\output\reports\diagnostics
```

真实数据按股票分目录时，可先做小规模抽样验证：

```bash
python main.py --mode batch --date 20260130 --input-dir C:\level-2-ana\data --output-dir C:\level-2-ana\output --stock-limit 20 --build-zip
```

输出：

- `C:\level-2-ana\output\reports\diagnostics\schema_probe_report.md`

后续将逐步补充：

- 用真实数据检查 `raw_active_inferred_count`、`raw_side_fallback_count`、`raw_unknown_side_amount`，确认主动/被动口径是否可靠
- 校准 `capital_anchor_error_max`、大单阈值、`kappa_i` 与 KF 噪声参数
- 将 `market_pid.py` 统一到“优先聚合个股 `c_p / c_i / c_d`，缺失时启发式 fallback”的口径
- 增加真实 Level2 样本的回归测试与诊断报表

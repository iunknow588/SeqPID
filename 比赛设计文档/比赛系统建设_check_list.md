# 天池赛题一：比赛系统建设 Check List

**版本：** V1.8  
**日期：** 2026-07-14  
**文档定位：** 重构准备与实现闭环核对版  
**适用范围：**

- `比赛概要设计说明书.md` V1.6
- `比赛详细设计说明书.md` V1.7
- `PID算法与实现.md`
- `统一资金类型判断规范.md` V1.1
- `金融领域的物理学概念模型.md`
- `比赛系统/` 当前代码实现

---

## 0. 本轮修正结论

当前系统已具备可运行基线，但代码结构仍是“可提交优先”的形态：`scheduler.py` 承载了数据读取、窗口聚合、样本构建、缺失补位、调度导出等多类职责；PID 分解层现已按“入口选择器 + shared 公共骨架 + 4D 独立实现 + 5D 独立实现”拆分，但周边文档、清单和少量调用说明仍需收口到同一口径。

本轮后续重构目标不是推翻基线，而是把现有能力拆成与 V1.4 详细设计一致的模块边界，并优先保证：

1. 输出文件不变：`pattern_reco.csv`、`predict_result.csv`、`submit.zip`。
2. 主入口不变：`main.py` 可继续运行。
3. 规则/PID 口径统一：`CH_rule / Q_rule / R_seed` 只作为规则流，`capital_ch / capital_q / capital_retail` 只来自 PID 外力贡献 `beta_* U_*`。
4. `phi / theta` 只作为系统响应与状态诊断，不反解为某一类资金身份。
5. 默认稳健运行态为 `baseline_4d`，5 维模式仅在输入质量、D 项有效性与可辨识性验证通过后启用。
6. 先做低风险模块拆分，再做弱监督模型和聚类原型库升级。
7. 理论口径现已定版：成交量窗口可视为离散交易时间 `q`，价格为 `P_state(q)`；`P_wv_window` 仅作成交量域诊断，实时状态和提交使用 `P_state`。
8. 观测差分 `y_t / v_q,t` 与预测值 `y_hat_t+1|t / v_hat_q,t+1|t` 必须分字段保存。
9. 实时路径只允许使用先验/滤波量；RTS、HP 和全样本平滑只用于离线复盘。
10. PID 实现按参数状态空间三式验收：`psi_t` 转移、`y_t` 观测、`y_hat_t+1|t` 预测，禁止把价格差分重构关系做成第二套状态估计。
11. 4D/5D 模式切换必须固定 `5/3/2` 滞回、`lambda_switch / lambda_jump / lambda_error` 和参数跳变阈值，提交期不得动态调参。
12. `beta_norm / m_eff / m_slow` 进入画像前必须通过同口径、市值占比流、截断、不确定性、实时方法白名单和流动性分组可比性检查。
13. 双域映射和 `kappa_t` 只作诊断；零成交、薄成交或 `domain_mapping_valid_flag = false` 时不得进入排名或正式标签判断。
14. `baseline_4d` 的正式结构化外力输出是 `capital_ch / capital_mix`；若展示 `capital_q / capital_retail`，必须标记为诊断分摊近似。
15. 48 个基础窗口的理论依据必须统一写明为“A 股连续竞价 240 分钟 / 5 分钟粒度”。

---

## 1. 文档一致性检查

本轮补充检查项：

- 所有设计文档必须明确“成交量/窗口序号可作为交易时间 `q`”这一假设。
- 所有设计文档不得再把一阶模型写成与二阶模型并列的理论解释。
- 若文档中出现一阶公式，只能标注为工程近似、降阶模型或稳健实现备选。
- 所有设计文档必须把 `v_q,t` 与 `P_state,t` 的关系标注为“观测定义/状态重构恒等式”，不得写成第三套独立状态转移。
- `beta_norm / m_eff` 必须说明同一 `U_*_mv_ratio` 输入口径、截断标记和不确定性边界。
- 详细设计、概要设计和清单中的模式名、零成交策略、泄漏字段与回退规则必须一致。
- 所有正式提交路径必须显式记录 `data_leakage_check` 和 `m_eff_uncertainty_flag`。
- 概要、详细和建设清单必须同步写明标准状态空间三式、模式切换 `lambda` 范围、流动性分组可比性和薄成交窗口降级。
- Jury 稳定性描述必须统一区分“完整冻结窗口判据”“快速启发式筛查”和“时变参数滚动诊断”三层口径。
- `m_slow_method` 的默认优先级必须解释为工程稳健性排序，不能写成理论最优性结论。

| 检查项 | 目标状态 | 当前状态 | 下一步 |
|---|---|---|---|
| 比赛概要设计版本 | V1.6 | `已更新` | 已对齐 PID/物理模型和实时/离线边界 |
| 比赛详细设计版本 | V1.7 | `已更新` | 已补观测预测分离、诊断字段、泄漏和稳定性验收 |
| PID 算法与实现 | V1.8 口径 | `已对齐` | 已补状态层级、Jury 判据和 4D 诊断分摊边界 |
| 资金类型判断规范 | V1.1 | `已确认` | 作为规则层主依据 |
| PID 原理与实现 | V1.1 | `已确认` | 作为结构反解主依据 |
| Task 1 输出文件名 | `pattern_reco.csv` | `已实现` | 重构期间不得改变 |
| Task 2 输出文件名 | `predict_result.csv` | `已实现` | 重构期间不得改变 |
| 市场状态输出文件 | `market_pid_snapshot.csv` / `market_regime_report.md` | `已实现` | 保持兼容 |
| PID 诊断文件 | `pid_window_diag.csv` / `pid_daily_diag.csv` | `设计已冻结` | 补实际导出与专项测试 |
| 启动入口 | `main.py` | `已实现` | 保持 CLI 兼容 |
| 输出目录规则 | `output/交易日_时间戳/` | `已实现` | 保持 |
| 股票清单模式 | 支持 100 股清单过滤与排序 | `已实现` | 加回放验收 |
| 缺失股票补位 | 名单股票缺失原始数据时补默认行并告警 | `已实现` | 加专项测试 |

---

## 2. 当前代码实现核对

### 2.1 已存在模块

| 模块 | 当前文件 | 当前状态 | 重构处理 |
|---|---|---|---|
| 启动入口 | `main.py` | `已完成` | 保持入口，减少内部路径逻辑 |
| 配置加载 | `src/config.py` | `已完成` | 保持 |
| schema 探针 | `src/schema_probe.py` | `已完成` | 补正式报告输出流程 |
| 调度流程 | `src/scheduler.py` | `已完成但过重` | P0 拆分 |
| PID 分解入口 | `src/pid_decomposer.py` | `已完成` | 保持统一 facade 与模式选择 |
| PID 公共骨架 | `src/pid_decomposer_shared.py` | `已完成` | 维护共享逻辑与诊断 |
| PID-4D 实现 | `src/pid_decomposer_4d.py` | `已完成` | 独立维护 `baseline_4d` |
| PID-5D 实现 | `src/pid_decomposer_5d.py` | `已完成` | 独立维护 `diag_5d / full_5d` |
| Task 1 基线 | `src/pattern_model.py` | `规则基线已完成` | P2 升级原型库 |
| Task 2 基线 | `src/capital_model.py` | `规则/PID 基线已完成` | P2 升级弱监督/监督模型 |
| 市场 PID | `src/market_pid.py` | `基线已完成` | P1 校验市场口径 |
| 导出 | `src/exporter.py` | `已完成` | 保持字段兼容 |
| 数据结构 | `src/schemas.py` | `已初步扩展` | 已增加 StateFeature/规则事件结构，后续随 PID 字段统一继续补充 |
| PID 诊断导出 | `src/exporter.py` / `src/schemas.py` | `设计待落地` | 增加窗口级/日级诊断字段与提交阻断状态 |

### 2.2 设计要求但尚未独立成模块

| 目标模块 | 当前承载位置 | 当前状态 | 重构优先级 |
|---|---|---|---|
| `data_loader.py` | `scheduler.py` | `未拆分` | P0 |
| `windowing.py` | `scheduler.py` | `未拆分` | P0 |
| `reference_feature_builder.py` | `scheduler.py` / 参考文件直读逻辑 | `未拆分` | P1 |
| `capital_rule_engine.py` | `scheduler.py` + PID selector/shared/4D/5D 链路的输入抽取 | `已初步拆分` | P0 |
| `state_feature_builder.py` | PID selector/shared/4D/5D 结果 + `capital_model.py` 间隐式传递 | `已初步拆分` | P1 |
| `prod.yaml` | 无 | `未完成` | P2 |

---

## 3. P0 重构准备清单

### 3.1 调度层瘦身

| 任务 | 目标文件 | 验收标准 | 状态 |
|---|---|---|---|
| 抽出 CSV 读取与编码适配 | `src/data_loader.py` | 支持 `utf-8-sig / gb18030`，保留中文文件名适配 | `已完成` |
| 抽出股票目录扫描与缺失文件检查 | `src/data_loader.py` | `scheduler.py` 仅保留兼容包装，主逻辑迁移到 `data_loader.py` | `已完成` |
| 抽出 48 个 5 分钟窗口映射 | `src/windowing.py` | `_time_to_window_id` 委托到 `windowing.py` 并由单测覆盖 | `已完成` |
| 抽出逐笔成交到窗口桶聚合 | `src/windowing.py` / `src/capital_rule_engine.py` / `src/order_lifecycle.py` | 窗口桶初始化、规则事件聚合与订单生命周期恢复已迁移；支持沪市 A/D 委托流、深市成交表撤单、委托号直连与价格 FIFO 队列 | `已完成` |
| 保持 `run_daily_batch()` 外部签名 | `src/scheduler.py` | 原测试和 CLI 不破坏，单元测试 33 项通过 | `已完成` |

### 3.2 规则层口径对齐

| 任务 | 目标文件 | 验收标准 | 状态 |
|---|---|---|---|
| 建立事件级 `CapitalBehaviorEvent` | `src/schemas.py` | 包含 `capital_type_rule / confidence_level / fallback_reason / reason_codes` | `已完成` |
| 新增规则层聚合字段 | `src/capital_rule_engine.py` | 输出 `CH_rule_t / Q_rule_t / R_seed_t`，并保持历史字段兼容 | `已完成` |
| 替换历史 `signed_mix_qr_amount` 主口径 | `src/scheduler.py` / PID selector/shared/4D/5D 链路 | PID 输入优先读取 `CH_rule_t / Q_rule_t / R_seed_t`，旧字段仅作 fallback | `进行中` |
| 输出字段契约冻结 | `reports/validation/state_feature_contract.md` | 明确规则流、一级贡献、结构反解、近似字段四类边界 | `已完成` |
| 被动成交 5 分钟阈值字段预留 | `src/capital_rule_engine.py` | 可处理 `order_age_minutes` 缺失并标记低置信，专项单测覆盖 | `已完成` |
| 集合竞价成交分类预留 | `src/capital_rule_engine.py` | 当前先按低置信 `quant` 回退，待接入竞价成交价后细化 | `进行中` |

### 3.3 PID 输出口径对齐

| 任务 | 目标文件 | 验收标准 | 状态 |
|---|---|---|---|
| 模式名统一 | `src/pid_decomposer.py` | 只输出 `rule_base / baseline_4d / diag_5d / full_5d` | `已完成` |
| 字段名统一 | `src/pid_decomposer.py` / `src/schemas.py` | 使用 `phi / theta / beta_ch / beta_q / beta_mix / beta_retail`，保留历史别名兼容 | `已完成` |
| 外力贡献闭合断言 | PID selector/shared/4D/5D 链路 | full_5d 校验 `capital_ch + capital_q + capital_retail = c_p`；baseline_4d 校验 `capital_ch + capital_mix = c_p`；另行校验 `closure_impl_error` | `待复核` |
| 规则近似字段隔离 | PID selector/shared/4D/5D 链路 / `src/capital_model.py` | `rule_base` 不写 `capital_*` 结构字段，规则近似仅落在 `capital_*_rule_approx` | `已完成` |
| 清理展示分摊主口径 | PID selector/shared/4D/5D 链路 | `delta_*_display` 不参与 `capital_type` 主判断，debug 显式输出主判断来源 | `已完成` |
| 4D / 5D 文件级拆分 | `src/pid_decomposer.py` / `src/pid_decomposer_shared.py` / `src/pid_decomposer_4d.py` / `src/pid_decomposer_5d.py` | 4D 与 5D 逻辑独立、上层统一通过 selector 调用 | `已完成` |
| 市场 PID 主聚合口径 | `src/market_pid.py` | 优先使用 `c_p / c_i / c_d`，fallback 必须记录来源，不得把规则流直接当模型外力贡献 | `已完成` |
| 实时/离线方法边界 | PID selector/shared | 实时路径禁止 RTS/HP/全样本平滑，离线方法必须显式标记 | `已对齐` |
| 等效质量安全边界 | PID shared / StateFeature | 同口径 `beta_norm`；截断或置信区间过宽时 `m_eff_rank_eligible = false` | `部分完成` |
| 观测/预测字段分离 | `src/schemas.py` / exporter | `y_observed / y_hat_next / v_q_observed / v_hat_q_next` 不覆盖 | `待复核` |
| 状态空间三式验收 | PID selector/shared/4D/5D 链路 | `psi_t` 转移、`y_t` 观测、`y_hat_t+1|t` 预测分层，价格重构关系不作为独立状态方程 | `待复核` |
| 4D 诊断分摊边界 | PID selector/shared/4D/5D 链路 / `src/schemas.py` | `baseline_4d` 正式输出为 `capital_mix`，`capital_q / capital_retail` 若存在必须标记诊断近似且不参与主判断 | `已对齐` |
| 48 窗口理论口径 | `src/windowing.py` / 配置文件 / 文档 | 固定为连续竞价 240 分钟按 5 分钟切分，跨文档与代码注释一致 | `待复核` |
| 模式切换超参冻结 | PID shared / 配置文件 | `lambda_switch / lambda_jump / lambda_error` 和 `K_up / K_down` 训练前固定，输出敏感性报告 | `待复核` |
| 流动性可比性与薄成交窗口 | PID shared / market_pid / exporter | 输出 `liquidity_group / cross_symbol_comparable / thin_trade_window / domain_mapping_valid_flag` | `待执行` |
| `m_slow` 方法优先级 | PID shared / 配置文件 | 默认 `ewma_realtime`，卡尔曼滤波需离线验证优于基线后启用 | `待复核` |

---

## 4. P1 工程闭环清单

### 4.1 schema 与报告

| 检查项 | 交付物 | 当前状态 | 下一步 |
|---|---|---|---|
| 四类原始数据真实文件格式确认 | `schema_probe_report.md` | `部分完成` | 补冻结版报告 |
| 逐笔成交字段映射确认 | `schema_probe_report.md` | `已完成` | 写入报告 |
| 逐笔委托字段映射确认 | `schema_probe_report.md` | `已完成` | 写入报告 |
| 逐笔撤单字段映射确认 | `schema_probe_report.md` | `已完成` | 沪市按委托表 `委托类型=D` 扣减，深市按成交表 `成交代码=C` 扣减；字段缺失时进入低置信量化回退 |
| 十档盘口字段映射确认 | `schema_probe_report.md` | `部分完成` | 补覆盖率 |
| `order_lifetime_ms` 可得性确认 | `schema_probe_report.md` | `已完成` | 已接入 `order_lifecycle.py`，统一恢复 `order_age_minutes`；支持沪深差异规则、原始整数价/元价归一、成交表撤单扣减；缺失时低置信量化回退 |
| 85 维参考特征是否提供确认 | `schema_probe_report.md` | `未完成` | 决定直读或重算 |
| 市场上涨/下跌家数口径确认 | `market_pid_validation_report.md` | `已完成` | 20260707 默认 100 股回放已生成市场口径报告 |

### 4.2 状态特征与市场口径

| 任务 | 目标文件 | 验收标准 | 状态 |
|---|---|---|---|
| 建立 `StateFeature` 生成器 | `src/state_feature_builder.py` | 从 PID 结果生成 V1.4 字段集，单测覆盖 `rule_base` 与结构模式 | `已完成` |
| 保留 `debug_info` 必要字段 | `src/capital_model.py` | 至少包含 `mode_name / is_structural_output / capital_* / rule_error_*` | `已完成` |
| 市场 PID 口径报告 | `reports/validation/market_pid_validation_report.md` | 明确上涨/下跌家数、相对市场偏离计算 | `已完成` |
| 100 股回放报告 | `reports/validation/100_stock_replay_report.md` | 记录行数、缺失补位、耗时、警告 | `已完成` |
| 状态特征字段契约 | `reports/validation/state_feature_contract.md` | 对齐 `CapitalBehaviorEvent / CapitalRuleWindowFeature / StateFeature` | `已完成` |
| PID 窗口诊断契约 | `reports/validation/pid_window_diag_contract.md` | 覆盖 `P_state / P_wv_window / y_hat / m_eff / leakage` 字段 | `已完成` |
| 日级泄漏审计 | `reports/validation/leakage_audit_report.md` | 覆盖特征工程、标准化、规则层、运行时方法白名单 | `部分完成` |
| PID 稳定性报告 | `reports/validation/pid_stability_report.md` | 覆盖特征根/Jury、参数回退、m_eff 不确定性 | `部分完成` |

---

## 5. P2 模型升级清单

以下任务应在 P0/P1 重构稳定后执行，避免在模块边界不稳时叠加模型复杂度。

| 任务 | 目标文件 | 验收标准 | 状态 |
|---|---|---|---|
| 将 `capital_model.py` 从规则基线升级为弱监督/监督模型 | `src/capital_model.py` | 保留规则兜底；模型输出包含置信度和解释字段 | `待执行` |
| 将 `pattern_model.py` 从规则基线升级为聚类原型库 | `src/pattern_model.py` | 支持离线原型训练 + 在线最近原型归类 + 低置信回退 | `待执行` |
| 增加原型库版本管理 | `models/pattern_prototypes/` | 输出 `prototype_id` 与版本号 | `待执行` |
| 增加弱监督种子生成报告 | `reports/validation/weak_supervision_seed_report.md` | 明确种子规则、覆盖率、噪声风险 | `待执行` |

---

## 6. 测试与验收检查

| 检查项 | 验收标准 | 当前状态 | 重构后要求 |
|---|---|---|---|
| `main.py --help` 可执行 | 正常输出参数说明 | `已完成` | 必须保持 |
| schema 探针运行 | 正常输出 `schema_probe_report.md` | `已完成` | 报告内容补全 |
| 空目录输入 | 结构化告警与缺失文件列表 | `已完成` | 必须保持 |
| 样例结果导出 | 两个 CSV 字段正确 | `已完成` | 必须保持 |
| 市场状态文件导出 | 快照文件与报告文件可生成 | `已完成` | 必须保持 |
| `submit.zip` 打包 | 包含两个标准 CSV | `已完成` | 必须保持 |
| 股票清单过滤 | 仅输出清单股票 | `已完成` | 必须保持 |
| 缺失股票补齐 | 输出行数与股票清单一致 | `已完成` | 必须保持 |
| 单元测试 | 当前测试全部通过 | `已完成` | 每步重构后运行 |
| 集成测试 | 真实样本全链路回放 | `已完成` | 20260707 默认 100 股样本已完成回放，后续可扩展多日回放 |
| 性能测试 | 全市场切片耗时基准 | `部分完成` | `--profile` 可输出性能摘要，真实全市场基准待补 |
| 稳定性报告 | 聚类/分类多日稳定性 | `未完成` | P2 后补 |

建议新增测试：

1. `test_windowing.py`：已新增，覆盖 09:30-11:30、13:00-15:00、15:00 边界与窗口桶 schema。
2. `test_data_loader.py`：已新增，覆盖股票代码识别、中文规范文件名、缺失文件、股票池过滤与日期过滤。
3. `test_capital_rule_engine.py`：已新增，覆盖主动大单、被动 5 分钟阈值、缺失委托存活时间低置信回退。
4. `test_state_feature_builder.py`：已新增，覆盖 `rule_base` 结构字段置空、近似字段单列与 `capital_model` debug 契约。
5. `test_pid_observation_prediction_boundary.py`：验证观测值、预测值和截止时间不混用。
6. `test_pid_stability_fallback.py`：验证 Jury/特征根失败、m_eff 截断和高不确定性回退。
7. `test_data_leakage_runtime_guard.py`：验证未来数据注入、标准化截止时间和离线平滑方法阻断。
8. `test_zero_trade_policy.py`：验证 `skip / carry_forward / mark_only` 固定策略不读取未来窗口。
9. `test_pid_state_space_contract.py`：验证 `psi_t|t-1 / psi_t|t / y_t / y_hat_t+1|t` 时间戳和字段边界。
10. `test_mode_switch_lambda_config.py`：验证模式切换 lambda、滞回窗口和日内切换上限训练前固定。
11. `test_liquidity_comparability.py`：验证流动性分组、跨股可比标记和薄成交窗口降级。

---

## 7. 重构执行顺序

### 阶段 A：无行为变化拆分

1. 新建 `data_loader.py`，迁移 CSV 读取、股票目录扫描、缺失文件检查。
2. 新建 `windowing.py`，迁移时间窗口映射与窗口桶初始化。
3. 调整 `scheduler.py` 只负责编排，不改变输出结果。
4. 运行现有单元测试与一次样本回放，确认输出 CSV 字段和行数不变。

### 阶段 B：规则层显式化

1. 新建 `capital_rule_engine.py`。
2. 把现有 `signed_large_active_amount / signed_mix_qr_amount` 兼容输入转换为正式 `CH_rule / Q_rule / R_seed`。
3. 保留历史字段读取兼容，但内部主字段统一为新命名。
4. 增加规则层单测。
5. 输出 `state_feature_contract.md` 草案，作为后续模型升级字段依据。

### 阶段 C：PID 与 StateFeature 对齐

1. 调整 PID selector/shared/4D/5D 链路的模式名、字段名与选择入口说明。
2. 增加 full_5d/baseline_4d 外力贡献闭合校验和 `closure_impl_error`。
3. 新建 `state_feature_builder.py`。
4. 调整 `capital_model.py` 从 `StateFeature` 或 PID 结果读取结构字段。
5. 验证 `rule_base` 模式下结构字段为空、规则近似字段单列。
6. 冻结 `P_state / P_wv_window / y_observed / y_hat_next` 字段边界。
7. 接入稳定性回退、m_eff 不确定性和实时/离线方法白名单。

### 阶段 D：报告与回放

1. 产出冻结版 `schema_probe_report.md`。
2. 产出 `market_pid_validation_report.md`。
3. 产出 100 股样本回放报告。
4. 更新 README 中的重构后运行说明。
5. 产出 `pid_window_diag_contract.md`、`pid_stability_report.md` 和 `leakage_audit_report.md`。

### 阶段 E：模型升级

1. 升级 `capital_model.py` 弱监督/监督模型。
2. 升级 `pattern_model.py` 聚类原型库。
3. 增加模型版本、原型库版本和稳定性报告。

---

## 8. 当前结论

### 8.1 已实现内容

1. 比赛系统已具备可运行的日终批处理能力。
2. 已可输出 `pattern_reco.csv`、`predict_result.csv`、市场状态文件和 `submit.zip`。
3. 已支持真实中文 Level2 文件读取。
4. 已支持 100 股股票清单过滤、顺序保持和缺失补位。
5. 已有 PID 结构反解雏形，可作为重构基础。

### 8.2 主要技术债

1. `scheduler.py` 职责过重，是本轮重构第一优先级。
2. 规则层三类流尚未作为独立模块显式存在。
3. PID 输出仍保留历史兼容字段，需要与 V1.7 详细设计和最新算法口径完全对齐。
4. `StateFeature` 已落成独立生成器，后续重点转为观测/预测字段、稳定性和泄漏校验。
5. schema 冻结报告、市场口径报告、100 股回放报告尚未成套交付。
6. PID 窗口级/日级诊断文件和运行时方法白名单仍需落地。

### 8.3 不建议立即做的事

1. 不建议在模块拆分前直接引入复杂监督模型。
2. 不建议在 `scheduler.py` 继续堆叠新特征。
3. 不建议把 `Q_rule / R_seed` 直接写入 `capital_q / capital_retail`。
4. 不建议在缺失 `order_age_minutes` 时输出高置信散户结论。

---

## 10. 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| V1.6 | 2026-07-11 | 补充统一 PID/规则口径、默认 `baseline_4d` 运行态与市场 PID 主聚合约束 |
| V1.7 | 2026-07-13 | 对齐 PID/金融物理模型最新口径，补充观测预测分离、稳定性回退、等效质量不确定性、防泄漏审计与诊断交付物 |
| V1.9 | 2026-07-14 | 吸收评审结论并补齐诊断验收件，新增 `pid_window_diag_contract.md / leakage_audit_report.md / pid_stability_report.md`，同步 `m_eff` 诊断代理状态 |
| V1.8 | 2026-07-13 | 同步状态空间三式、模式切换 lambda、流动性可比性、薄成交窗口和 `m_slow` 工程优先级检查 |

---

## 9. 下一步执行建议

## 8.1 2026-07-14 补充验收项

新增 P0/P1 验收项：

- [ ] Rust 与 Python 统一识别 `empty_raw_file / null_filled_raw_file / invalid_raw_schema / no_effective_rows`
- [ ] 生成 `raw_data_quality_report.csv`
- [ ] `raw_data_quality_report.csv` 覆盖 `trade / order / quote` 三类原始文件
- [ ] 补全样本进入 `pid_daily_diag.csv`
- [ ] 补全样本日级诊断包含 `sample_origin = imputed`
- [ ] 补全样本日级诊断包含 `reason_code = missing_raw_data_imputed`
- [ ] 补全样本日级诊断固定 `m_eff_rank_eligible = false`
- [ ] Python 与 Rust 的 `pid_daily_diag.csv` 股票覆盖范围一致
- [ ] Python 与 Rust 的 `raw_data_quality_report.csv` 质量状态口径一致
- [ ] `100_stock_replay_report.md` 中 `stock_universe_size / imputed_output_count / missing_symbol_count` 与实际结果一致

1. 先做阶段 A：拆 `data_loader.py` 与 `windowing.py`，保持行为不变。
2. 再做阶段 B：显式 `capital_rule_engine.py`，统一 `CH_rule / Q_rule / R_seed`。
3. 然后做阶段 C：对齐 PID selector/shared/4D/5D 链路与 `StateFeature`。
4. 最后推进原选中任务：
   - 将 `capital_model.py` 从规则基线升级为弱监督/监督模型。
   - 将 `pattern_model.py` 从规则基线升级为聚类原型库。
   - 增加集成测试、性能测试与 100 股样本回放报告。

# PID算法与实现

文档定位：股票价格预测的过程控制模型与工程实现口径  
适用范围：规则层输入、PID 状态方程、贡献拆解、资金类型输出、运行模式与校验  
整理来源：`算法设计.md`、`PID原理与实现.md`、`统一资金类型判断规范.md`、`统一.md`

---

## 1. 文档目的

本文定义比赛系统中的 PID 过程控制模型，用于把窗口级行为代理流与价格变化解释为：

1. 价格闭合贡献：`c_p / c_i / c_d / eps`
2. 三类行为代理外力贡献：`capital_ch / capital_q / capital_retail`
3. 市场系统响应参数：`phi / theta`
4. 外力加载参数：`beta_ch / beta_q / beta_retail / beta_mix`

本文不重新定义金融-物理基础概念。基础模型见 [金融领域的物理学概念模型.md](金融领域的物理学概念模型.md)。

> **重要警告：本文不是标准 PID 控制器。**
>
> `c_p / c_i / c_d` 是行为代理外力、惯性记忆和速度变化修正的解释性拆分，
> 不是由误差积分、误差微分直接驱动的 `Kp / Ki / Kd` 控制律。不得直接套用
> 标准 PID 的调参经验、频域稳定性结论或控制器实现模板；工程实现应以本文的
> 参数状态递推、观测方程、样本外验证和字段边界为准。

### 1.1 命名说明

本文中的 “PID” 是类比命名，不等同于标准控制论中的误差驱动型 PID 控制器。

标准 PID 以当前误差、误差积分和误差微分为核心输入；本文中的 `c_p / c_i / c_d` 分别对应：

- `c_p`：行为代理流加载形成的外力冲击项
- `c_i`：价格速度的惯性/记忆项
- `c_d`：价格速度变化的修正项

因此，本文实质上是**带控制论解释的线性状态空间模型**。保留 PID 命名，是为了兼容既有设计和接口；新实现可使用中性别名 `contrib_force / contrib_inertia / contrib_adjust`，避免与标准 PID 控制律混淆。

### 1.2 与标准 PID 的对照

| 维度 | 标准 PID | 本文口径 |
| --- | --- | --- |
| 核心输入 | 误差 `e`、误差积分、误差微分 | 行为代理流、价格速度历史、速度变化历史 |
| P 项 | `Kp * e_t` | `beta_* U_*` 外力加载 |
| I 项 | `Ki * sum(e)` | `phi * Delta_q P_t-1` 惯性/记忆项 |
| D 项 | `Kd * de/dt` | `theta * D_driver_t` 速度变化修正 |
| 主要用途 | 闭环控制 | 状态解释、价格变化分解与诊断 |
| 是否标准 PID | 是 | 否，属于类比命名的状态空间模型 |

---

## 2. 核心原则

### 2.1 分层原则

系统分为三层：

| 层级 | 输出 | 职责 |
| --- | --- | --- |
| 规则层 | `CH_rule / Q_rule / R_seed` | 识别行为锚点与种子流 |
| PID 闭合层 | `c_p / c_i / c_d / eps` | 解释窗口级价格变化 |
| 外力贡献层 | `capital_ch / capital_q / capital_retail` | 输出三类行为代理资金贡献 |

### 2.2 禁止混用

必须遵守：

1. `CH_rule / Q_rule / R_seed` 不是最终资金贡献
2. `capital_ch / capital_q / capital_retail` 只能由 `beta_* U_*` 计算
3. `phi / theta` 只解释市场惯性与阻尼，不反解为资金身份
4. `C_I / C_D` 是系统响应项，不参与三类资金拆分
5. 规则兜底结果如需展示，必须写入 `capital_*_rule_approx` 或等价字段

### 2.3 控制论解释边界

`统一.md` 中的 `F = ma` 与 PID 统一框架可作为解释本模型的控制论背景，但工程实现仍以可闭合、可估计、可诊断为准。

本系统采用如下保守映射：

| 模型项 | 控制论含义 | 物理类比 | 工程边界 |
| --- | --- | --- | --- |
| `beta_* U_*` | 比例/外力加载项 | 行为代理流对价格速度的冲击柔度 | 只能生成对应 `capital_*` 贡献 |
| `phi * Delta_q P_t-1` | 惯性/记忆项 | 价格速度留存 | 不参与资金身份拆分 |
| `theta * D_driver_t` | 微分/变化率诊断项 | 速度变化的修正 | 当前差分方向下，正负号分别表示助推或抑制 |
| `epsilon_t` | 未解释扰动 | 噪声与未建模外力 | 不反解为资金类型 |

因此，`F = ma`、PID 与状态空间方程在本文中是同一组变量的不同解释层，不作为未经诊断的严格等价证明。

### 2.4 统一术语

为与基础概念文档保持一致，推荐在实现和接口层使用：

| 基础概念 | 工程建议命名 |
| --- | --- |
| `P_wv` | `P_wv_window`（兼容别名：`p_wv`） |
| `P_state(q)` | `P_state`（兼容别名：`p_state`） |
| `Delta_q P_state` | `Delta_q P_state`（兼容别名：`dq_price`、`price_velocity_q`） |
| `Delta_q^2 P_state` | `Delta_q^2 P_state`（兼容别名：`ddq_price`、`price_accel_q`） |

正式文档、跨模块接口和诊断文件优先使用左列的规范名称；右列仅用于兼容既有实现，不得在同一字段中混用多个别名。

---

## 3. 输入数据与规则层

### 3.1 原始数据

系统可使用：

- 逐笔成交
- 逐笔委托
- 撤单数据
- 盘口快照
- 集合竞价结果

### 3.2 行为代理类型

系统识别的是行为代理类型，不是真实账户身份：

| 类型 | 字段 | 含义 |
| --- | --- | --- |
| 游资 | `hot_money` / `CH_rule` | 主动塑造价格路径的高冲击行为 |
| 量化 | `quant` / `Q_rule` | 快速响应、做市、短周期博弈或高频型行为 |
| 散户 | `retail` / `R_seed` | 被动、分散、低同步性的跟随型行为 |

### 3.3 规则层输出

规则层按窗口聚合后输出：

```text
CH_rule_t
Q_rule_t
R_seed_t
```

这些字段是 PID 输入流，记为：

```text
U_ch,t = CH_rule_t
U_q,t = Q_rule_t
U_retail,t = R_seed_t
```

`U_*` 可以是有符号规则分数、标准化订单流或金额等价流，但必须在运行配置中声明口径：

| 口径 | 字段建议 | 用途 |
| --- | --- | --- |
| 有符号规则分数 | `U_*_score` | 状态方程估计与方向判断 |
| 金额等价流 | `U_*_amount` | 归一化柔度与等效质量计算 |
| 市值占比流 | `U_*_mv_ratio` | 跨股比较与稳定量诊断 |

若没有 `U_*_mv_ratio`，可以估计 `beta_*` 和 `capital_*`，但不得输出正式 `beta_norm_* / m_eff_*`，只能输出诊断近似并标记来源。`U_*_amount` 需要另行完成统一单位标准化后，才可进入跨股比较。

`beta_*` 的数值和量纲依赖 `U_*` 的口径。切换 `score`、`amount`、`mv_ratio` 时必须重新估计 `beta_*`，不同 `u_source_type` 下的 `beta_*` 不得直接比较，并须在配置和输出中保留口径标记。

若两个口径之间存在固定线性映射：

```text
U_mv_ratio,t = a_t * U_score,t
U_amount,t = b_t * U_score,t
```

则仅在 `a_t`、`b_t` 已知且在训练窗口内稳定时，才可近似换算：

```text
beta_mv_ratio ≈ beta_score / a_t
beta_amount ≈ beta_score / b_t
```

这只是“严格确定性缩放”下的启发式近似。若
`U_mv_ratio = a_t * U_score + eta_t`，且 `a_t` 随窗口变化或
`eta_t` 与误差项相关，回归系数还会受到测量误差、共线性和误差相关结构影响，
不能再按比例换算。现实中 `a_t`、`b_t` 通常随股票、窗口和流动性变化，
因此正式比赛实现默认重新估计，不采用跨口径直接换算。

在 4 维基线模式下：

```text
U_mix,t = Q_rule_t + R_seed_t
```

`U_mix` 是净效应输入，不保留 `Q_rule` 与 `R_seed` 的方向分解。当二者符号相反且冲突强度较高时，4 维模式只能输出 `capital_mix`，不能再把 `capital_mix` 结构化解释为量化或散户贡献。

### 3.4 规则层接口与误差边界

规则层不是账户身份识别器，而是行为代理流生成器。正式接口至少应提供：

```text
trade_date
symbol
window_id
window_start
window_end
CH_rule / Q_rule / R_seed
u_source_type
rule_confidence
rule_version
feature_cutoff_timestamp
```

若比赛数据不提供账户类型标签，`CH_rule / Q_rule / R_seed` 必须标记为启发式代理，不得在输出中写成真实资金身份。若无法稳定区分三路行为，应输出 `rule_confidence = low`，并降级到 `baseline_4d`、`capital_mix` 或 `unknown`。

规则层误差会传播到 `beta_*` 和 `capital_*`。至少应在离线敏感性分析中模拟代理误标，例如将 10% 的 `U_q` 注入 `U_ch`，记录 `beta_*` 偏差、结构化类型变化率和样本外误差。误标敏感性未通过时，不得输出高置信度的三类结构化身份解释。

---

## 4. PID 主状态方程

系统采用交易时间 `q` 轴上的价格状态与价格速度二层方程。为保持量纲清晰，先定义：

```text
v_q,t = (P_state(q_t) - P_state(q_t-1)) / Delta q_t
P_state,t = P_state,t-1 + v_q,t * Delta q_t
```

上面两行在当前实现中是**观测量定义与状态重构关系**，不是独立的不可观测状态演化模型：

- `v_q,t` 由相邻的 `P_state` 观测差分得到；
- `P_state,t` 可由 `P_state,t-1` 与 `v_q,t` 重构；
- 真正需要估计的参数状态是 `psi_t`，而不是把 `P_state` 与 `v_q` 再重复估计一遍。

因此，本文的核心统计关系是观测方程 `y_t = x_t · psi_t + epsilon_t`；“状态方程”主要指参数状态 `psi_t` 的递推。这样可以避免把恒等重构关系误称为严格的价格状态空间动力学。

标准状态空间口径固定为：

```text
# 参数状态转移：默认随机游走或带轻微收缩的随机游走
psi_t = psi_t-1 + eta_t
eta_t ~ N(0, Q)

# 唯一与价格观测交互的方程
y_t = x_t · psi_t + epsilon_t
epsilon_t ~ N(0, R)

# 实时预测使用先验参数，不使用吸收了 y_t 的后验参数
y_hat_t+1|t = x_t+1|t · psi_t|t-1
```

若采用滚动 OLS、递推最小二乘或其他估计器，也必须保留同样的时间戳语义：`psi_t|t-1` 用于预测，`psi_t|t` 只用于复盘、诊断或下一窗口更新。不得把 `P_state`、`v_q` 和 `psi_t` 同时作为三组互相独立的状态变量估计。

当采用等步长交易时间且 `Delta q_t = 1` 时，工程字段 `Delta_q P_t` 可作为 `v_q,t` 的数值简写。一般步长下，主状态方程应保留 `Delta q_t`，不能把价格变化量直接与价格状态相加。

其中价格速度 `v_q,t` 由下式刻画：

```text
v_q,t =
    beta_ch,t * U_ch,t-1
  + beta_q,t * U_q,t-1
  + beta_retail,t * U_retail,t-1
  + phi_t * v_q,t-1
  + theta_t * (v_q,t-1 - v_q,t-2)
  + epsilon_t
```

为避免把递推关系误读为“用未知的 `v_q,t` 自我预测”，统一采用：

```text
# 观测量：由价格状态差分直接计算
y_t = Delta_q P_state,t
v_q,t = y_t / Delta q_t

# 模型观测方程：用于参数估计和当期闭合
y_t = x_t · psi_t + epsilon_t

# 模型预测值：用于实时预测和比赛提交
y_hat_t+1|t = x_t+1|t · psi_t|t-1
v_hat_q,t+1|t = y_hat_t+1|t / Delta q_t+1
```

其中 `y_t` 是已观测的价格差分，`y_hat_t+1|t` 是模型预测值，二者不能使用同一字段覆盖。主状态方程是观测方程的展开式，不是第三种独立的计算流程。

其中：

- `v_q,t`：按 `Delta q` 归一化后的交易时间价格速度；等步长时可用 `Delta_q P_t` 表示
- `U_*`：规则层行为代理流
- `beta_*`：外力加载系数；`beta_t` 表示针对观测向量 `x_t` 的当前窗口响应参数
- `phi`：惯性系数
- `theta`：速度变化修正系数，具体方向由符号与稳定性诊断决定；`theta_t` 表示对 `D_driver_t = v_q,t-1 - v_q,t-2` 的当前窗口响应参数
- `epsilon`：未解释扰动

一级闭合关系为：

```text
v_q,t = C_P,t + C_I,t + C_D,t + epsilon_t
```

若需要恢复价格状态变化量，则使用：

```text
Delta_q P_state,t = Delta q_t * (C_P,t + C_I,t + C_D,t + epsilon_t)
```

在等步长 `Delta q_t = 1` 的工程口径下，才可省略乘法并把 `v_q,t` 记作 `Delta_q P_t`。

其中：

```text
C_P,t = beta_ch,t * U_ch,t-1
      + beta_q,t * U_q,t-1
      + beta_retail,t * U_retail,t-1

C_I,t = phi_t * v_q,t-1

D_driver_t = v_q,t-1 - v_q,t-2

C_D,t = theta_t * D_driver_t
```

若工程上需要引入残差记忆项 `kappa_I * epsilon_t-1`，必须同步加入主状态方程与状态向量；否则不纳入正式闭合贡献，避免破坏 `v_q,t = C_P,t + C_I,t + C_D,t + epsilon_t` 的定义。

这里采用统一时间戳口径：

- `x_t` 由截至 `t-1` 的已知输入和历史状态构成
- `psi_t` 是针对 `y_t = v_q,t` 的当期参数状态
- `beta_t`、`theta_t` 与 `x_t` 配对使用，不构成前瞻性偏差
- 历史解释、复盘和参数画像可以使用基于 `y_t` 更新后的 `psi_t`
- 实时预测、比赛提交和在线决策必须使用更新前的先验或滤波预测量，例如 `psi_t|t-1`、`beta_t|t-1`、`theta_t|t-1`

若用于预测下一窗口，则应单独写作：

```text
y_hat_t+1|t = x_t+1|t · psi_t|t-1 + epsilon_t+1|t
v_hat_q,t+1|t = y_hat_t+1|t / Delta q_t+1
```

比赛默认采用以下构造规则：

```text
x_t+1|t =
[
  v_q,t,
  U_ch,t-1,
  U_q,t-1,
  U_retail,t-1,
  D_driver_t
]
```

其中：

- `U_*,t-1` 是最近一个已确认窗口的规则流；当前窗口尚未结束时，不得把窗口内尚未观测完的数据提前聚合为 `U_*,t`
- 规则流必须记录 `feature_cutoff_timestamp` 和 `rule_latency_windows`；若规则识别至少需要完整窗口结束后才能稳定生成，则预测只能使用最近一个完整窗口的结果
- 若规则层另有独立预测器，可替换为 `U_*,t|t-1`，但必须记录 `u_forecast_method`，并在训练、验证、提交阶段保持一致
- `psi_t` 默认指卡尔曼滤波的一步先验 `psi_t|t-1`；若使用滚动 OLS，必须固定回看窗口、权重和更新时点，并将其标记为 `estimator_method = rolling_ols`
- 点预测时令 `epsilon_t+1|t = 0`，表示条件均值预测；若需要区间预测，则另行输出基于 `R` 或滚动残差方差的预测区间，不得把未知噪声直接填入点预测

上述规则适用于 `full_5d`；`baseline_4d` 删除三路输入中的 `U_q`、`U_retail`，改用 `U_mix,t-1`。这样可避免不同实现对 `x_t+1|t` 的自由解释。

时序关系固定为：

```text
历史数据 <= t-1
    -> 构造 x_t
    -> 得到 psi_t|t-1
    -> 观测 v_q,t 后更新为 psi_t|t
    -> 用 x_t+1|t 和 psi_t|t-1 预测 v_q,t+1|t
```

其中最后一步若在窗口 `t` 已完整结束、且比赛规则允许使用该窗口观测，则可以使用更新后的 `psi_t|t` 预测下一窗口；若提交时点早于窗口结束，必须继续使用先验 `psi_t|t-1`。提交接口应记录 `prediction_cutoff_timestamp`。为兼容旧接口，`v_q,t+1|t` 可以保留为别名，但正式输出建议使用 `v_hat_q,t+1|t`。

### 4.1 坐标口径

`Delta_q P_t` 默认基于等步长交易时间窗口，`Delta q = 1`。若工程输入来自固定自然时间窗口，例如 5 分钟窗口，则必须同时记录：

```text
Delta_t V
dV_dt_approx = Delta_t V / Delta t
turnover_rate = Delta_t W / Delta t
```

其中：

```text
Delta_t W ≈ P_t * Delta_t V
```

这些字段不直接进入主状态方程，但用于解释同样的 `Delta_q P` 为什么会在高成交窗口和低成交窗口中表现出不同的冲击强度。

### 4.2 残差记忆扩展

默认模型不启用残差记忆项。只有同时满足以下条件时，才允许启用：

1. 残差记忆筛查同时满足：滚动残差一阶自相关 `abs(rho_eps_1)` 持续高于
   预设阈值，且 Ljung-Box 或等价白噪声检验在预先固定的窗口长度和多重检验
   校正后仍未通过。两者是同一筛查阶段的互补证据，不是两次独立显著性证明。
2. 离线诊断显示残差记忆项在同类股票或历史样本中对残差方差、样本外误差
   或白噪声检验有稳定改善。
3. 该改善不是由输入共线性、窗口重叠或异常窗口驱动。
4. 增加参数维度后的有效自由度、条件数和样本外惩罚仍在预设范围内。

“稳定改善”默认要求：时间顺序样本外 MSE 相对基线下降至少 `5%`，并在至少
`10` 个连续**评估窗口**中不低于基线。评估窗口默认以交易日为单位；
若使用日内窗口，必须在配置中明确 `evaluation_window_unit` 和对应跨度。
滚动检验的显著性应采用预先固定的多重检验校正或分组汇总规则，不能把每个
窗口的 `p < 0.05` 直接当成独立证据。

残差记忆扩展从 5 维增加到 6 维，至少应记录：

```text
parameter_count_before
parameter_count_after
effective_sample_size
degrees_of_freedom_ratio
condition_number_after
```

若 `degrees_of_freedom_ratio`、条件数或样本外惩罚超过训练前固定阈值，
即使残差相关显著，也不得启用扩展。

推荐分两阶段执行：

- **离线阶段**：在历史样本上比较“无残差记忆项”与“有残差记忆项”两种结构，决定默认是否启用
- **在线阶段**：只监控条件 1 和 2 并产生告警，不自动切换模型结构；是否启用由训练前固定配置决定，避免流式结构切换和前瞻性偏差
- 若在线残差自相关连续 `M = 20` 个窗口低于 `0.1`，只标记 `residual_memory_decay_alert = true`；是否在下一交易日或下一训练周期禁用，必须经过固定的离线复核流程，不在当前提交过程中临时切换

启用后，主方程扩展为：

```text
v_q,t =
    beta_ch,t * U_ch,t-1
  + beta_q,t * U_q,t-1
  + beta_retail,t * U_retail,t-1
  + phi_t * v_q,t-1
  + theta_t * D_driver_t
  + kappa_eps,t * epsilon_t-1
  + epsilon_t
```

5 维模式扩展为 6 维：

```text
psi_t^(6) = [phi_t, beta_ch,t, beta_q,t, beta_retail,t, theta_t, kappa_eps,t]^T
x_t^(6) = [v_q,t-1, U_ch,t-1, U_q,t-1, U_retail,t-1, D_driver_t, epsilon_t-1]^T
```

闭合贡献同步扩展：

```text
C_E,t = kappa_eps,t * epsilon_t-1
v_q,t = C_P,t + C_I,t + C_D,t + C_E,t + epsilon_t
```

输出字段应增加 `c_e = C_E,t` 和 `residual_memory_enabled`。未启用时不得把 `epsilon_t-1` 暗含进 `C_I,t`。

---

## 5. 运行模式

### 5.1 `rule_base`

规则展示模式，仅输出规则近似，不输出结构化 PID 外力贡献。

要求：

- `is_structural_output = false`
- `capital_ch / capital_q / capital_retail` 置空或不作为模型字段输出
- 规则展示值写入 `capital_*_rule_approx`

### 5.2 `baseline_4d`

稳健基线模式，状态向量为：

```text
psi_t^(4) = [phi_t, beta_ch,t, beta_mix,t, theta_t]^T
```

观测向量为：

```text
x_t^(4) = [Delta_q P_t-1, U_ch,t-1, U_mix,t-1, D_driver_t]^T
```

观测方程：

```text
Delta_q P_t = x_t^(4) · psi_t^(4) + epsilon_t
```

该模式输出：

- `capital_ch`
- `capital_mix`
- `c_p / c_i / c_d / eps`

若需要展示 `capital_q / capital_retail`，只能按 `Q_rule` 与 `R_seed` 在 `U_mix` 中的绝对权重做诊断分摊。分摊使用的时间索引应与 `capital_mix,t = beta_mix,t * U_mix,t-1` 保持一致。

符号冲突规则：

```text
mix_sign_conflict_t = sign(Q_rule_t-1) != sign(R_seed_t-1)
mix_conflict_ratio_t = min(abs(Q_rule_t-1), abs(R_seed_t-1)) / (max(abs(Q_rule_t-1), abs(R_seed_t-1)) + eps0)
```

其中默认建议：

```text
eps0 = 1e-8
```

若 `mix_sign_conflict_t = true` 且 `mix_conflict_ratio_t >= 0.3`，则：

- 4 维模式仍可用于价格闭合和 `capital_mix` 估计
- 不输出结构化 `capital_q / capital_retail`
- `capital_type` 不得基于该分摊判断为 `quant` 或 `retail`
- 若业务必须拆分 `quant / retail`，应切换到 `diag_5d / full_5d` 或降级为带来源标记的规则展示
- 推荐输出 `capital_type = mixed`

### 5.3 `diag_5d / full_5d`

增强 5 维模式，状态向量为：

```text
psi_t^(5) = [phi_t, beta_ch,t, beta_q,t, beta_retail,t, theta_t]^T
```

观测向量为：

```text
x_t^(5) = [Delta_q P_t-1, U_ch,t-1, U_q,t-1, U_retail,t-1, D_driver_t]^T
```

观测方程：

```text
Delta_q P_t = x_t^(5) · psi_t^(5) + epsilon_t
```

启用条件：

1. `Q_rule` 与 `R_seed` 可辨识
2. 三路输入相关性不过高
3. `theta` 的 D 驱动项有效
4. 残差诊断通过
5. 5 维结果优于或不劣于 4 维基线

建议至少通过以下一项可辨识性检验：

| 检验 | 默认建议阈值 | 用途 |
| --- | --- | --- |
| 设计矩阵条件数 `cond(X'X)` | `< 50`，高流动性建议 `< 30` | 防止病态回归 |
| 方差膨胀因子 `VIF` | `< 10`，高流动性建议 `< 5` | 限制多重共线性 |
| Gram 矩阵最小特征值 | `> 1e-6` | 避免近似退化 |
| 输入两两相关系数 | `abs(corr) < 0.9` | 快速筛查 |

若检验失败，则必须回退到 `baseline_4d` 或 `rule_base`，不得继续输出 5 维结构化贡献。

实时模式切换需加入滞回规则，建议：

- 至少连续 `k = 5` 个窗口通过可辨识性检验才允许从 4 维切换到 5 维
- 至少连续 `k = 3` 个窗口失败才回退到 4 维
- 切换事件应输出 `mode_switch_flag` 和触发原因，避免无记录的频繁跳变
- 单个交易日内默认最多切换 `2` 次；超过后锁定在最近一次稳定模式，直到下一个交易日或人工复位

上述 `5 / 3 / 2` 只是保守的工程默认值，不是理论常数。敏感性分析至少测试以下三组：

| 组别 | 通过窗口 | 失败窗口 | 单日上限 |
| --- | ---: | ---: | ---: |
| A | 3 | 2 | 4 |
| B（默认） | 5 | 3 | 2 |
| C | 8 | 5 | 1 |

每组至少记录模式切换频率、回退次数、样本外误差、闭合误差和结构化输出覆盖率，最终在训练前固定一组配置。

阈值的解释必须结合窗口粒度：若窗口长度为 `L` 分钟，连续通过阈值
对应的最短切换确认时间约为 `k_pass * L`，连续失败阈值对应约为
`k_fail * L`。例如 5 分钟窗口下，默认 `5 / 3` 分别约为 25 分钟和
15 分钟；这不是系统稳定性的理论时间常数，只是抗噪声确认延迟。
不同流动性组和波动率组应至少报告该延迟、切换频率和样本外误差。
当窗口较长或比赛更重视响应速度时，较大的 `k` 会带来切换滞后；
此时只能在训练前降低 `k`，并同步评估上述指标，不能在比赛运行中临时调整。

滞回规则的目的，是把短暂的可辨识性噪声与真正的结构变化区分开。切换时应加入结构稳定性约束：

- 从 4 维切换到 5 维时，优先用 4 维参数作为 5 维滤波器的初始化，并记录新增参数的初值来源
- 若切换后连续窗口的预测误差、最大特征根模或参数跳变量显著恶化，应触发回退
- `mode_switch_penalty` 可按以下诊断口径计算：

```text
mode_switch_penalty =
    lambda_switch * switch_count
  + lambda_jump * mean(parameter_jump_norm)
  + lambda_error * max(0, error_5d - error_4d)
```

其中三个 `lambda` 必须在训练前固定。建议通过训练集内的时间序列交叉验证，
以“样本外误差 + 切换次数约束 + 输出覆盖率约束”的预先固定目标选择，
并在独立验证期锁定。该分数只用于离线比较和回退决策。软切换或贝叶斯模型平均
属于后续增强方案，不作为当前比赛默认要求。

工程默认搜索范围可取：

```text
lambda_switch in {0.05, 0.1, 0.2}
lambda_jump   in {0.5, 1.0, 2.0}
lambda_error  in {5.0, 10.0, 20.0}
```

其中 `parameter_jump_norm` 建议按参数后验标准差或滚动历史标准差归一化。若新增维度后的 `beta_q / beta_retail` 任一参数跳变超过 `2 * rolling_param_std`，且预测误差未同步改善，可标记为短暂可辨识性噪声；若跳变持续不少于 `K_up = 5` 个窗口、方向稳定且样本外误差不劣于 4 维基线，才视为候选结构变化。滞回参数的敏感性分析至少报告 `K_up / K_down / max_switch_per_day` 三组配置下的样本外误差、切换次数、结构化输出覆盖率和回退次数。

---

## 6. 参数估计

推荐使用状态空间模型、卡尔曼滤波与 RTS 平滑估计：

```text
psi_t = psi_t-1 + eta_t
Delta_q P_t = x_t · psi_t + epsilon_t
```

其中：

- `psi_t`：状态参数向量
- `eta_t`：状态漂移噪声
- `epsilon_t`：观测噪声

为避免先验、后验和价格状态 `P_state` 混用，协方差统一记为 `Sigma`。默认的一步卡尔曼递推口径为：

```text
psi_t|t-1 = psi_t-1|t-1
Sigma_t|t-1 = Sigma_t-1|t-1 + Q
y_t = x_t' * psi_t + epsilon_t
K_t = Sigma_t|t-1 * x_t
      / (x_t' * Sigma_t|t-1 * x_t + R)
psi_t|t = psi_t|t-1
          + K_t * (y_t - x_t' * psi_t|t-1)
Sigma_t|t = (I - K_t * x_t') * Sigma_t|t-1
```

其中 `Q` 是参数漂移协方差，`R` 是观测噪声方差。实时预测使用 `psi_t|t-1`；当期观测到达后才得到 `psi_t|t`。RTS 或其他平滑器得到的后验轨迹只用于离线复盘，不得替代实时先验。

估计目标：

- `phi_t`
- `theta_t`
- `beta_ch,t`
- `beta_q,t` 或 `beta_mix,t`
- `beta_retail,t`

5 维模型默认逐股票独立更新，以控制协方差矩阵规模。实现可采用向量化或批量矩阵更新，但必须记录运行预算；不要求比赛提交阶段实时运行 RTS 平滑。建议至少输出：

```text
compute_budget_ms
runtime_warning_flag
estimator_method
```

当单窗口更新超过预先设定的预算时，应优先回退到 `baseline_4d`、固定参数或最近一次有效滤波状态，不得为了追赶时延调用离线平滑或读取未来窗口。

为降低 5 维短窗口过拟合风险，可使用固定先验或弱正则化：

```text
psi_0 ~ N(psi_prior, Lambda_prior^-1)
```

其中 `psi_prior`、`Lambda_prior`、参数边界和 `Q` 必须在训练前固定。先验只用于稳定初始化和约束漂移，不得根据提交期的样本外结果动态回调。

参数解释必须降级为状态解释，不得直接写作长期固定基因。

实时预测只能使用滤波估计或递推更新结果；RTS 平滑会使用未来观测，更适合离线复盘、参数画像和赛后解释。

### 6.0 过程噪声与参数边界

若采用状态随机游走：

```text
psi_t = psi_t-1 + eta_t
eta_t ~ N(0, Q)
epsilon_t ~ N(0, R)
```

则 `Q` 与 `R` 需要按流动性分组或品种分组设定，不能完全留空。默认建议：

- `R`：由观测残差的滚动方差初始化
- `Q`：取 `R` 的较小比例起步，例如 `Q = lambda * I`，`lambda` 可在 `1e-4 ~ 1e-2` 范围内网格或分组调优
- 高流动性股票可用更小 `Q`
- 事件驱动型或高波动股票可适度放宽 `Q`
- 若条件允许，可使用自适应 `Q/R` 更新或按波动率、成交量分位动态重标定

`lambda = 1e-4 ~ 1e-2` 是工程搜索范围：低值对应参数近似不变，高值对应参数更快适应状态变化。正式提交前应固定具体值或分组值，不得根据提交日表现临时回选。

推荐参数边界：

| 参数 | 默认建议边界 | 说明 |
| --- | --- | --- |
| `phi` | `[-1, 1]`，常用稳定区间 `[0, 1]` | 防止惯性爆炸 |
| `theta` | `[-1, 1]` | 允许阻尼、反转或助推 |
| `beta_*` | 按样本分位裁剪 | 防止极端冲击污染 |
| `kappa_eps` | `[-0.5, 0.5]` 起步 | 控制残差记忆项过拟合 |

`phi` 与 `theta` 必须联合检查，不能只分别检查边界。对无外力齐次项：

```text
r^2 - (phi + theta) * r + theta = 0
r_1,2 = ((phi + theta) +/- sqrt((phi + theta)^2 - 4 * theta)) / 2
```

正式稳定性要求：

```text
abs(r_1) < 1
abs(r_2) < 1
```

等价的二阶 Jury 条件为：

```text
abs(theta) < 1
1 - phi > 0
1 + phi + 2 * theta > 0
```

部分资料将二阶条件写成额外的 `abs(a1) < 1 + a0`。在本模型中，
`abs(theta) < 1` 已保证 `1 + a0 > 0`，而两个端点条件
`1 + a1 + a0 > 0`、`1 - a1 + a0 > 0` 合并后正好给出该绝对值不等式，
所以它不是当前特征方程下遗漏的独立约束。工程实现仍应直接计算特征根最大模，
并将 Jury 检查作为冻结窗口的代数筛查。

`abs(phi + theta) < 1` 只作为启发式快速筛查，既不是充分条件，也不是所有稳定组合的必要条件。例如 `phi = 0.5, theta = 0.9` 满足 Jury 条件，但 `abs(phi + theta) = 1.4`。正式判断必须使用特征根或 Jury 条件。若联合稳定性失败，必须设置 `param_stability_flag = fail`，并回退到稳定的基线参数或 `baseline_4d`。

稳定性诊断应按两种口径输出：

- `param_stability_pointwise`：当前或先验参数的冻结窗口检查
- `param_stability_rolling`：滚动窗口平均参数、最大特征根模和冲击响应衰减检查

时变 `psi_t` 不能仅凭单点 Jury 通过就宣称全局稳定。

稳定性检查默认按窗口执行。若当前窗口失败：

1. 保留最近一次通过稳定性检查的参数快照
2. 将当前参数协方差放大固定倍数 `covariance_inflation = 1.5`，等待后续有效观测重新收敛
3. 当前窗口结构化输出降级为 `baseline_4d` 或 `unknown`
4. 记录 `stability_fallback_flag`，不直接清空历史参数序列

若连续 `3` 个窗口失败，则进入日级人工/离线复核；不得仅凭单个异常窗口重置滤波器。

### 6.1 等效质量估计

`统一.md` 提出的 `m = 1 / beta` 可作为等效质量的启发式来源，但正式实现必须使用归一化和稳定性检验后的口径。

推荐定义：

```text
beta_norm_* = (capital_* / P_state) / U_*_mv_ratio
capital_* = beta_*_mv_ratio * U_*_mv_ratio
beta_norm_* = beta_*_mv_ratio / P_state
m_eff_* = 1 / max(abs(beta_norm_*), beta_norm_floor)
```

上述三行必须使用同一 `U_*_mv_ratio` 口径重新估计得到的 `beta_*_mv_ratio` 与 `capital_*`。不得用 `U_*_score` 或 `U_*_amount` 口径生成的 `capital_*` 再除以 `U_*_mv_ratio`，否则会把规则分数、金额流和市值占比流混在同一个归一化指标中。若暂时只能使用非市值占比口径，应输出 `beta_norm_unit = score_response / amount_response` 并设置 `m_eff_rank_eligible = false`。

其中 `beta_norm_floor` 建议按流动性分组设定，默认可取：

```text
beta_norm_floor = max(1e-6, p10(abs(beta_norm_*)))
```

其中 `p10` 只有在至少 `N_floor = 30` 个历史有效样本后才启用；样本不足时固定使用 `1e-6`，并输出 `insufficient_history_flag = true`。该下限只是“最小可识别响应”的工程保护线，不是经济学常数。这样可以避免 `beta_norm_* -> 0` 时 `m_eff_*` 数值发散。若触发截断，建议同时输出：

```text
m_eff_clipped_flag = true
```

若 `m_eff_clipped_flag = true`，该值只能用于告警和单股诊断，不得进入跨股排名、稳定量分位比较或正式质地评分。

由于 `m_eff` 是 `beta_norm` 的倒数，其不确定性必须单独记录。对点估计可采用一阶 Delta method 近似：

```text
se_m_eff ≈ se_beta_norm
            / max(abs(beta_norm), beta_norm_floor)^2

var_m_eff ≈ var_beta_norm
              / max(abs(beta_norm), beta_norm_floor)^4
```

上述 Delta method 只适用于 `abs(beta_norm) > beta_norm_floor` 的未截断区域。
若 `abs(beta_norm) <= beta_norm_floor`，截断函数在该区域对输入的导数为 0，
但这不代表真实参数不确定性为 0；该结果应标记为“截断导致不可估计”，
不应生成看似精确的标准误或置信区间。

建议增加以下字段：

```text
m_eff_se
m_eff_ci_low
m_eff_ci_high
m_eff_uncertainty_flag
```

`var_beta_norm` 的来源必须随估计器记录：卡尔曼滤波可取 `Sigma_t|t` 中对应 `beta_*_mv_ratio` 的后验方差并按 `P_state` 缩放；滚动 OLS 可取异方差稳健协方差矩阵的对应元素；样本较少或残差重尾时优先使用按时间块重采样的稳健自助法。Delta method 默认要求 `beta_norm` 估计量在当前窗口族内近似正态，且未触发截断；该条件不满足时，应使用训练前固定的似然比、参数后验分位数或 block bootstrap 构造置信区间。

置信区间可按训练阶段固定的正态近似、稳健自助法或参数后验计算。若区间过宽、跨越业务判定边界、`beta_norm` 接近截断下限，或发生截断，则必须设置 `m_eff_uncertainty_flag = true`，并将 `m_eff_rank_eligible = false`；此时只允许做单股诊断，不得进入跨股排名或正式质地画像。训练阶段应做覆盖率抽样验证，例如在历史滚动窗口中检查 `m_eff_ci_low / m_eff_ci_high` 对后续稳定估计的经验覆盖率是否接近预设置信水平。

同时建议输出：

```text
beta_norm_sign = sign(beta_norm_*)
sign_flip_flag = sign(beta_norm_t) != sign(beta_norm_t-1)
```

以保留“响应方向”信息。`m_eff_*` 本身用于描述响应难易程度，`beta_norm_sign` 用于描述方向，二者应联合解读。

正式的 `beta_norm_*` 和 `m_eff_*` 只允许在 `U_*_mv_ratio` 口径下生成：

```text
beta_norm_* = (capital_* / P_state) / U_*_mv_ratio
```

这里有一个必须满足的口径约束：`capital_*` 必须由同一 `U_*_mv_ratio`
输入口径下的响应系数重新计算，即：

```text
capital_* = beta_*_mv_ratio * U_*_mv_ratio
beta_norm_* = beta_*_mv_ratio / P_state
```

不得用 `U_*_score` 或 `U_*_amount` 生成的 `capital_*`，再除以
`U_*_mv_ratio`。前一种写法只是同口径定义的展开式；后一种混用会使结果失去明确量纲。
`beta_norm_*` 的推荐量纲是“每个交易时间步的价格收益率 / 市值占比流”，
在固定 `q_type`、窗口粒度和输入口径下才可进行相对比较。

三种输入口径的边界如下：

| 输入口径 | `beta_norm` 解释 | 是否可用于正式 `m_eff` |
| --- | --- | --- |
| `U_*_score` | 价格响应 / 规则分数，只能做同口径诊断 | 否 |
| `U_*_amount` | 价格响应 /（金额占市值），受窗口和金额单位影响 | 否，除非另行完成单位标准化 |
| `U_*_mv_ratio` | 价格响应 / 市值占比，在固定 `q` 步长下可作跨股比较 | 是 |

其中 `capital_* / P_state` 必须明确表示归一化价格贡献；若字段仍沿用 `capital_*` 命名，也必须在接口说明中标记 `capital_unit = price_contribution`。建议同时输出 `beta_norm_unit`，不得再笼统标记为“无量纲”。

若使用 4 维模式，则只输出：

```text
beta_norm_ch
beta_norm_mix
m_eff_ch
m_eff_mix
```

若使用 5 维模式，则可输出：

```text
beta_norm_ch
beta_norm_q
beta_norm_retail
m_eff_ch
m_eff_q
m_eff_retail
```

慢变质量分量可写为：

```text
m_eff,t = m_slow,t + m_fast,t
```

其中 `m_slow,t` 用于候选个股质地画像，`m_fast,t` 用于日内扰动诊断。`m_slow,t` 必须经过跨日稳定性检验后，才能进入比赛提交或个股画像字段。

实时与离线口径必须分开：

- 实时预测：`m_slow,t` 只能使用截至 `t-1` 的历史窗口或历史交易日递推得到。默认优先使用对 `m_eff` 序列做 EWMA：

```text
alpha = 2 / (N + 1)
m_slow,t = alpha * m_eff,t-1 + (1 - alpha) * m_slow,t-1
```

其中 `N` 为预先固定的 `lookback_days`；若使用滚动中位数，窗口同样固定为 `N`
- 离线复盘：可以使用 RTS 平滑、HP 滤波或全样本稳健趋势提取，但必须标记为 `offline_smooth`
- 比赛提交：若目标是实时预测，不得使用包含当日未来窗口信息的 `m_slow,t`

推荐优先级为：`ewma_realtime` > `rolling_median_realtime` > `kalman_filter_realtime`。该排序不是理论最优性声明，而是比赛工程默认：EWMA 参数少、计算稳定、前瞻风险低，适合作为基线；滚动中位数对异常窗口更稳健，但响应较慢；卡尔曼滤波表达能力更强，但依赖状态方程、`Q/R` 和初始化设定，超参数敏感性更高，只有在离线验证稳定优于基线时才建议作为默认。`kalman_smoother_offline`、RTS 和 HP 平滑只用于离线复盘。

应增加字段：

```text
m_slow_method = ewma_realtime / rolling_median_realtime / kalman_filter_realtime / kalman_smoother_offline / rts_offline / hp_offline
```

推荐固定历史窗口长度后再提取 `m_slow`，不得在比赛提交阶段按“稳定性最好”自适应回选窗口。默认可选：

- `lookback_days = 20`
- `lookback_days = 60`

二者应在训练前固定，并写入运行配置。若需要比较不同窗口长度，只能在离线实验阶段完成，不得在提交阶段动态切换。

---

## 7. 贡献计算

### 7.1 PID 闭合贡献

输出：

```text
c_p = C_P,t
c_i = C_I,t
c_d = C_D,t
eps = epsilon_t
```

闭合校验：

```text
closure_impl_error = v_q,t - (c_p + c_i + c_d + eps)
# 兼容旧接口
closure_error = closure_impl_error
```

`closure_error` 的作用是**实现一致性检查**，用于验证字段拆解、索引和数值计算无误。
它不是独立模型有效性的充分证据。工程上应把两类误差分开：

```text
closure_impl_error = v_q,t - (c_p + c_i + c_d + eps)
model_residual = eps
```

`closure_impl_error` 的阈值应接近数值精度，由 `closure_numeric_tolerance`
预先配置；`model_residual` 的大小、白噪声性和样本外预测能力才属于模型适配性诊断。

若 `closure_impl_error` 在大量窗口持续接近机器精度，不能直接视为模型更优，应同时检查是否误用了当期后验参数、未来窗口字段或过多自由参数；闭合过好与样本外预测更好不是同一结论。

独立验证应至少补充：

1. 样本外预测误差是否优于基线模型
2. 残差是否接近白噪声
3. 参数是否稳定且未越界
4. 5 维模式是否相对 4 维模式带来稳健改善

推荐同时保留相对误差口径，例如：

```text
closure_error_ratio = abs(closure_impl_error) / max(1e-8, abs(v_q,t))
```

以避免只看绝对阈值时，对不同价格量级或不同波动区间产生不一致的宽严程度。

### 7.2 三类外力贡献

正式口径：

```text
capital_ch,t = beta_ch,t * U_ch,t-1
capital_q,t = beta_q,t * U_q,t-1
capital_retail,t = beta_retail,t * U_retail,t-1
```

这里的 `capital_*` 是历史接口名称，数学上表示对应行为代理流对 `v_q` 的价格贡献，不表示可直接与账户现金余额相加的资金金额。若输出真实金额流，必须使用独立字段并声明金额单位。

4 维模式下：

```text
capital_ch,t = beta_ch,t * U_ch,t-1
capital_mix,t = beta_mix,t * U_mix,t-1
```

若做诊断分摊，时间索引应与 `capital_mix,t = beta_mix,t * U_mix,t-1` 保持一致：

```text
capital_q,t = capital_mix,t * abs(Q_rule_t-1) / (abs(Q_rule_t-1) + abs(R_seed_t-1) + eps0)
capital_retail,t = capital_mix,t * abs(R_seed_t-1) / (abs(Q_rule_t-1) + abs(R_seed_t-1) + eps0)
```

若工程实现选择当前窗口规则值做展示分摊，必须单独标记为当前窗口诊断口径：

```text
capital_q_diag_current,t = capital_mix,t * abs(Q_rule_t) / (abs(Q_rule_t) + abs(R_seed_t) + eps0)
capital_retail_diag_current,t = capital_mix,t * abs(R_seed_t) / (abs(Q_rule_t) + abs(R_seed_t) + eps0)
```

诊断分摊必须带来源标记，不能误认为完整 5 维结构输出。

当 `mix_sign_conflict_t = true` 且 `mix_conflict_ratio_t >= 0.3` 时，上述诊断分摊公式默认禁用；若为调试目的强制输出，必须写入 `diagnostic_only = true` 并禁止进入 `capital_type`、`capital_intention` 和稳定量诊断。

### 7.3 禁止反解公式

不得使用如下形式生成三类资金贡献：

```text
CH = (C_P + C_I - C_D) / 2
Q  = (C_P + C_D - C_I) / 2
R  = (C_I + C_D - C_P) / 2
```

原因：

- `C_I` 是市场惯性响应
- `C_D` 是市场阻尼响应
- 二者不属于某一类外部行为代理流

---

## 8. 资金类型输出

### 8.1 `capital_type`

若 `is_structural_output = true`，主判断来自：

```text
abs(capital_ch)
abs(capital_q)
abs(capital_retail)
```

最大者对应主导行为代理类型：

- `hot_money`
- `quant`
- `retail`

若结构化输出不可用，则使用规则兜底，但必须标记来源。

补充规则：

- 若 4 维模式发生高强度符号冲突并禁止结构化分摊，推荐输出 `capital_type = mixed`
- 若结构化输出不可用且规则层也无法给出稳定判断，则输出 `capital_type = unknown`
- 若要输出单一类型，建议同时满足显著性条件，例如：

```text
max(abs(capital_*)) / (abs(capital_ch) + abs(capital_q) + abs(capital_retail) + eps0) > 0.5
```

否则降级为 `mixed` 或 `unknown`。

### 8.2 `capital_intention`

资金意图由主导外力贡献符号与价格路径共同判断：

- 正向贡献：偏买入或推动
- 负向贡献：偏卖出或压制
- 接近 0：中性或不明确

需要结合：

- `Delta_q P`
- `capital_*`
- `eps`
- 规则层置信度
- 市场整体状态

### 8.3 `theta_sign_interpretation`

为避免 `theta` 的动态解释漂移，建议输出：

```text
theta_sign_interpretation
```

默认口径（当前定义 `D_driver_t = v_q,t-1 - v_q,t-2`）：

- `theta > 0`：偏助推，强化最近一次速度变化的方向
- `theta < 0`：偏抑制或反转，抵消最近一次速度变化
- `theta ≈ 0`：该项影响较弱

最终解释必须联合 `theta * D_driver_t`：

- `theta * D_driver_t > 0`：强化当前速度变化方向
- `theta * D_driver_t < 0`：抵消当前速度变化方向

单独的 `theta` 符号不直接等同于价格上涨助推或下跌抑制。

同时记录变化率驱动信噪比：

```text
driver_snr = abs(D_driver_t) / max(1e-8, rolling_std_D_driver)
```

当 `driver_snr < 1` 时，`theta_sign_interpretation` 应降级为 `weak`，不得作为明确的助推/抑制标签。

该字段只反映局部动态解释，不直接等同于买卖意图或资金身份。

---

## 9. 输出字段

### 9.1 窗口级参数

建议输出到 `pid_window_params.csv`：

| 字段 | 含义 |
| --- | --- |
| `trade_date` | 交易日 |
| `symbol` | 股票代码 |
| `window_id` | 窗口序号 |
| `phi` | 惯性系数 |
| `theta` | 阻尼系数 |
| `beta_ch` | 游资加载系数 |
| `beta_q` / `beta_mix` | 量化或混合加载系数 |
| `beta_retail` | 散户加载系数 |
| `mode` | 运行模式 |
| `is_structural_output` | 是否结构化输出 |
| `theta_sign_interpretation` | `damping / boosting / weak` 等符号解释 |

### 9.2 窗口级贡献

建议输出到 `pid_window_contrib.csv`：

| 字段 | 含义 |
| --- | --- |
| `c_p` | 外力冲击贡献 |
| `c_i` | 惯性贡献 |
| `c_d` | 阻尼贡献 |
| `c_e` | 可选残差记忆贡献，仅残差记忆扩展启用时输出 |
| `eps` | 未解释扰动 |
| `capital_ch` | 游资外力贡献 |
| `capital_q` | 量化外力贡献 |
| `capital_retail` | 散户外力贡献 |
| `capital_mix` | 4 维混合外力贡献 |
| `closure_impl_error` | 实现级闭合误差 |
| `model_residual` | 模型残差，通常等于 `eps` |
| `residual_memory_enabled` | 是否启用残差记忆扩展 |

### 9.3 窗口级双域诊断

建议输出到 `pid_window_domain_diag.csv`：

| 字段 | 含义 |
| --- | --- |
| `delta_t_v` | 自然时间窗口成交量 |
| `delta_t_w` | 自然时间窗口成交金额 |
| `dV_dt_approx` | 近似成交速度 |
| `turnover_rate` | 资金吞吐率近似值 |
| `price_basis_error_ratio` | `P_wv_window` 与 `P_state` 的相对偏差 |
| `domain_mapping_error` | 双域差分映射误差 |
| `domain_mapping_valid_flag` | 双域映射是否通过分组误差校验 |
| `beta_norm_ch` | 游资归一化柔度 |
| `beta_norm_q` / `beta_norm_mix` | 量化或混合归一化柔度 |
| `beta_norm_retail` | 散户归一化柔度 |
| `m_eff_ch` | 游资等效质量 |
| `m_eff_q` / `m_eff_mix` | 量化或混合等效质量 |
| `m_eff_retail` | 散户等效质量 |
| `m_eff_se` | 等效质量标准误 |
| `m_eff_ci_low` / `m_eff_ci_high` | 等效质量置信区间 |
| `m_eff_uncertainty_flag` | 不确定性是否过高 |
| `m_eff_clipped_flag` | 是否触发 `beta_norm_floor` 截断 |
| `m_eff_rank_eligible` | 是否允许进入跨股排名 |
| `beta_norm_sign` | 归一化响应方向 |
| `sign_flip_flag` | 归一化响应方向是否翻转 |
| `mix_sign_conflict` | 4 维混合输入是否存在符号冲突 |
| `mix_conflict_ratio` | 4 维混合输入冲突强度 |
| `q_type` | `volume_equal / volume_quantile / window_index` |
| `u_source_type` | `score / amount / mv_ratio` 等输入口径标记 |
| `data_leakage_check` | 窗口级输入是否通过前瞻性偏差扫描 |
| `driver_snr` | `D_driver` 信噪比 |
| `stability_fallback_flag` | 是否发生稳定性回退 |
| `beta_norm_unit` | `score_response / amount_response / mv_ratio_response` |
| `m_slow_method` | 慢变分量提取方法 |
| `m_eff_uncertainty_flag` | 等效质量不确定性是否过高 |

### 9.4 日级输出

用于比赛提交：

- `pattern_reco.csv`
- `predict_result.csv`
- `pid_daily_diag.csv`

`predict_result.csv` 中的 `capital_type / capital_intention` 应优先来自结构化外力贡献。

若提交字段需要体现个股质地或稳定量，只能使用跨日稳定性诊断通过后的 `m_eff_slow` 或其分位标签，不得使用单窗口 `m_eff_*` 直接提交。

字段优先级建议：

| 优先级 | 字段范围 | 用途 |
| --- | --- | --- |
| `P0` | `trade_date`、`symbol`、`window_id`、`v_q`、`c_p`、`c_i`、`c_d`、`eps` | 核心预测和闭合 |
| `P1` | `capital_*`、`capital_type`、`capital_intention` | 结构化输出 |
| `P2` | `beta_*`、`phi`、`theta`、`mode` | 参数诊断 |
| `P3` | `m_eff_*`、`m_slow`、`param_stability_flag` | 质地画像 |
| `P4` | 双域诊断、模式切换日志、详细泄漏审计 | 离线复盘 |

比赛提交文件至少保证 `P0`；是否提交 `P1` 及以上字段由比赛接口和评分规则决定，详细诊断优先放入独立诊断文件。

---

## 10. 稳定性诊断

参数不应直接解释为长期固定属性。推荐输出跨日诊断：

- `param_mean_7d`
- `param_std_7d`
- `param_cv_7d`
- `param_sign_flip_count`
- `pattern_switch_count`
- `capital_type_switch_count`
- `capital_intention_switch_count`

对于候选等效质量，还应输出：

- `beta_norm_mean`
- `beta_norm_std`
- `beta_norm_cv`
- `m_eff_median`
- `m_eff_iqr`
- `m_eff_slow`
- `m_eff_fast_std`
- `m_eff_stable_flag`

推荐稳定性规则：

1. `beta_norm` 不接近 0，避免质量倒数爆炸
2. `beta_norm` 符号翻转次数低于阈值
3. `m_eff_iqr / m_eff_median` 低于阈值
4. `m_eff_slow` 跨日变化慢于 `m_eff_fast_std`
5. 残差占比和输入相关性诊断通过

默认阈值建议采用流动性分组后的自适应口径：

| 诊断项 | 默认建议 | 说明 |
| --- | --- | --- |
| `abs(beta_norm_mean)` | `> 1e-6` 或分组 10% 分位以上 | 避免倒数爆炸 |
| `param_cv_7d` | `< 1.0` | 高波动股票可按流动性分组放宽 |
| `param_sign_flip_count_7d` | `<= 2` | 频繁翻转时不进入稳定量 |
| `m_eff_iqr / abs(m_eff_median)` | `< 0.5` | 默认稳健离散度阈值 |
| `mix_conflict_ratio` | `< 0.3` | 超过则不做 4 维结构化分摊 |
| `rho_eps_1` | `< 0.3` | 超过时考虑残差记忆扩展 |
| `closure_impl_error` | `<= closure_numeric_tolerance` | 实现级数值一致性校验，默认按浮点精度配置 |
| `model_residual` | 通过样本外误差和残差诊断评估 | 模型级适配性，不使用固定闭合阈值替代 |

若样本较少，阈值不得硬判，应输出 `insufficient_history_flag = true` 并降级解释。

### 10.1 `data_leakage_check` 检查建议

建议至少检查以下项目：

1. 预测时是否只使用截至 `t` 或 `t-1` 的输入，不含未来窗口字段
2. 比赛提交或实时预测是否明确使用 `psi_t|t-1`、`beta_t|t-1` 等先验量，而不是使用吸收了 `y_t` 的后验 `psi_t`
3. `m_slow` 是否标记为 `realtime_filter`，若为 `offline_smooth` 则禁止进入预测或比赛提交
4. `m_slow` 的 `lookback_days` 或等价历史窗口长度是否在训练前固定，未在提交阶段按稳定性结果动态回选
5. `RTS`、全样本平滑、全样本标准化参数是否仅用于离线复盘
6. `q_type`、`u_source_type`、`mode` 是否与训练时配置一致
7. 特征工程是否使用了当日最高价、最低价、收盘后统计或其他预测截止时点之后才能知道的信息
8. 标准化、分组分位数和阈值参数是否只由训练集或滚动历史窗口拟合
9. 滑动窗口重叠是否已记录，并避免把重叠残差当作独立样本
10. `CH_rule / Q_rule / R_seed` 的规则识别过程是否也通过了同样的时间截断检查

训练/验证时间切分、标准化参数拟合和模型选择属于外部训练规范；若本文件承担训练流程管理，则另行写入日级训练记录，不作为窗口级字段。

自动化检查可按以下伪代码执行：

```text
assert max_feature_timestamp <= prediction_cutoff_timestamp
assert m_slow_method not in {kalman_smoother_offline, rts_offline, hp_offline}
assert lookback_days == config.lookback_days
assert u_forecast_method == config.u_forecast_method
assert feature_engineering_leakage_check == pass
assert normalization_fit_cutoff <= prediction_cutoff_timestamp
assert rule_layer_leakage_check == pass
assert overlapping_window_flag in {true, false}
assert data_leakage_check == pass
```

其中，时间戳、方法名、窗口长度和配置一致性属于自动化检查；代码是否确实调用先验参数、训练切分是否按时间顺序、是否存在隐藏缓存等属于人工审查和训练审计。比赛提交时自动化检查必须全部通过，人工审查记录应保留在日级诊断中。

提交前还应执行白盒方法检查：

```text
assert call_graph(m_slow_realtime).not_contains("rts_smooth")
assert call_graph(m_slow_realtime).not_contains("hp_filter_full_sample")
assert unit_test("future_data_mutation") == pass
assert unit_test("prediction_cutoff_respected") == pass
```

除静态白盒检查外，运行时应采用白名单和数据切片保护：

```text
assert runtime_smoother_method in {
    ewma_realtime,
    rolling_median_realtime,
    kalman_filter_realtime
}
assert runtime_data_view.max_timestamp <= prediction_cutoff_timestamp
assert unit_test("future_data_injection_rejected") == pass
assert unit_test("offline_method_blocked_in_submission") == pass
```

白盒检查不能仅依赖字段标记，必须绑定提交代码版本或构建哈希；动态加载或配置切换也必须经过运行时白名单校验。

若任一项失败，应写入：

```text
data_leakage_check = fail
```

并阻止比赛提交或正式结构化输出。窗口级 `data_leakage_check` 只记录输入时序；训练级和日级检查应写入 `pid_daily_diag.csv`。

`pid_daily_diag.csv` 至少包含：

```text
trade_date
symbol
data_leakage_check
feature_engineering_leakage_check
normalization_fit_cutoff
rule_layer_leakage_check
overlapping_window_flag
code_build_hash
train_valid_time_order_check
offline_smooth_used
lookback_days
m_slow_method
q_type
u_source_type
mode
param_stability_flag
rule_confidence
rule_version
rule_latency_windows
zero_trade_policy
submission_requires_complete_windows
submission_ready
```

---

## 11. 工程校验

必须通过以下检查：

1. `capital_ch / capital_q / capital_retail` 与 `beta_* U_*` 一致
2. `closure_impl_error` 不超过预先配置的 `closure_numeric_tolerance`，并单独评估 `model_residual`
3. `C_I / C_D` 不参与资金身份反解
4. `rule_base` 不输出结构化模型贡献
5. `baseline_4d` 与 `full_5d` 的字段边界清楚
6. `theta` 不在 D 驱动无效时主导解释
7. 残差、噪声占比、输入相关性有诊断记录
8. `m_eff` 只能由归一化 `beta_norm` 生成，并通过稳定性诊断后才进入画像口径
9. `F = ma` 或 PID 统一解释不得绕过闭合校验、残差诊断和字段边界
10. 4 维 `U_mix` 在符号冲突时不得拆成结构化 `capital_q / capital_retail`
11. 残差记忆扩展必须输出 `c_e`、`kappa_eps` 和启用原因
12. 所有 `m_slow` 字段必须标记 `realtime_filter` 或 `offline_smooth` 来源
13. 5 维模式启用前必须保留可辨识性检验记录
14. `closure_error` 只作为实现校验，不得单独作为模型有效性结论
15. `theta` 的联合稳定性需通过特征根或 Jury 条件检查；`abs(phi + theta) < 1` 只能作为快速筛查
16. 比赛提交前必须通过 `data_leakage_check`，确认未使用 `offline_smooth` 或未来窗口信息
17. 零成交窗口的降级优先级应预先固定，推荐 `skip > carry_forward > mark_only`，不得在运行时随结果表现临时切换
18. `mode_switch_flag` 应保留结构化记录，至少包含时间戳、前后模式、触发原因和关键诊断值
19. `beta_norm` 正式输出必须使用 `U_*_mv_ratio`，并记录 `beta_norm_unit`
20. `m_slow_method`、`lookback_days` 和 `u_forecast_method` 必须在训练前固定并写入日级诊断
21. 实时预测明确禁用 `kalman_smoother_offline`、`rts_offline` 和 `hp_offline`
22. `m_eff_clipped_flag = true` 时必须设置 `m_eff_rank_eligible = false`
23. `driver_snr < 1` 时不得输出强确定性的 `theta_sign_interpretation`
24. `P_wv_window` 仅用于诊断；实时状态和提交必须使用 `P_state`
25. `m_eff_uncertainty_flag = true` 时必须设置 `m_eff_rank_eligible = false`
26. 特征工程、标准化参数和规则层均必须通过独立的泄漏检查，并记录拟合截止时间与代码构建哈希
27. 5 维估计必须使用训练前固定的先验、`Q`、参数边界和运行预算；超预算时按固定规则回退
28. `y_t`、`y_hat_t+1|t`、`v_q,t` 和 `v_hat_q,t+1|t` 必须分字段保存，不得用观测值覆盖预测值

---

## 12. 最终口径

PID 层的职责是：

```text
规则层行为流 -> 价格闭合 -> 外力贡献 -> 状态诊断
```

不是：

```text
规则标签 -> 直接资金身份
```

也不是：

```text
C_P / C_I / C_D -> 代数反解三类资金
```

最终统一为：

```text
capital_* = beta_* U_*
```

扩展诊断链条为：

```text
Delta_t V / Delta_t W -> dV_dt_approx / turnover_rate
capital_* -> beta_norm_* -> m_eff_* -> m_eff_slow / m_eff_fast
```

`phi / theta` 只解释市场系统响应，`beta_*` 解释行为代理流对价格变化的加载强度，所有参数首先是状态变量，再经过跨日统计后才可进入个股画像或稳定量检验。

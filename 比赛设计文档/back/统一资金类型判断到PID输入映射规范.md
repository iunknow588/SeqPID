# 统一资金类型判断到PID输入映射规范

文档版本：V1.0  
文档状态：接口规范版  
前置文档：

1. `统一资金类型判断方法.md`
2. `统一资金类型判断参数配置表.md`

## 1. 文档目标

本文档用于定义：

1. 规则层输出哪些字段
2. 这些字段如何聚合到窗口级
3. 如何映射为 PID 模型输入变量
4. 哪些字段是强锚点，哪些字段只是辅助种子或混合池

目标是避免规则层与模型层之间出现口径漂移。

## 2. 总体架构关系

统一链路如下：

```text
逐笔委托/成交/撤单/盘口
    ->
规则层行为判断
    ->
原子资金行为事件
    ->
窗口级聚合
    ->
规则锚点/种子流/混合池
    ->
PID 状态空间模型
    ->
一级 PID 贡献 c_p / c_i / c_d
    ->
三类资金代理贡献 capital_ch / capital_q / capital_retail
```

## 3. 规则层输出对象

## 3.1 原子事件输出

每条可识别事件建议输出如下结构：

```python
class CapitalBehaviorEvent:
    event_time: str
    side: str                  # buy / sell
    scene: str                 # continuous / call_auction
    signed_amount: float       # 买入为正，卖出为负
    price_aggressive_score: float
    sustain_score: float
    follow_score: float
    direction_reliability: float
    capital_type_rule: str     # hot_money / quant / retail / mix_qr / unknown
    confidence_score: float
    confidence_level: str      # high / medium / low
    reason_codes: list[str]
```

## 3.2 事件层分类原则

| `capital_type_rule` | 含义 |
| --- | --- |
| `hot_money` | 高置信快速影响走势行为 |
| `quant` | 高置信缓慢改变走势行为 |
| `retail` | 高置信适应走势行为 |
| `mix_qr` | 非游资但无法高置信区分量化/散户 |
| `unknown` | 信息不足或方向不可靠 |

## 4. 窗口级聚合规范

## 4.1 基本原则

PID 模型使用窗口级输入，因此规则层输出必须先做窗口聚合。

推荐窗口长度：

- `5分钟`

与主算法设计文档保持一致。

## 4.2 聚合字段

对每个窗口 `t`，计算：

\[
buy\_ch\_anchor_t
\]

\[
sell\_ch\_anchor_t
\]

\[
buy\_q\_anchor_t
\]

\[
sell\_q\_anchor_t
\]

\[
buy\_retail\_seed_t
\]

\[
sell\_retail\_seed_t
\]

\[
mix\_qr\_signed_t
\]

其中：

1. 买入方向为正
2. 卖出方向为负
3. `mix_qr_signed_t` 保留方向符号

## 4.3 窗口级净流变量

窗口级统一定义：

\[
CH^{rule}_t = buy\_ch\_anchor_t + sell\_ch\_anchor_t
\]

\[
Q^{rule}_t = buy\_q\_anchor_t + sell\_q\_anchor_t
\]

\[
R^{seed}_t = buy\_retail\_seed_t + sell\_retail\_seed_t
\]

\[
M_{qr,t}^{rule} = mix\_qr\_signed_t
\]

解释：

1. `CH_rule` 是游资规则锚点净额
2. `Q_rule` 是量化规则锚点净额
3. `R_seed` 是散户高置信种子净额
4. `M_qr_rule` 是量化+散户未分离混合池净额

## 5. 输入变量映射规范

## 5.1 主流程映射

在主流程中，建议优先采用：

| 规则层字段 | PID 输入变量 | 说明 |
| --- | --- | --- |
| `CH_rule_t` | `U_ch,t` | 游资强锚点主输入 |
| `M_qr_rule_t` | `U_mix,t` | 量化+散户混合池主输入 |
| `Q_rule_t` | `U_q_seed,t` | 量化辅助种子输入 |
| `R_seed_t` | `U_retail_seed,t` | 散户辅助种子输入 |

对应主设计中的两类模式：

1. 规则锚定主流程：只使用 `U_ch + U_mix`
2. 扩展种子流程：使用 `U_ch + U_q_seed + U_retail_seed`

## 5.2 baseline_4d 映射

若当前模式为 `baseline_4d` 或 `fallback_4d`，推荐映射：

\[
U_{ch,t} = CH^{rule}_t
\]

\[
U_{mix,t} = M_{qr,t}^{rule} + Q^{rule}_t + R^{seed}_t
\]

说明：

1. `Q_rule` 与 `R_seed` 不单独进入状态向量
2. 但可并入 `U_mix`
3. 同时保留为辅助诊断字段

## 5.3 enhanced_5d 映射

若当前模式为 `full_5d` 或 `diag_5d`，推荐映射：

\[
U_{ch,t} = CH^{rule}_t
\]

\[
U_{q,t}^{seed} = Q^{rule}_t
\]

\[
U_{retail,t}^{seed} = R^{seed}_t
\]

\[
U_{mix,t} = M_{qr,t}^{rule}
\]

说明：

1. `U_q_seed` 与 `U_retail_seed` 用于 5 维扩展观测方程
2. `U_mix` 仍保留，作为规则层剩余流量解释
3. 若种子流质量不足，不得强启 5 维主模型

## 6. 锚点优先级规范

## 6.1 游资锚点优先级最高

当事件被高置信识别为“快速影响走势”时：

1. 优先进入 `CH_rule`
2. 不再进入 `M_qr`
3. 不再重复进入量化或散户种子流

即：

> 游资强锚点是互斥分类。

## 6.2 量化与散户高置信事件优先进入种子流

若事件未被判为游资，但高置信属于：

1. 缓慢改变走势 -> 进入 `Q_rule`
2. 适应走势 -> 进入 `R_seed`

此时也不应重复进入 `M_qr`。

## 6.3 冲突或低置信事件进入混合池

若存在以下任一情况：

1. 量化/散户规则冲突
2. 主动方向恢复不可靠
3. 证据不足
4. 置信度低于门槛

则：

1. 不进入 `CH_rule / Q_rule / R_seed`
2. 进入 `M_qr_rule`

## 7. 聚合前预处理规范

在进入 PID 前，对窗口级输入做以下处理：

1. `1%` 缩尾
2. 缺失补零
3. 有符号净额保留
4. EWMA 自适应标准化

建议顺序：

```text
窗口内事件求和
    ->
形成 CH_rule / Q_rule / R_seed / M_qr_rule
    ->
缩尾
    ->
补零
    ->
EWMA 标准化
    ->
进入 PID
```

## 8. 与资金类型最终输出的关系

规则层字段不是最终比赛输出字段，不能直接等价替换：

- `capital_ch`
- `capital_q`
- `capital_retail`

两者关系如下：

| 层级 | 字段 | 含义 |
| --- | --- | --- |
| 规则层 | `CH_rule / Q_rule / R_seed / M_qr_rule` | 行为锚点、种子流、混合池 |
| 模型层 | `c_p / c_i / c_d / eps` | 一级 PID 作用贡献 |
| 模型层 | `capital_ch / capital_q / capital_retail` | 结构反解后的资金代理贡献 |

因此：

1. 规则层负责给模型提供先验方向和高置信样本
2. 模型层负责闭合价格变化并输出最终结构贡献

## 9. 一致性校验字段

建议为每个窗口保留以下校验量：

| 字段 | 含义 |
| --- | --- |
| `ch_anchor_rule` | 规则层游资净锚点 |
| `mix_qr_rule` | 规则层混合池净额 |
| `q_seed_rule` | 规则层量化净种子 |
| `retail_seed_rule` | 规则层散户净种子 |
| `capital_ch_model` | 模型层游资结构贡献 |
| `capital_q_model` | 模型层量化结构贡献 |
| `capital_retail_model` | 模型层散户结构贡献 |
| `capital_anchor_error` | 规则锚点与模型反解误差 |

## 9.1 游资一致性校验

主设计已定义：

\[
err_{ch,t} =
\frac{|CH_t^{anchor} - CH_t^{pid}|}
{\max(|CH_t^{anchor}|, |CH_t^{pid}|, \delta)}
\]

本规范中：

\[
CH_t^{anchor} = CH_t^{rule}
\]

即规则层的游资锚点净额直接作为校验锚点。

## 9.2 量化/散户一致性校验

由于 `Q_rule` 与 `R_seed` 只是种子流，不应强制等于模型结构贡献，但可用于：

1. 方向一致性
2. 主导窗口一致性
3. 日终主导一致性

若长期方向冲突，则说明规则口径或模型口径需要回看。

## 10. 输出对象建议

建议窗口级标准接口如下：

```python
class WindowCapitalRuleFeature:
    window_id: int
    buy_ch_anchor: float
    sell_ch_anchor: float
    buy_q_anchor: float
    sell_q_anchor: float
    buy_retail_seed: float
    sell_retail_seed: float
    mix_qr_signed: float
    direction_reliability: float
    confidence_score_mean: float
    confidence_level: str
    fallback_reason: str | None
```

进一步形成 PID 输入对象：

```python
class WindowPidInputFeature:
    window_id: int
    u_ch: float
    u_mix: float
    u_q_seed: float
    u_retail_seed: float
    ch_anchor_rule: float
    mix_qr_rule: float
```

## 11. 模式切换映射规则

## 11.1 `rule_base`

使用场景：

1. schema 不稳定
2. 方向恢复较差
3. 无法进入状态空间模型

映射规则：

1. 只输出规则锚点和种子流
2. 不输出结构贡献
3. 不强行映射到 `capital_ch/q/retail`

## 11.2 `baseline_4d`

映射规则：

1. `U_ch = CH_rule`
2. `U_mix = M_qr_rule + Q_rule + R_seed`
3. `Q_rule / R_seed` 只做辅助校验

## 11.3 `diag_5d`

映射规则：

1. `U_ch = CH_rule`
2. `U_q_seed = Q_rule`
3. `U_retail_seed = R_seed`
4. `U_mix = M_qr_rule`
5. `theta` 只用于诊断，不用于强拆分

## 11.4 `full_5d`

映射规则：

1. `U_ch = CH_rule`
2. `U_q_seed = Q_rule`
3. `U_retail_seed = R_seed`
4. `U_mix = M_qr_rule`
5. `theta + D_driver` 参与结构拆分

## 12. 不允许的口径漂移

以下行为在工程实现中明确禁止：

1. 将规则层的 `Q_rule` 直接当成最终 `capital_q`
2. 将规则层的 `R_seed` 直接当成最终 `capital_retail`
3. 将卖出方向写成正数后在模型层再修正
4. 同一事件重复进入多个互斥资金池
5. 因为某日拟合更好而临时改变字段语义

## 13. 最终结论

规则层与 PID 层的统一关系可总结为：

1. 快速影响走势的事件 -> 游资锚点
2. 缓慢改变走势的事件 -> 量化种子/锚点
3. 适应走势的事件 -> 散户种子
4. 规则上无法强分的剩余 -> 量化+散户混合池
5. 最终资金贡献解释 -> 交由 PID 状态模型与联盟方程闭合

也就是说：

> 规则负责识别行为起点，PID 负责完成结构解释终局。

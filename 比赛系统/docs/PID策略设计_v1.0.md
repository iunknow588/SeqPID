# PID参数识别与资金贡献度拆解策略设计 v1.0

**文档状态**: ✅ 定稿（待编码实施）  
**适用范围**: 100只股票日终批量处理  
**生效日期**: 2026-07-08  
**上游依赖**: 算法设计.md, 比赛详细设计说明书.md

---

## 1. 核心设计决策

### 1.1 方案选择
- ✅ **纯PID方案**：不保留原统计特征打分逻辑，所有pattern/capital预测均基于PID贡献度拆解结果
- ✅ **100股范围**：性能压力小，可启用完整KF+RTS平滑，无需JIT/并行优化
- ✅ **规则映射**：Task输出采用可解释规则映射，暂不引入轻量模型

### 1.2 关键参数（100股适用）

| 参数 | 取值 | 说明 |
|------|------|------|
| 资金分类-游资阈值 | ≥50万元 & <500ms | 单笔主动成交金额+挂单存活时间 |
| 资金分类-量化阈值 | <10万元 & >3s | 被动挂单/撤单/小额成交 |
| 资金分类-散户 | 其余订单 | fallback规则 |
| 窗口粒度 | 5分钟 | 全天48个窗口 |
| KF状态维度 | 5维 | [φ, β_ch, β_q, β_retail, θ] |
| KF过程噪声Q | diag([1e-3, 1e-2, 1e-2, 1e-2, 5e-3]) | 参数随机游走强度 |
| 观测噪声r_base | 1e-4 | 基础观测方差 |
| 贡献度闭合容差 | <1e-6 | 数值验证阈值 |

---

## 2. 模块接口定义

### 2.1 PIDDecomposer 类

`python
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class DecompositionResult:
    """单股单日PID分解结果"""
    stock_code: str
    transaction_date: str
    
    # PID参数序列 (T=48)
    inertia: np.ndarray          # φ_t: 惯性系数
    beta_ch: np.ndarray          # 游资冲击系数
    beta_q: np.ndarray           # 量化冲击系数  
    beta_retail: np.ndarray      # 散户冲击系数
    damping: np.ndarray          # θ_t: 阻尼系数
    
    # 贡献度序列
    delta_ch: np.ndarray         # 游资贡献度
    delta_q: np.ndarray          # 量化贡献度
    delta_retail: np.ndarray     # 散户贡献度
    
    # 聚合指标
    inertia_mean: float          # 日均惯性
    damping_mean: float          # 日均阻尼
    hot_money_ratio: float       # 游资主导窗口占比
    quant_ratio: float           # 量化主导窗口占比
    retail_ratio: float          # 散户主导窗口占比
    dominant_type: str           # 日终主导资金类型
    closure_error: float         # 贡献度闭合误差
    
    # 诊断信息
    kf_converged: bool           # KF是否收敛
    warnings: list[str]          # 运行警告


class PIDDecomposer:
    """PID参数识别与贡献度拆解核心模块"""
    
    def __init__(self, config: dict):
        """
        初始化分解器
        config需包含:
          - species_rules: 资金分类规则
          - kf_params: Q矩阵, r_base, 初始化策略
          - mapping_rules: pattern/intention映射阈值
        """
        pass
    
    def decompose_day(self, level2_window: Level2Window) -> DecompositionResult:
        """
        执行单股单日完整分解流程
        
        Args:
            level2_window: 包含48个5分钟窗口的Level2数据聚合对象
            
        Returns:
            DecompositionResult: 分解结果，含参数序列+贡献度+主导判定
        """
        pass
    
    def _classify_capital_species(self, trades: list[Trade]) -> dict[str, list[Trade]]:
        """资金物种分类：游资/量化/散户"""
        pass
    
    def _compute_U_series(self, classified_trades: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算三类资金净流量序列 U_ch, U_q, U_retail"""
        pass
    
    def _kalman_filter_forward(self, delta_P: np.ndarray, U: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """正向KF递推: 返回滤波状态序列 + 残差序列"""
        pass
    
    def _rts_backward_smooth(self, filtered_states: np.ndarray, filtered_covs: np.ndarray) -> np.ndarray:
        """RTS反向平滑: 返回平滑后状态序列"""
        pass
    
    def _decompose_contributions(self, states: np.ndarray, U: np.ndarray, eps: np.ndarray) -> dict[str, np.ndarray]:
        """贡献度拆解: 返回Δ_ch, Δ_q, Δ_retail"""
        pass
    
    def _verify_closure(self, delta_total: np.ndarray, delta_P: np.ndarray) -> float:
        """闭合性验证: 返回最大绝对误差"""
        pass
    
    def _determine_dominant(self, deltas: dict[str, np.ndarray], states: np.ndarray) -> dict:
        """主导力量判定: 窗口级+日终级"""
        pass
`

### 2.2 与现有模块的集成点

`python
# capital_model.py 新增参数
def predict_capitals(
    sample: DailySample, 
    config: dict, 
    label_dict: dict,
    pid_result: DecompositionResult  # ✅ 必传，无降级
) -> list[PredictResult]:
    """
    基于PID贡献度预测资金类型与意图
    """
    # 主导类型直接取自pid_result.dominant_type
    # 意图映射: _map_contribution_to_intention(pid_result, sample.feature_summary)
    pass

# pattern_model.py 新增参数  
def predict_pattern(
    sample: DailySample,
    config: dict,
    label_dict: dict,
    pid_result: DecompositionResult  # ✅ 必传，无降级
) -> PatternResult:
    """
    基于PID参数映射交易模式
    """
    # 规则映射: _map_pid_to_pattern(pid_result, config["mapping_rules"]["pattern"])
    pass
`

---

## 3. 资金分类规则实现

### 3.1 分类逻辑（单笔订单级）

`python
def classify_trade(trade: Trade, config: dict) -> str:
    """
    单笔交易分类规则
    """
    amount = trade.amount  # 成交金额(元)
    lifetime_ms = trade.order_lifetime_ms  # 挂单存活时间(ms)
    is_active = trade.is_active_order  # 是否主动成交
    
    rules = config["species_rules"]
    
    # 游资: 大单 + 快速吃单
    if (amount >= rules["hot_money"]["min_amount"] and 
        lifetime_ms < rules["hot_money"]["max_lifetime_ms"] and
        is_active):
        return "hot_money"
    
    # 量化: 小单 + 长存活 + 被动
    if (amount < rules["quant"]["max_amount"] and
        lifetime_ms > rules["quant"]["min_lifetime_ms"] and
        not is_active):  # 被动挂单/成交
        return "quant"
    
    # 散户: fallback
    return "retail"
`

### 3.2 窗口聚合公式

对每个5分钟窗口t：
`
U_ch,t    = Σ(主动买入_i - 主动卖出_i) for i ∈ 游资订单_t
U_q,t     = Σ(主动买入_i - 主动卖出_i) for i ∈ 量化订单_t  
U_retail,t = Σ(主动买入_i - 主动卖出_i) for i ∈ 散户订单_t

# 标准化处理（进入KF前）
U_norm = (U - EWMA_mean) / (EWMA_std + 1e-8)  # 自适应标准化
U_clipped = np.clip(U_norm, -3, 3)  # 1%缩尾等效
`

---

## 4. KF+RTS 实现细节

### 4.1 状态空间方程

**观测方程**（t时刻）:
`
ΔP_t = [ΔP_{t-1}, U_ch_{t-1}, U_q_{t-1}, U_retail_{t-1}, ε̂_{t-1}] @ ψ_t + ε_t
ε_t ~ N(0, r_t^eff)
r_t^eff = r_base × (σ_hist / σ_EWMA,t)²  # 自适应观测噪声
`

**状态转移方程**:
`
ψ_t = I₅ × ψ_{t-1} + η_t
η_t ~ N(0, Q_opt)  # Q_opt为对角阵，见1.2节
`

### 4.2 初始化策略

`python
def _initialize_states(self, delta_P: np.ndarray, U: np.ndarray, window: int = 5):
    """
    用前window个窗口OLS估计初始化状态
    """
    # 构造设计矩阵 X = [ΔP_lag, U_ch_lag, U_q_lag, U_retail_lag, eps_lag]
    # OLS: ψ_ols = (X'X)⁻¹X'y
    # P_0 = 10 × I₅ (高不确定性初始化)
    pass
`

### 4.3 收敛性判定

`python
def _check_convergence(self, filtered_states: np.ndarray, tol: float = 1e-4) -> bool:
    """
    判定KF是否收敛: 最后10个窗口状态变化 < tol
    """
    recent_diff = np.abs(np.diff(filtered_states[-10:], axis=0)).max()
    return recent_diff < tol
`

---

## 5. Task映射规则（Δ贡献度 → 比赛输出）

### 5.1 Pattern映射规则

`python
def _map_pid_to_pattern(pid: DecompositionResult, rules: dict) -> tuple[str, float]:
    """
    基于PID参数映射交易模式标签
    返回: (pattern_type, confidence_score)
    """
    scores = {}
    
    # TREND_LIFT: 游资主导 + 强惯性
    if (pid.hot_money_ratio > rules["TREND_LIFT"]["hot_money_ratio_min"] and
        pid.inertia_mean > rules["TREND_LIFT"]["inertia_min"]):
        scores["TREND_LIFT"] = 0.5 * pid.hot_money_ratio + 0.5 * _normalize(pid.inertia_mean, 0, 1)
    
    # QUANT_MM: 量化主导 + 强阻尼  
    if (pid.quant_ratio > rules["QUANT_MM"]["quant_ratio_min"] and
        pid.damping_mean < rules["QUANT_MM"]["damping_max"]):
        scores["QUANT_MM"] = 0.6 * pid.quant_ratio + 0.4 * _normalize(-pid.damping_mean, 0, 1)
    
    # WASH_TRADE: 散户主导 + 高噪声
    noise_ratio = pid.closure_error / (np.abs(pid.delta_ch).mean() + 1e-8)
    if (pid.retail_ratio > rules["WASH_TRADE"]["retail_ratio_min"] and
        noise_ratio > rules["WASH_TRADE"]["noise_ratio_min"]):
        scores["WASH_TRADE"] = 0.7 * pid.retail_ratio + 0.3 * _normalize(noise_ratio, 0, 1)
    
    # 默认: INTRADAY_ARB
    if not scores:
        return "INTRADAY_ARB", 0.5
    
    # 选最高分
    pattern, score = max(scores.items(), key=lambda x: x[1])
    return pattern, min(score + 0.3, 0.95)  # 基础置信度+映射置信度
`

### 5.2 Capital Intention映射规则

`python
def _map_contribution_to_intention(
    pid: DecompositionResult, 
    summary: dict,
    rules: dict
) -> tuple[str, float]:
    """
    基于贡献度符号+盘口位置映射资金意图
    """
    dominant = pid.dominant_type
    vwap_pct = summary.get("close_strength", 0.5)  # 收盘价在日内区间的位置
    
    if dominant == "hot_money":
        # 游资意图判定
        if pid.delta_ch[-1] > 0 and vwap_pct < 0.8:  # 贡献为正 + 未到高位
            return "LIFT", 0.75  # 拉升
        elif pid.delta_ch[-1] < 0 and vwap_pct > 0.2:  # 贡献为负 + 不在低位
            return "DISTRIBUTE", 0.72  # 出货
        elif abs(pid.delta_ch[-1]) < 1e-4:
            return "PROBE", 0.65  # 试盘
        else:
            return "ABSORB", 0.68  # 吸筹
    
    elif dominant == "quant":
        # 量化意图判定  
        if abs(summary.get("close_return", 0)) < 0.01:
            return "T0交易", 0.70
        elif pid.delta_q[-1] > 0:
            return "买入", 0.62
        else:
            return "卖出", 0.62
    
    else:  # retail
        if abs(summary.get("close_return", 0)) < 0.008:
            return "中性", 0.58
        elif summary.get("close_return", 0) > 0:
            return "买入", 0.60
        else:
            return "卖出", 0.60
`

---

## 6. 验收标准与测试用例

### 6.1 单元测试用例

`python
# tests/unit/test_pid_decomposer.py

def test_closure_property():
    """验证贡献度闭合性: Δ_ch + Δ_q + Δ_retail == ΔP"""
    result = decomposer.decompose_day(test_window)
    assert result.closure_error < 1e-6

def test_kf_convergence():
    """验证KF在24窗口内收敛"""
    result = decomposer.decompose_day(test_window)
    assert result.kf_converged == True

def test_dominant_consistency():
    """验证主导类型与贡献度占比一致"""
    result = decomposer.decompose_day(test_window)
    expected = max(
        [("hot_money", result.hot_money_ratio), 
         ("quant", result.quant_ratio), 
         ("retail", result.retail_ratio)],
        key=lambda x: x[1]
    )[0]
    assert result.dominant_type == expected
`

### 6.2 集成测试用例

`python
# tests/integration/test_100stocks.py

def test_batch_decomposition_100stocks():
    """100股批量分解性能与正确性"""
    # 性能: <30秒完成100股
    start = time.time()
    results = [decomposer.decompose_day(w) for w in test_windows_100]
    elapsed = time.time() - start
    assert elapsed < 30.0
    
    # 正确性: 所有结果闭合误差达标
    errors = [r.closure_error for r in results]
    assert max(errors) < 1e-6
    assert sum(1 for e in errors if e > 1e-7) <= 5  # 允许少量数值误差
`

### 6.3 策略验证指标（100股抽样）

| 指标 | 目标值 | 验证方法 |
|------|--------|---------|
| 主导判定准确率 | >65% | 对比次日实际走势方向 |
| pattern映射一致性 | >80% | 与人工标注10只典型股票对比 |
| intention置信度均值 | >0.65 | 统计输出confidence分布 |
| 闭合误差P99 | <5e-7 | 100股误差分布99分位 |

---

## 7. 配置示例 (configs/pid_config.yaml)

`yaml
species_rules:
  hot_money:
    min_amount: 500000
    max_lifetime_ms: 500
    require_active: true
  quant:
    max_amount: 100000
    min_lifetime_ms: 3000
    prefer_passive: true
  retail:
    fallback: true

kf_params:
  process_noise_diag: [0.001, 0.01, 0.01, 0.01, 0.005]
  observation_noise_base: 1.0e-4
  init_ols_window: 5
  init_cov_scale: 10.0
  convergence_tol: 1.0e-4
  convergence_window: 10

mapping_rules:
  pattern:
    TREND_LIFT:
      hot_money_ratio_min: 0.6
      inertia_min: 0.3
    QUANT_MM:
      quant_ratio_min: 0.5
      damping_max: -0.2
    WASH_TRADE:
      retail_ratio_min: 0.5
      noise_ratio_min: 0.4
  intention:
    vwap_percentile_low: 0.2
    vwap_percentile_high: 0.8
    small_return_threshold: 0.008

validation:
  closure_error_threshold: 1.0e-6
  dominant_accuracy_target: 0.65
  pattern_consistency_target: 0.80
`

---

## 8. 实施Checklist

- [ ] 创建 src/pid_decomposer.py 实现核心类
- [ ] 创建 configs/pid_config.yaml 配置文件
- [ ] 修改 src/capital_model.py 移除降级逻辑，适配pid_result参数
- [ ] 修改 src/pattern_model.py 移除降级逻辑，适配pid_result参数  
- [ ] 修改 src/scheduler.py 集成PID分解调用链路
- [ ] 编写 	ests/unit/test_pid_decomposer.py 单元测试
- [ ] 编写 	ests/integration/test_100stocks.py 集成测试
- [ ] 运行100股验证，输出 eports/pid_validation_100stocks.md
- [ ] 更新 README.md 说明PID方案使用说明

---

> 📌 **备注**: 本文档为编码实施的唯一依据。如有调整需先更新本文档并评审。

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    from schemas import DailySample
except Exception:  # pragma: no cover
    DailySample = Any


logger = logging.getLogger(__name__)


@dataclass
class DecompositionResult:
    stock_code: str
    transaction_date: str
    phi: np.ndarray = field(default_factory=lambda: np.zeros(48))
    theta: np.ndarray = field(default_factory=lambda: np.zeros(48))
    inertia: np.ndarray = field(default_factory=lambda: np.zeros(48))
    beta_ch: np.ndarray = field(default_factory=lambda: np.zeros(48))
    beta_q: np.ndarray = field(default_factory=lambda: np.zeros(48))
    beta_retail: np.ndarray = field(default_factory=lambda: np.zeros(48))
    beta_mix: np.ndarray = field(default_factory=lambda: np.zeros(48))
    damping: np.ndarray = field(default_factory=lambda: np.zeros(48))
    c_p: np.ndarray = field(default_factory=lambda: np.zeros(48))
    c_i: np.ndarray = field(default_factory=lambda: np.zeros(48))
    c_d: np.ndarray = field(default_factory=lambda: np.zeros(48))
    eps: np.ndarray = field(default_factory=lambda: np.zeros(48))
    capital_ch: np.ndarray = field(default_factory=lambda: np.zeros(48))
    capital_mix: np.ndarray = field(default_factory=lambda: np.zeros(48))
    capital_q: np.ndarray = field(default_factory=lambda: np.zeros(48))
    capital_retail: np.ndarray = field(default_factory=lambda: np.zeros(48))
    price_basis: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_ch_amount_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_q_amount_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_retail_amount_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_mix_amount_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_ch_mv_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_q_mv_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_retail_mv_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    u_mix_mv_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    capital_anchor_error: np.ndarray = field(default_factory=lambda: np.full(48, np.nan))
    delta_ch: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_q: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_retail: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_ch_alloc: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_q_alloc: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_retail_alloc: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_ch_display: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_q_display: np.ndarray = field(default_factory=lambda: np.zeros(48))
    delta_retail_display: np.ndarray = field(default_factory=lambda: np.zeros(48))
    noise_ratio: np.ndarray = field(default_factory=lambda: np.ones(48))
    explain_ratio: np.ndarray = field(default_factory=lambda: np.zeros(48))
    inertia_mean: float = 0.0
    damping_mean: float = 0.0
    hot_money_ratio: float = 0.0
    quant_ratio: float = 0.0
    retail_ratio: float = 0.0
    dominant_type: str = "unknown"
    dominant_intention: str = "中性"
    closure_error: float = 0.0
    pid_closure_error: float = 0.0
    alloc_closure_error: float = 0.0
    display_closure_error: float = 0.0
    capital_cp_identity_error: float = 0.0
    capital_ci_identity_error: float = 0.0
    capital_cd_identity_error: float = 0.0
    capital_identity_error: float = 0.0
    dominant_source: str = "capital_external_force"
    display_fields_used_for_dominant: bool = False
    kf_converged: bool = False
    mode: str = "baseline_4d"
    u_basis_effective: str = "amount"
    mv_ratio_input_requested: bool = False
    mv_ratio_input_applied: bool = False
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not np.any(self.phi) and np.any(self.inertia):
            self.phi = self.inertia.copy()
        if not np.any(self.inertia) and np.any(self.phi):
            self.inertia = self.phi.copy()
        if not np.any(self.theta) and np.any(self.damping):
            self.theta = self.damping.copy()
        if not np.any(self.damping) and np.any(self.theta):
            self.damping = self.theta.copy()
        if self.display_closure_error == 0.0 and self.closure_error != 0.0:
            self.display_closure_error = self.closure_error


class BasePIDDecomposer:
    MODE_NAME = "baseline_4d"
    STATE_DIM = 4

    def __init__(self, config: dict, mode_name: str | None = None):
        self.config = config
        self.pid_config = config.get("pid_decomposer", {})
        self.species_rules = config.get("species_rules", {})
        self.kf_params = config.get("kf_params", {})
        self.mode_name = mode_name or self.MODE_NAME
        q_default = [0.001, 0.01, 0.01, 0.01, 0.005]
        q_diag = list(
            self.kf_params.get("process_noise_diag_anchor", self.kf_params.get("process_noise_diag", q_default))
        )
        q_diag = self._build_q_diag(q_diag)
        self.Q = np.diag(np.asarray(q_diag[: self.STATE_DIM], dtype=float))
        self.r_base = float(self.kf_params.get("observation_noise_base", 1e-4))
        self.init_cov_scale = float(self.kf_params.get("init_cov_scale", 10.0))
        self.convergence_tol = float(self.kf_params.get("convergence_tol", 1e-4))
        self.convergence_window = int(self.kf_params.get("convergence_window", 10))
        self.kappa_i = float(self.pid_config.get("kappa_i", config.get("kappa_i", 0.5)))
        self.anchor_error_max = float(self.pid_config.get("capital_anchor_error_max", 0.4))
        self.eps = 1e-8
        self.clip_limit = 3.0

    def _build_q_diag(self, q_diag: list[float]) -> list[float]:
        while len(q_diag) < self.STATE_DIM:
            q_diag.append(q_diag[-1] if q_diag else 0.01)
        return q_diag

    def _lagged_delta(self, t: int, delta_p: np.ndarray) -> float:
        return float(delta_p[t - 1]) if t > 0 else 0.0

    def _driver_signal(self, t: int, delta_p: np.ndarray) -> float:
        """Current default keeps the D-term tied to the second difference.

        Future lower-order variants can override this method without changing
        the surrounding decomposition loop.
        """
        return float(delta_p[t - 1] - delta_p[t - 2]) if t > 1 else 0.0

    def decompose_sample(self, sample: DailySample) -> DecompositionResult:
        features = self._extract_from_daily_sample(sample)
        return self._decompose_arrays(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            **features,
        )

    def decompose_day(self, level2_window) -> DecompositionResult:
        if hasattr(level2_window, "feature_summary"):
            return self.decompose_sample(level2_window)
        features = self._extract_from_level2_window(level2_window)
        return self._decompose_arrays(
            stock_code=getattr(level2_window, "stock_code", "UNKNOWN"),
            transaction_date=getattr(level2_window, "transaction_date", ""),
            **features,
        )

    def _decompose_arrays(
        self,
        stock_code: str,
        transaction_date: str,
        delta_p: np.ndarray,
        u_ch: np.ndarray,
        u_mix: np.ndarray,
        ch_anchor: np.ndarray,
        mix_qr: np.ndarray,
        u_q: np.ndarray | None = None,
        u_retail: np.ndarray | None = None,
        price_basis: np.ndarray | None = None,
        u_ch_amount_ratio: np.ndarray | None = None,
        u_q_amount_ratio: np.ndarray | None = None,
        u_retail_amount_ratio: np.ndarray | None = None,
        u_mix_amount_ratio: np.ndarray | None = None,
        u_ch_mv_ratio: np.ndarray | None = None,
        u_q_mv_ratio: np.ndarray | None = None,
        u_retail_mv_ratio: np.ndarray | None = None,
        u_mix_mv_ratio: np.ndarray | None = None,
        u_basis_effective: str = "amount",
        mv_ratio_input_requested: bool = False,
        mv_ratio_input_applied: bool = False,
    ) -> DecompositionResult:
        t_len = len(delta_p)
        u_ch_norm = self._adaptive_normalize(u_ch)
        u_mix_norm = self._adaptive_normalize(u_mix)
        u_q_norm = self._adaptive_normalize(np.zeros(t_len) if u_q is None else u_q)
        u_retail_norm = self._adaptive_normalize(np.zeros(t_len) if u_retail is None else u_retail)
        psi_filtered, cov_filtered = self._run_kalman_filter(delta_p, u_ch_norm, u_mix_norm, u_q_norm, u_retail_norm)
        psi = self._rts_backward_smooth(psi_filtered, cov_filtered)

        phi, beta_ch, beta_mix, beta_q, beta_retail, theta = self._extract_components(psi, t_len)
        c_p = np.zeros(t_len)
        c_i = np.zeros(t_len)
        c_d = np.zeros(t_len)
        eps_smooth = np.zeros(t_len)
        capital_ch = np.zeros(t_len)
        capital_mix = np.zeros(t_len)
        capital_q = np.zeros(t_len)
        capital_retail = np.zeros(t_len)
        anchor_error = np.full(t_len, np.nan)
        delta_ch_alloc = np.zeros(t_len)
        delta_q_alloc = np.zeros(t_len)
        delta_retail_alloc = np.zeros(t_len)
        w_ch_series = np.zeros(t_len)
        w_q_series = np.zeros(t_len)
        w_retail_series = np.zeros(t_len)

        for t in range(t_len):
            delta_prev = self._lagged_delta(t, delta_p)
            eps_prev = eps_smooth[t - 1] if t > 0 else 0.0
            d_driver = self._driver_signal(t, delta_p)
            u_ch_prev = u_ch_norm[t - 1] if t > 0 else 0.0
            u_mix_prev = u_mix_norm[t - 1] if t > 0 else 0.0
            u_q_prev = u_q_norm[t - 1] if t > 0 else 0.0
            u_retail_prev = u_retail_norm[t - 1] if t > 0 else 0.0

            c_p[t], capital_mix[t], capital_q[t], capital_retail[t] = self._compute_external_terms(
                t=t,
                beta_ch=beta_ch,
                beta_mix=beta_mix,
                beta_q=beta_q,
                beta_retail=beta_retail,
                u_ch_prev=u_ch_prev,
                u_mix_prev=u_mix_prev,
                u_q_prev=u_q_prev,
                u_retail_prev=u_retail_prev,
            )
            c_i[t] = phi[t] * delta_prev + self.kappa_i * eps_prev
            c_d[t] = theta[t] * d_driver
            eps_smooth[t] = delta_p[t] - c_p[t] - c_i[t] - c_d[t]
            capital_ch[t] = beta_ch[t] * u_ch_prev

            if np.isfinite(ch_anchor[t]) and np.isfinite(mix_qr[t]):
                rule_total = abs(ch_anchor[t]) + abs(mix_qr[t])
                model_total = abs(capital_ch[t]) + abs(capital_mix[t])
                if rule_total > self.eps and model_total > self.eps:
                    rule_share = abs(ch_anchor[t]) / rule_total
                    model_share = abs(capital_ch[t]) / model_total
                    anchor_error[t] = abs(rule_share - model_share)

            flow_abs_sum = abs(u_ch_prev) + abs(u_q_prev) + abs(u_retail_prev)
            if flow_abs_sum > self.eps:
                w_ch = abs(u_ch_prev) / flow_abs_sum
                w_q = abs(u_q_prev) / flow_abs_sum
                w_retail = abs(u_retail_prev) / flow_abs_sum
            else:
                external_abs_sum = abs(capital_ch[t]) + abs(capital_mix[t])
                if external_abs_sum > self.eps:
                    w_ch = abs(capital_ch[t]) / external_abs_sum
                    if self.mode_name == "baseline_4d":
                        mix_weight = abs(capital_mix[t]) / external_abs_sum
                        qr_abs = abs(u_q_prev) + abs(u_retail_prev)
                        if qr_abs > self.eps:
                            w_q = mix_weight * abs(u_q_prev) / qr_abs
                            w_retail = mix_weight * abs(u_retail_prev) / qr_abs
                        else:
                            w_q = mix_weight
                            w_retail = 0.0
                    else:
                        w_q = abs(capital_q[t]) / external_abs_sum
                        w_retail = abs(capital_retail[t]) / external_abs_sum
                else:
                    w_ch = w_q = w_retail = 1.0 / 3.0
            w_ch_series[t] = w_ch
            w_q_series[t] = w_q
            w_retail_series[t] = w_retail
            delta_ch_alloc[t] = beta_ch[t] * u_ch_prev + c_i[t] * w_ch + c_d[t] * min(w_ch, 0.1)
            delta_q_alloc[t] = beta_q[t] * u_q_prev + c_d[t] * w_q + c_i[t] * min(w_q, 0.1)
            delta_retail_alloc[t] = c_p[t] + c_i[t] + c_d[t] - delta_ch_alloc[t] - delta_q_alloc[t]

        delta_ch_display = delta_ch_alloc + eps_smooth * w_ch_series
        delta_q_display = delta_q_alloc + eps_smooth * w_q_series
        delta_retail_display = delta_retail_alloc + eps_smooth * w_retail_series
        total_pid = c_p + c_i + c_d + eps_smooth
        pid_closure_error = self._max_abs(total_pid - delta_p)
        total_alloc = delta_ch_alloc + delta_q_alloc + delta_retail_alloc + eps_smooth
        alloc_closure_error = self._max_abs(total_alloc - delta_p)
        total_display = delta_ch_display + delta_q_display + delta_retail_display
        closure_error = self._max_abs(total_display - delta_p)
        formal_capital_total = capital_ch + (capital_mix if self.mode_name == "baseline_4d" else capital_q + capital_retail)
        capital_cp_identity_error = self._max_abs(formal_capital_total - c_p)
        noise_ratio = np.abs(eps_smooth) / np.maximum(np.abs(delta_p), self.eps)
        explain_ratio = 1.0 - np.minimum(noise_ratio, 1.0)
        dominant_info = self._determine_dominant(capital_ch, capital_q, capital_retail)
        kf_converged = self._check_convergence(psi_filtered)

        result = DecompositionResult(
            stock_code=stock_code,
            transaction_date=transaction_date,
            phi=phi,
            theta=theta,
            inertia=phi,
            beta_ch=beta_ch,
            beta_q=beta_q,
            beta_retail=beta_retail,
            beta_mix=beta_mix,
            damping=theta,
            c_p=c_p,
            c_i=c_i,
            c_d=c_d,
            eps=eps_smooth,
            capital_ch=capital_ch,
            capital_mix=capital_mix,
            capital_q=capital_q,
            capital_retail=capital_retail,
            price_basis=np.asarray(np.zeros(t_len) if price_basis is None else price_basis, dtype=float),
            u_ch_amount_ratio=np.asarray(np.zeros(t_len) if u_ch_amount_ratio is None else u_ch_amount_ratio, dtype=float),
            u_q_amount_ratio=np.asarray(np.zeros(t_len) if u_q_amount_ratio is None else u_q_amount_ratio, dtype=float),
            u_retail_amount_ratio=np.asarray(np.zeros(t_len) if u_retail_amount_ratio is None else u_retail_amount_ratio, dtype=float),
            u_mix_amount_ratio=np.asarray(np.zeros(t_len) if u_mix_amount_ratio is None else u_mix_amount_ratio, dtype=float),
            u_ch_mv_ratio=np.asarray(np.zeros(t_len) if u_ch_mv_ratio is None else u_ch_mv_ratio, dtype=float),
            u_q_mv_ratio=np.asarray(np.zeros(t_len) if u_q_mv_ratio is None else u_q_mv_ratio, dtype=float),
            u_retail_mv_ratio=np.asarray(np.zeros(t_len) if u_retail_mv_ratio is None else u_retail_mv_ratio, dtype=float),
            u_mix_mv_ratio=np.asarray(np.zeros(t_len) if u_mix_mv_ratio is None else u_mix_mv_ratio, dtype=float),
            capital_anchor_error=anchor_error,
            delta_ch=capital_ch,
            delta_q=capital_q,
            delta_retail=capital_retail,
            delta_ch_alloc=delta_ch_alloc,
            delta_q_alloc=delta_q_alloc,
            delta_retail_alloc=delta_retail_alloc,
            delta_ch_display=delta_ch_display,
            delta_q_display=delta_q_display,
            delta_retail_display=delta_retail_display,
            noise_ratio=noise_ratio,
            explain_ratio=explain_ratio,
            inertia_mean=float(np.mean(phi)) if t_len else 0.0,
            damping_mean=float(np.mean(theta)) if t_len else 0.0,
            hot_money_ratio=dominant_info["hot_money_ratio"],
            quant_ratio=dominant_info["quant_ratio"],
            retail_ratio=dominant_info["retail_ratio"],
            dominant_type=dominant_info["dominant_type"],
            dominant_intention=dominant_info["dominant_intention"],
            closure_error=closure_error,
            pid_closure_error=pid_closure_error,
            alloc_closure_error=alloc_closure_error,
            display_closure_error=closure_error,
            capital_cp_identity_error=capital_cp_identity_error,
            capital_ci_identity_error=0.0,
            capital_cd_identity_error=0.0,
            capital_identity_error=capital_cp_identity_error,
            dominant_source="capital_external_force",
            display_fields_used_for_dominant=False,
            kf_converged=kf_converged,
            mode=self.mode_name,
            u_basis_effective=u_basis_effective,
            mv_ratio_input_requested=mv_ratio_input_requested,
            mv_ratio_input_applied=mv_ratio_input_applied,
        )
        if mv_ratio_input_requested and not mv_ratio_input_applied:
            result.warnings.append("mv_ratio input requested but float-share metadata unavailable; fell back to amount basis")
        if not kf_converged:
            result.warnings.append("KF did not converge")
        if closure_error > 1e-7:
            result.warnings.append(f"High display closure error: {closure_error:.2e}")
        finite_anchor_error = anchor_error[np.isfinite(anchor_error)]
        if len(finite_anchor_error) and float(np.mean(finite_anchor_error)) > self.anchor_error_max:
            result.warnings.append("Capital anchor consistency is weak")
        if capital_cp_identity_error > 1e-7:
            result.warnings.append(f"Capital identity error: {capital_cp_identity_error:.2e}")
        return result

    def _run_kalman_filter(
        self,
        delta_p: np.ndarray,
        u_ch: np.ndarray,
        u_mix: np.ndarray,
        u_q: np.ndarray,
        u_retail: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        t_len = len(delta_p)
        psi_prev = np.zeros(self.STATE_DIM)
        p_prev = self.init_cov_scale * np.eye(self.STATE_DIM)
        psi_filtered = np.zeros((t_len, self.STATE_DIM))
        cov_filtered = np.zeros((t_len, self.STATE_DIM, self.STATE_DIM))
        eps_prev = 0.0
        sigma_hist = np.std(delta_p[1:]) if t_len > 1 and np.std(delta_p[1:]) > self.eps else 1.0
        for t in range(t_len):
            x_t = self._observation_vector(t, delta_p, u_ch, u_mix, u_q, u_retail)
            psi_pred = psi_prev.copy()
            p_pred = p_prev + self.Q
            sigma_ewma = np.std(delta_p[max(0, t - 10) : t + 1]) if t > 0 else sigma_hist
            r_eff = self.r_base * (sigma_hist / (sigma_ewma + self.eps)) ** 2
            denom = x_t @ p_pred @ x_t + r_eff + self.eps
            k_gain = p_pred @ x_t / denom
            y_adjusted = delta_p[t] - self.kappa_i * eps_prev
            innovation = y_adjusted - x_t @ psi_pred
            psi_update = psi_pred + k_gain * innovation
            p_update = (np.eye(self.STATE_DIM) - np.outer(k_gain, x_t)) @ p_pred
            eps_prev = delta_p[t] - self.kappa_i * eps_prev - x_t @ psi_update
            psi_filtered[t] = psi_update
            cov_filtered[t] = p_update
            psi_prev, p_prev = psi_update, p_update
        return psi_filtered, cov_filtered

    def _extract_from_daily_sample(self, sample: DailySample) -> dict[str, np.ndarray]:
        rows = list(getattr(sample, "rows", []) or [])
        if rows:
            return self._extract_from_feature_rows(rows)
        return self._extract_from_summary(getattr(sample, "feature_summary", {}) or {})

    def _extract_from_feature_rows(self, rows: list[dict]) -> dict[str, np.ndarray]:
        max_window = 0
        for row in rows:
            value = row.get("window_id", 0)
            if str(value).isdigit():
                max_window = max(max_window, int(value))
        t_len = max(48, max_window + 1)
        delta_p = np.zeros(t_len)
        u_ch = np.zeros(t_len)
        u_q = np.zeros(t_len)
        u_retail = np.zeros(t_len)
        u_mix = np.zeros(t_len)
        price_basis = np.zeros(t_len)
        u_ch_amount_ratio = np.zeros(t_len)
        u_q_amount_ratio = np.zeros(t_len)
        u_retail_amount_ratio = np.zeros(t_len)
        u_mix_amount_ratio = np.zeros(t_len)
        u_ch_mv_ratio = np.zeros(t_len)
        u_q_mv_ratio = np.zeros(t_len)
        u_retail_mv_ratio = np.zeros(t_len)
        u_mix_mv_ratio = np.zeros(t_len)
        ch_anchor = np.zeros(t_len)
        mix_qr = np.zeros(t_len)
        flow_windows = 0
        mv_ratio_valid_windows = 0
        for row in rows:
            t = int(float(row.get("window_id", 0) or 0))
            if t < 0 or t >= t_len:
                continue
            amount = self._to_float_any(row, ["deal_amount", "amount", "鎴愪氦棰?"])
            close_price = self._to_float_any(row, ["window_close_price", "close_price", "last_price"])
            float_mv = self._to_float_any(row, ["float_mv"])
            buy = self._to_float_any(row, ["signal_deal_buy_amount", "buy_amount", "涓诲姩涔版垚浜ら"])
            sell = self._to_float_any(row, ["signal_deal_sell_amount", "sell_amount", "涓诲姩鍗栨垚浜ら"])
            impact = self._to_float_any(row, ["pi_max_price_impact_pct", "price_impact", "浠锋牸鍐插嚮"])
            burst = self._to_float_any(row, ["rs_burst_ratio", "burst_ratio", "鐖嗗彂搴?"])
            cancel = self._to_float_any(row, ["cb_cancel_order_ratio", "cancel_ratio", "鎾ゅ崟鐜?"])
            explicit_ch = self._to_float_any(row, ["CH_rule_t", "signed_large_active_amount", "signed_hot_money_amount"], np.nan)
            explicit_q = self._to_float_any(row, ["Q_rule_t", "signed_quant_amount"], np.nan)
            explicit_r = self._to_float_any(row, ["R_seed_t", "signed_retail_amount"], np.nan)
            explicit_mix = self._to_float_any(row, ["signed_mix_qr_amount", "signed_quant_retail_amount"], np.nan)
            if np.isfinite(explicit_q) or np.isfinite(explicit_r):
                explicit_mix = (explicit_q if np.isfinite(explicit_q) else 0.0) + (
                    explicit_r if np.isfinite(explicit_r) else 0.0
                )
            net = buy - sell
            has_explicit_anchor = np.isfinite(explicit_ch) and np.isfinite(explicit_mix)
            if has_explicit_anchor:
                ch_anchor[t] = explicit_ch
                u_q[t] = explicit_q if np.isfinite(explicit_q) else 0.0
                u_retail[t] = explicit_r if np.isfinite(explicit_r) else 0.0
                mix_qr[t] = explicit_mix
                net = explicit_ch + explicit_mix
            else:
                hot_score = min(1.0, max(0.0, (amount - 500_000.0) / 2_000_000.0) + 0.4 * burst)
                ch_anchor[t] = net * min(1.0, hot_score)
                mix_qr[t] = net - ch_anchor[t]
                u_q[t] = mix_qr[t]
                u_retail[t] = 0.0
            sign = 1.0 if net >= 0 else -1.0
            delta_p[t] = impact if has_explicit_anchor else impact * sign
            u_ch[t] = ch_anchor[t]
            u_mix[t] = mix_qr[t] * (1.0 + min(cancel, 1.0))
            price_basis[t] = close_price
            if abs(ch_anchor[t]) > self.eps or abs(mix_qr[t]) > self.eps or abs(u_retail[t]) > self.eps:
                flow_windows += 1
            if abs(amount) > self.eps:
                u_ch_amount_ratio[t] = ch_anchor[t] / amount
                u_q_amount_ratio[t] = u_q[t] / amount
                u_retail_amount_ratio[t] = u_retail[t] / amount
                u_mix_amount_ratio[t] = mix_qr[t] / amount
            if abs(float_mv) > self.eps:
                u_ch_mv_ratio[t] = ch_anchor[t] / float_mv
                u_q_mv_ratio[t] = u_q[t] / float_mv
                u_retail_mv_ratio[t] = u_retail[t] / float_mv
                u_mix_mv_ratio[t] = mix_qr[t] / float_mv
                if abs(ch_anchor[t]) > self.eps or abs(mix_qr[t]) > self.eps or abs(u_retail[t]) > self.eps:
                    mv_ratio_valid_windows += 1
        mv_ratio_input_requested = str(self.config.get("u_source_type", "") or "").strip() == "mv_ratio"
        mv_ratio_input_applied = mv_ratio_input_requested and flow_windows > 0 and mv_ratio_valid_windows >= flow_windows
        effective_u_ch = u_ch_mv_ratio if mv_ratio_input_applied else u_ch
        effective_u_q = u_q_mv_ratio if mv_ratio_input_applied else u_q
        effective_u_retail = u_retail_mv_ratio if mv_ratio_input_applied else u_retail
        effective_u_mix = u_mix_mv_ratio if mv_ratio_input_applied else u_mix
        effective_ch_anchor = u_ch_mv_ratio if mv_ratio_input_applied else ch_anchor
        effective_mix_qr = u_mix_mv_ratio if mv_ratio_input_applied else mix_qr
        return {
            "delta_p": delta_p,
            "u_ch": effective_u_ch,
            "u_q": effective_u_q,
            "u_retail": effective_u_retail,
            "u_mix": effective_u_mix,
            "price_basis": price_basis,
            "u_ch_amount_ratio": u_ch_amount_ratio,
            "u_q_amount_ratio": u_q_amount_ratio,
            "u_retail_amount_ratio": u_retail_amount_ratio,
            "u_mix_amount_ratio": u_mix_amount_ratio,
            "u_ch_mv_ratio": u_ch_mv_ratio,
            "u_q_mv_ratio": u_q_mv_ratio,
            "u_retail_mv_ratio": u_retail_mv_ratio,
            "u_mix_mv_ratio": u_mix_mv_ratio,
            "ch_anchor": self._adaptive_normalize(effective_ch_anchor),
            "mix_qr": self._adaptive_normalize(effective_mix_qr),
            "u_basis_effective": "mv_ratio" if mv_ratio_input_applied else "amount",
            "mv_ratio_input_requested": mv_ratio_input_requested,
            "mv_ratio_input_applied": mv_ratio_input_applied,
        }

    def _extract_from_summary(self, summary: dict) -> dict[str, np.ndarray]:
        t_len = 48
        delta_p = np.zeros(t_len)
        u_ch = np.zeros(t_len)
        u_q = np.zeros(t_len)
        u_retail = np.zeros(t_len)
        u_mix = np.zeros(t_len)
        price_basis = np.zeros(t_len)
        u_ch_amount_ratio = np.zeros(t_len)
        u_q_amount_ratio = np.zeros(t_len)
        u_retail_amount_ratio = np.zeros(t_len)
        u_mix_amount_ratio = np.zeros(t_len)
        u_ch_mv_ratio = np.zeros(t_len)
        u_q_mv_ratio = np.zeros(t_len)
        u_retail_mv_ratio = np.zeros(t_len)
        u_mix_mv_ratio = np.zeros(t_len)
        ch_anchor = np.zeros(t_len)
        mix_qr = np.zeros(t_len)
        net_direction = float(summary.get("net_direction", 0.0) or 0.0)
        deal_amount = float(summary.get("deal_amount", 0.0) or 0.0)
        burst = float(summary.get("burst_ratio", 0.0) or 0.0)
        cancel = float(summary.get("cancel_ratio", 0.0) or 0.0)
        impact = float(summary.get("price_impact", 0.0) or 0.0)
        tail_ratio = float(summary.get("tail_ratio", 0.0) or 0.0)
        last15 = float(summary.get("last15_return", 0.0) or 0.0)
        active_windows = [10, 24, 42, 45]
        for idx, t in enumerate(active_windows):
            scale = [0.25, 0.25, 0.2, 0.3][idx]
            delta_p[t] = (impact * net_direction if impact else net_direction * 0.01) * scale
            if t >= 42:
                delta_p[t] += last15 * scale
            net_amount = deal_amount * net_direction * scale
            hot_score = min(1.0, 0.35 + burst + tail_ratio if deal_amount >= 500_000 else 0.25)
            ch_anchor[t] = net_amount * hot_score
            mix_qr[t] = net_amount - ch_anchor[t]
            u_q[t] = mix_qr[t]
            u_ch[t] = ch_anchor[t]
            u_mix[t] = mix_qr[t] * (1.0 + min(cancel, 1.0))
        return {
            "delta_p": delta_p,
            "u_ch": u_ch,
            "u_q": u_q,
            "u_retail": u_retail,
            "u_mix": u_mix,
            "price_basis": price_basis,
            "u_ch_amount_ratio": u_ch_amount_ratio,
            "u_q_amount_ratio": u_q_amount_ratio,
            "u_retail_amount_ratio": u_retail_amount_ratio,
            "u_mix_amount_ratio": u_mix_amount_ratio,
            "u_ch_mv_ratio": u_ch_mv_ratio,
            "u_q_mv_ratio": u_q_mv_ratio,
            "u_retail_mv_ratio": u_retail_mv_ratio,
            "u_mix_mv_ratio": u_mix_mv_ratio,
            "ch_anchor": self._adaptive_normalize(ch_anchor),
            "mix_qr": self._adaptive_normalize(mix_qr),
            "u_basis_effective": "amount",
            "mv_ratio_input_requested": str(self.config.get("u_source_type", "") or "").strip() == "mv_ratio",
            "mv_ratio_input_applied": False,
        }

    def _extract_from_level2_window(self, level2_window) -> dict[str, np.ndarray]:
        trades = list(getattr(level2_window, "trades", []) or [])
        windows = list(getattr(level2_window, "windows", []) or range(48))
        t_len = len(windows) if windows else 48
        price_basis = np.zeros(t_len)
        u_ch_amount_ratio = np.zeros(t_len)
        u_q_amount_ratio = np.zeros(t_len)
        u_retail_amount_ratio = np.zeros(t_len)
        u_mix_amount_ratio = np.zeros(t_len)
        u_ch_mv_ratio = np.zeros(t_len)
        u_q_mv_ratio = np.zeros(t_len)
        u_retail_mv_ratio = np.zeros(t_len)
        u_mix_mv_ratio = np.zeros(t_len)
        u_ch = np.zeros(t_len)
        u_q = np.zeros(t_len)
        u_retail = np.zeros(t_len)
        u_mix = np.zeros(t_len)
        ch_anchor = np.zeros(t_len)
        mix_qr = np.zeros(t_len)
        for trade in trades:
            t = int(getattr(trade, "window_id", 0) or 0)
            if t < 0 or t >= t_len:
                continue
            signed = float(getattr(trade, "signed_amount", 0.0) or 0.0)
            amount = abs(float(getattr(trade, "amount", signed) or signed))
            is_active = bool(getattr(trade, "is_active", False))
            cross_level = float(getattr(trade, "cross_level", 0.0) or 0.0)
            if amount >= 500_000 and is_active and cross_level >= 2:
                u_ch[t] += signed
                ch_anchor[t] += signed
            else:
                u_mix[t] += signed
                u_q[t] += signed
                mix_qr[t] += signed
        vwaps = list(getattr(level2_window, "vwaps", []) or [])
        delta_p = self._compute_delta_p_from_prices(vwaps, t_len)
        return {
            "delta_p": delta_p,
            "u_ch": u_ch,
            "u_q": u_q,
            "u_retail": u_retail,
            "u_mix": u_mix,
            "price_basis": price_basis,
            "u_ch_amount_ratio": u_ch_amount_ratio,
            "u_q_amount_ratio": u_q_amount_ratio,
            "u_retail_amount_ratio": u_retail_amount_ratio,
            "u_mix_amount_ratio": u_mix_amount_ratio,
            "u_ch_mv_ratio": u_ch_mv_ratio,
            "u_q_mv_ratio": u_q_mv_ratio,
            "u_retail_mv_ratio": u_retail_mv_ratio,
            "u_mix_mv_ratio": u_mix_mv_ratio,
            "ch_anchor": self._adaptive_normalize(ch_anchor),
            "mix_qr": self._adaptive_normalize(mix_qr),
            "u_basis_effective": "amount",
            "mv_ratio_input_requested": str(self.config.get("u_source_type", "") or "").strip() == "mv_ratio",
            "mv_ratio_input_applied": False,
        }

    def _rts_backward_smooth(self, psi_filtered: np.ndarray, cov_filtered: np.ndarray) -> np.ndarray:
        t_len, n_state = psi_filtered.shape
        if t_len == 0:
            return psi_filtered
        psi_smooth = np.zeros_like(psi_filtered)
        psi_smooth[-1] = psi_filtered[-1]
        for t in range(t_len - 2, -1, -1):
            p_pred = cov_filtered[t] + self.Q
            try:
                gain = cov_filtered[t] @ np.linalg.inv(p_pred + self.eps * np.eye(n_state))
            except np.linalg.LinAlgError:
                gain = 0.1 * np.eye(n_state)
            psi_smooth[t] = psi_filtered[t] + gain @ (psi_smooth[t + 1] - psi_filtered[t])
        return psi_smooth

    def _adaptive_normalize(self, series: np.ndarray) -> np.ndarray:
        series = np.asarray(series, dtype=float)
        if len(series) == 0:
            return series
        non_zero = series[np.abs(series) > self.eps]
        scale = np.nanstd(non_zero) if len(non_zero) > 1 else 0.0
        if scale < self.eps:
            scale = max(np.nanmax(np.abs(series)), 1.0)
        return np.clip(series / (scale + self.eps), -self.clip_limit, self.clip_limit)

    def _compute_delta_p_from_prices(self, prices: list, t_len: int) -> np.ndarray:
        delta_p = np.zeros(t_len)
        values = [float(value) for value in prices if value not in (None, "")]
        for t in range(1, min(t_len, len(values))):
            if values[t] > 0 and values[t - 1] > 0:
                delta_p[t] = np.log(values[t]) - np.log(values[t - 1])
        return delta_p

    def _determine_dominant(self, capital_ch, capital_q, capital_retail) -> dict:
        t_len = len(capital_ch)
        labels = []
        intentions = []
        for t in range(t_len):
            candidates = [
                ("hot_money", capital_ch[t]),
                ("quant", capital_q[t]),
                ("retail", capital_retail[t]),
            ]
            key, value = max(candidates, key=lambda item: abs(item[1]))
            labels.append(key)
            intentions.append("买入" if value > 0 else "卖出" if value < 0 else "中性")
        counts = {key: labels.count(key) for key in ("hot_money", "quant", "retail")}
        total = sum(counts.values()) + self.eps
        ratios = {key: value / total for key, value in counts.items()}
        dominant_key = max(ratios.items(), key=lambda item: item[1])[0]
        tail_values = {
            "hot_money": capital_ch[-1] if t_len else 0.0,
            "quant": capital_q[-1] if t_len else 0.0,
            "retail": capital_retail[-1] if t_len else 0.0,
        }
        dominant_value = tail_values[dominant_key]
        dominant_type = {"hot_money": "游资", "quant": "量化", "retail": "散户"}.get(dominant_key, "unknown")
        if self.mode_name == "baseline_4d":
            hot_ratio = ratios["hot_money"]
            hot_threshold = float(
                self.pid_config.get(
                    "baseline_4d_hot_money_dominant_threshold",
                    self.pid_config.get("capital_structural_strong_ratio", 0.46),
                )
            )
            if hot_ratio >= hot_threshold and hot_ratio >= max(ratios["quant"], ratios["retail"]):
                dominant_type = "游资"
                dominant_value = tail_values["hot_money"]
            else:
                dominant_type = "unknown"
                dominant_value = (capital_ch[-1] + capital_q[-1] + capital_retail[-1]) if t_len else 0.0
        return {
            "hot_money_ratio": ratios["hot_money"],
            "quant_ratio": ratios["quant"],
            "retail_ratio": ratios["retail"],
            "dominant_type": dominant_type,
            "dominant_intention": "买入" if dominant_value > 0 else "卖出" if dominant_value < 0 else "中性",
            "window_dominant": labels,
            "window_intentions": intentions,
        }

    def _check_convergence(self, psi_filtered: np.ndarray) -> bool:
        if len(psi_filtered) < self.convergence_window:
            return False
        return bool(np.abs(np.diff(psi_filtered[-self.convergence_window :], axis=0)).max() < self.convergence_tol)

    def _to_float_any(self, row: dict, names: list[str], default: float = 0.0) -> float:
        for name in names:
            if name in row and row.get(name) not in (None, ""):
                try:
                    return float(row.get(name))
                except (TypeError, ValueError):
                    continue
        return default

    def _max_abs(self, values: np.ndarray) -> float:
        return float(np.nanmax(np.abs(values))) if len(values) else 0.0

    def _observation_vector(
        self,
        t: int,
        delta_p: np.ndarray,
        u_ch: np.ndarray,
        u_mix: np.ndarray,
        u_q: np.ndarray,
        u_retail: np.ndarray,
    ) -> np.ndarray:
        raise NotImplementedError

    def _extract_components(self, psi: np.ndarray, t_len: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        raise NotImplementedError

    def _compute_external_terms(
        self,
        t: int,
        beta_ch: np.ndarray,
        beta_mix: np.ndarray,
        beta_q: np.ndarray,
        beta_retail: np.ndarray,
        u_ch_prev: float,
        u_mix_prev: float,
        u_q_prev: float,
        u_retail_prev: float,
    ) -> tuple[float, float, float, float]:
        raise NotImplementedError

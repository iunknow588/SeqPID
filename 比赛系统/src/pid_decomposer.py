from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    from schemas import DailySample
except Exception:  # pragma: no cover - keeps this module importable in isolation
    DailySample = Any


logger = logging.getLogger(__name__)


@dataclass
class DecompositionResult:
    stock_code: str
    transaction_date: str
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
    capital_q: np.ndarray = field(default_factory=lambda: np.zeros(48))
    capital_retail: np.ndarray = field(default_factory=lambda: np.zeros(48))
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
    kf_converged: bool = False
    mode: str = "baseline_4d"
    warnings: list[str] = field(default_factory=list)


class PIDDecomposer:
    """Rule-anchored PID decomposer.

    The first Python implementation follows the current design document:
    large active orders anchor hot money, small/passive flow forms a
    quant+retail mixed pool, and capital values are solved from the PID
    alliance equations.
    """

    def __init__(self, config: dict):
        self.config = config
        self.pid_config = config.get("pid_decomposer", {})
        self.species_rules = config.get("species_rules", {})
        self.kf_params = config.get("kf_params", {})
        q_default = [0.001, 0.01, 0.01, 0.005]
        q_diag = self.kf_params.get("process_noise_diag_anchor", self.kf_params.get("process_noise_diag", q_default))
        if len(q_diag) >= 5:
            q_diag = [q_diag[0], q_diag[1], (q_diag[2] + q_diag[3]) / 2.0, q_diag[4]]
        self.Q = np.diag(np.asarray(q_diag[:4], dtype=float))
        self.r_base = float(self.kf_params.get("observation_noise_base", 1e-4))
        self.init_cov_scale = float(self.kf_params.get("init_cov_scale", 10.0))
        self.convergence_tol = float(self.kf_params.get("convergence_tol", 1e-4))
        self.convergence_window = int(self.kf_params.get("convergence_window", 10))
        self.kappa_i = float(self.pid_config.get("kappa_i", config.get("kappa_i", 0.5)))
        self.anchor_error_max = float(self.pid_config.get("capital_anchor_error_max", 0.4))
        self.eps = 1e-8
        self.clip_limit = 3.0

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
    ) -> DecompositionResult:
        T = len(delta_p)
        u_ch_norm = self._adaptive_normalize(u_ch)
        u_mix_norm = self._adaptive_normalize(u_mix)
        psi_filtered, eps_filtered, cov_filtered = self._kalman_filter_anchor(delta_p, u_ch_norm, u_mix_norm)
        psi = self._rts_backward_smooth(psi_filtered, cov_filtered)

        phi = psi[:, 0]
        beta_ch = psi[:, 1]
        beta_mix = psi[:, 2]
        theta = psi[:, 3]
        beta_q = beta_mix.copy()
        beta_retail = np.zeros(T)

        c_p = np.zeros(T)
        c_i = np.zeros(T)
        c_d = np.zeros(T)
        eps_smooth = np.zeros(T)
        capital_ch = np.zeros(T)
        capital_q = np.zeros(T)
        capital_retail = np.zeros(T)
        anchor_error = np.full(T, np.nan)
        delta_ch_alloc = np.zeros(T)
        delta_q_alloc = np.zeros(T)
        delta_retail_alloc = np.zeros(T)
        w_ch_series = np.zeros(T)
        w_mix_series = np.zeros(T)

        for t in range(T):
            delta_prev = delta_p[t - 1] if t > 0 else 0.0
            eps_prev = eps_smooth[t - 1] if t > 0 else 0.0
            d_driver = (delta_p[t - 1] - delta_p[t - 2]) if t > 1 else 0.0
            u_ch_prev = u_ch_norm[t - 1] if t > 0 else 0.0
            u_mix_prev = u_mix_norm[t - 1] if t > 0 else 0.0

            c_p[t] = beta_ch[t] * u_ch_prev + beta_mix[t] * u_mix_prev
            c_i[t] = phi[t] * delta_prev + self.kappa_i * eps_prev
            c_d[t] = theta[t] * d_driver
            eps_smooth[t] = delta_p[t] - c_p[t] - c_i[t] - c_d[t]

            ch_pid = 0.5 * (c_p[t] + c_i[t] - c_d[t])
            q_pid = 0.5 * (c_p[t] + c_d[t] - c_i[t])
            retail_pid = 0.5 * (c_i[t] + c_d[t] - c_p[t])

            if np.isfinite(ch_anchor[t]) and np.isfinite(mix_qr[t]):
                q_anchor = 0.5 * (mix_qr[t] + c_p[t] - c_i[t])
                retail_anchor = 0.5 * (mix_qr[t] - c_p[t] + c_i[t])
                ch_from_mix = 0.5 * (c_p[t] + c_i[t] - mix_qr[t])
                denom = max(abs(ch_anchor[t]), abs(ch_from_mix), self.eps)
                err = abs(ch_anchor[t] - ch_from_mix) / denom
                anchor_error[t] = err
                if err < self.anchor_error_max:
                    capital_ch[t] = ch_anchor[t]
                    capital_q[t] = q_anchor
                    capital_retail[t] = retail_anchor
                else:
                    capital_ch[t] = ch_pid
                    capital_q[t] = q_pid
                    capital_retail[t] = retail_pid
            else:
                capital_ch[t] = ch_pid
                capital_q[t] = q_pid
                capital_retail[t] = retail_pid

            total_flow = abs(u_ch_prev) + abs(u_mix_prev) + self.eps
            w_ch = abs(u_ch_prev) / total_flow
            w_mix = abs(u_mix_prev) / total_flow
            w_ch_series[t] = w_ch
            w_mix_series[t] = w_mix
            # Display/allocation口径保持价格闭合；资金判断不依赖该口径。
            delta_ch_alloc[t] = beta_ch[t] * u_ch_prev + c_i[t] * w_ch + c_d[t] * min(w_ch, 0.1)
            remaining = c_p[t] + c_i[t] + c_d[t] - delta_ch_alloc[t]
            delta_q_alloc[t] = remaining * 0.5
            delta_retail_alloc[t] = remaining * 0.5

        delta_ch_display = delta_ch_alloc + eps_smooth * w_ch_series
        delta_q_display = delta_q_alloc + eps_smooth * w_mix_series * 0.5
        delta_retail_display = delta_retail_alloc + eps_smooth * w_mix_series * 0.5

        total_pid = c_p + c_i + c_d + eps_smooth
        pid_closure_error = self._max_abs(total_pid - delta_p)
        total_alloc = delta_ch_alloc + delta_q_alloc + delta_retail_alloc + eps_smooth
        alloc_closure_error = self._max_abs(total_alloc - delta_p)
        total_display = delta_ch_display + delta_q_display + delta_retail_display
        closure_error = self._max_abs(total_display - delta_p)

        noise_ratio = np.abs(eps_smooth) / np.maximum(np.abs(delta_p), self.eps)
        explain_ratio = 1.0 - np.minimum(noise_ratio, 1.0)
        dominant_info = self._determine_dominant(capital_ch, capital_q, capital_retail)
        kf_converged = self._check_convergence(psi_filtered)

        result = DecompositionResult(
            stock_code=stock_code,
            transaction_date=transaction_date,
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
            capital_q=capital_q,
            capital_retail=capital_retail,
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
            inertia_mean=float(np.mean(phi)) if T else 0.0,
            damping_mean=float(np.mean(theta)) if T else 0.0,
            hot_money_ratio=dominant_info["hot_money_ratio"],
            quant_ratio=dominant_info["quant_ratio"],
            retail_ratio=dominant_info["retail_ratio"],
            dominant_type=dominant_info["dominant_type"],
            dominant_intention=dominant_info["dominant_intention"],
            closure_error=closure_error,
            pid_closure_error=pid_closure_error,
            alloc_closure_error=alloc_closure_error,
            kf_converged=kf_converged,
            mode="enhanced_5d" if np.nanmean(np.abs(c_d)) > self.eps else "baseline_4d",
        )
        if not kf_converged:
            result.warnings.append("KF did not converge")
        if closure_error > 1e-7:
            result.warnings.append(f"High display closure error: {closure_error:.2e}")
        if np.nanmean(anchor_error) > self.anchor_error_max:
            result.warnings.append("Capital anchor consistency is weak")
        return result

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
        T = max(48, max_window + 1)
        delta_p = np.zeros(T)
        u_ch = np.zeros(T)
        u_mix = np.zeros(T)
        ch_anchor = np.zeros(T)
        mix_qr = np.zeros(T)
        for row in rows:
            t = int(float(row.get("window_id", 0) or 0))
            if t < 0 or t >= T:
                continue
            amount = self._to_float_any(row, ["deal_amount", "amount", "成交额"])
            buy = self._to_float_any(row, ["signal_deal_buy_amount", "buy_amount", "主动买成交额"])
            sell = self._to_float_any(row, ["signal_deal_sell_amount", "sell_amount", "主动卖成交额"])
            impact = self._to_float_any(row, ["pi_max_price_impact_pct", "price_impact", "价格冲击"])
            burst = self._to_float_any(row, ["rs_burst_ratio", "burst_ratio", "爆发度"])
            cancel = self._to_float_any(row, ["cb_cancel_order_ratio", "cancel_ratio", "撤单率"])
            explicit_ch = self._to_float_any(row, ["signed_large_active_amount", "signed_hot_money_amount"], np.nan)
            explicit_mix = self._to_float_any(row, ["signed_mix_qr_amount", "signed_quant_retail_amount"], np.nan)
            net = buy - sell
            has_explicit_anchor = np.isfinite(explicit_ch) and np.isfinite(explicit_mix)
            if has_explicit_anchor:
                ch_anchor[t] = explicit_ch
                mix_qr[t] = explicit_mix
                net = explicit_ch + explicit_mix
            else:
                hot_score = min(1.0, max(0.0, (amount - 500_000.0) / 2_000_000.0) + 0.4 * burst)
                hot_score = min(1.0, hot_score)
                ch_anchor[t] = net * hot_score
                mix_qr[t] = net - ch_anchor[t]
            sign = 1.0 if net >= 0 else -1.0
            delta_p[t] = impact if has_explicit_anchor else impact * sign
            u_ch[t] = ch_anchor[t]
            # cancel较高时提高混合池强度，保留净方向符号。
            u_mix[t] = mix_qr[t] * (1.0 + min(cancel, 1.0))
        return {
            "delta_p": delta_p,
            "u_ch": u_ch,
            "u_mix": u_mix,
            "ch_anchor": self._adaptive_normalize(ch_anchor),
            "mix_qr": self._adaptive_normalize(mix_qr),
        }

    def _extract_from_summary(self, summary: dict) -> dict[str, np.ndarray]:
        T = 48
        delta_p = np.zeros(T)
        u_ch = np.zeros(T)
        u_mix = np.zeros(T)
        ch_anchor = np.zeros(T)
        mix_qr = np.zeros(T)
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
            u_ch[t] = ch_anchor[t]
            u_mix[t] = mix_qr[t] * (1.0 + min(cancel, 1.0))
        return {
            "delta_p": delta_p,
            "u_ch": u_ch,
            "u_mix": u_mix,
            "ch_anchor": self._adaptive_normalize(ch_anchor),
            "mix_qr": self._adaptive_normalize(mix_qr),
        }

    def _extract_from_level2_window(self, level2_window) -> dict[str, np.ndarray]:
        trades = list(getattr(level2_window, "trades", []) or [])
        windows = list(getattr(level2_window, "windows", []) or range(48))
        T = len(windows) if windows else 48
        u_ch = np.zeros(T)
        u_mix = np.zeros(T)
        ch_anchor = np.zeros(T)
        mix_qr = np.zeros(T)
        for trade in trades:
            t = int(getattr(trade, "window_id", 0) or 0)
            if t < 0 or t >= T:
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
                mix_qr[t] += signed
        vwaps = list(getattr(level2_window, "vwaps", []) or [])
        delta_p = self._compute_delta_p_from_prices(vwaps, T)
        return {
            "delta_p": delta_p,
            "u_ch": u_ch,
            "u_mix": u_mix,
            "ch_anchor": self._adaptive_normalize(ch_anchor),
            "mix_qr": self._adaptive_normalize(mix_qr),
        }

    def _kalman_filter_anchor(self, delta_p: np.ndarray, u_ch: np.ndarray, u_mix: np.ndarray):
        T = len(delta_p)
        n_state = 4
        psi_prev = np.zeros(n_state)
        p_prev = self.init_cov_scale * np.eye(n_state)
        psi_filtered = np.zeros((T, n_state))
        cov_filtered = np.zeros((T, n_state, n_state))
        eps_prev = 0.0
        sigma_hist = np.std(delta_p[1:]) if T > 1 and np.std(delta_p[1:]) > self.eps else 1.0
        for t in range(T):
            d_driver = (delta_p[t - 1] - delta_p[t - 2]) if t > 1 else 0.0
            x_t = np.array(
                [
                    delta_p[t - 1] if t > 0 else 0.0,
                    u_ch[t - 1] if t > 0 else 0.0,
                    u_mix[t - 1] if t > 0 else 0.0,
                    d_driver,
                ],
                dtype=float,
            )
            psi_pred = psi_prev.copy()
            p_pred = p_prev + self.Q
            sigma_ewma = np.std(delta_p[max(0, t - 10) : t + 1]) if t > 0 else sigma_hist
            r_eff = self.r_base * (sigma_hist / (sigma_ewma + self.eps)) ** 2
            denom = x_t @ p_pred @ x_t + r_eff + self.eps
            k_gain = p_pred @ x_t / denom
            y_adjusted = delta_p[t] - self.kappa_i * eps_prev
            innovation = y_adjusted - x_t @ psi_pred
            psi_update = psi_pred + k_gain * innovation
            p_update = (np.eye(n_state) - np.outer(k_gain, x_t)) @ p_pred
            eps_prev = delta_p[t] - self.kappa_i * eps_prev - x_t @ psi_update
            psi_filtered[t] = psi_update
            cov_filtered[t] = p_update
            psi_prev, p_prev = psi_update, p_update
        return psi_filtered, np.zeros(T), cov_filtered

    def _rts_backward_smooth(self, psi_filtered: np.ndarray, cov_filtered: np.ndarray) -> np.ndarray:
        T, n_state = psi_filtered.shape
        if T == 0:
            return psi_filtered
        psi_smooth = np.zeros_like(psi_filtered)
        psi_smooth[-1] = psi_filtered[-1]
        for t in range(T - 2, -1, -1):
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

    def _compute_delta_p_from_prices(self, prices: list, T: int) -> np.ndarray:
        delta_p = np.zeros(T)
        values = [float(value) for value in prices if value not in (None, "")]
        for t in range(1, min(T, len(values))):
            if values[t] > 0 and values[t - 1] > 0:
                delta_p[t] = np.log(values[t]) - np.log(values[t - 1])
        return delta_p

    def _determine_dominant(self, capital_ch, capital_q, capital_retail) -> dict:
        T = len(capital_ch)
        labels = []
        intentions = []
        for t in range(T):
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
            "hot_money": capital_ch[-1] if T else 0.0,
            "quant": capital_q[-1] if T else 0.0,
            "retail": capital_retail[-1] if T else 0.0,
        }
        dominant_value = tail_values[dominant_key]
        return {
            "hot_money_ratio": ratios["hot_money"],
            "quant_ratio": ratios["quant"],
            "retail_ratio": ratios["retail"],
            "dominant_type": {"hot_money": "游资", "quant": "量化", "retail": "散户"}.get(dominant_key, "unknown"),
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

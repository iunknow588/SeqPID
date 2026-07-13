from __future__ import annotations

import numpy as np

from pid_decomposer_shared import BasePIDDecomposer


class PIDDecomposer4D(BasePIDDecomposer):
    MODE_NAME = "baseline_4d"
    STATE_DIM = 4

    def _build_q_diag(self, q_diag: list[float]) -> list[float]:
        if len(q_diag) >= 5:
            q_diag = [q_diag[0], q_diag[1], (q_diag[2] + q_diag[3]) / 2.0, q_diag[4]]
        return super()._build_q_diag(q_diag)

    def _observation_vector(
        self,
        t: int,
        delta_p: np.ndarray,
        u_ch: np.ndarray,
        u_mix: np.ndarray,
        u_q: np.ndarray,
        u_retail: np.ndarray,
    ) -> np.ndarray:
        d_driver = self._driver_signal(t, delta_p)
        return np.array(
            [
                self._lagged_delta(t, delta_p),
                u_ch[t - 1] if t > 0 else 0.0,
                u_mix[t - 1] if t > 0 else 0.0,
                d_driver,
            ],
            dtype=float,
        )

    def _extract_components(self, psi: np.ndarray, t_len: int):
        phi = psi[:, 0]
        beta_ch = psi[:, 1]
        beta_mix = psi[:, 2]
        theta = psi[:, 3]
        beta_q = beta_mix.copy()
        beta_retail = np.zeros(t_len)
        return phi, beta_ch, beta_mix, beta_q, beta_retail, theta

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
    ) -> tuple[float, float, float]:
        c_p_t = beta_ch[t] * u_ch_prev + beta_mix[t] * u_mix_prev
        capital_mix = beta_mix[t] * u_mix_prev
        qr_abs = abs(u_q_prev) + abs(u_retail_prev)
        if qr_abs > self.eps:
            capital_q_t = capital_mix * abs(u_q_prev) / qr_abs
            capital_retail_t = capital_mix * abs(u_retail_prev) / qr_abs
        else:
            capital_q_t = capital_mix
            capital_retail_t = 0.0
        return c_p_t, capital_q_t, capital_retail_t

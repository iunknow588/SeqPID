from __future__ import annotations

import numpy as np

from pid_decomposer_shared import BasePIDDecomposer


class PIDDecomposer5D(BasePIDDecomposer):
    MODE_NAME = "diag_5d"
    STATE_DIM = 5

    def _observation_vector(
        self,
        t: int,
        delta_p: np.ndarray,
        u_ch: np.ndarray,
        u_mix: np.ndarray,
        u_q: np.ndarray,
        u_retail: np.ndarray,
    ) -> np.ndarray:
        d_driver = (delta_p[t - 1] - delta_p[t - 2]) if t > 1 else 0.0
        return np.array(
            [
                delta_p[t - 1] if t > 0 else 0.0,
                u_ch[t - 1] if t > 0 else 0.0,
                u_q[t - 1] if t > 0 else 0.0,
                u_retail[t - 1] if t > 0 else 0.0,
                d_driver,
            ],
            dtype=float,
        )

    def _extract_components(self, psi: np.ndarray, t_len: int):
        phi = psi[:, 0]
        beta_ch = psi[:, 1]
        beta_q = psi[:, 2]
        beta_retail = psi[:, 3]
        theta = psi[:, 4]
        beta_mix = beta_q + beta_retail
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
        c_p_t = beta_ch[t] * u_ch_prev + beta_q[t] * u_q_prev + beta_retail[t] * u_retail_prev
        capital_q_t = beta_q[t] * u_q_prev
        capital_retail_t = beta_retail[t] * u_retail_prev
        return c_p_t, capital_q_t, capital_retail_t

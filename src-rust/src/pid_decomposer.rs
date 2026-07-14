use crate::config::ConfigMap;
use crate::schemas::{DailySample, DecompositionResult};
use serde_yaml::Value;
use std::collections::HashMap;

const PID_DIM: usize = 5;

pub struct PIDDecomposer {
    mode_name: String,
    q_diag: [f64; PID_DIM],
    r_base: f64,
    init_cov_scale: f64,
    convergence_tol: f64,
    convergence_window: usize,
    kappa_i: f64,
    anchor_error_max: f64,
    baseline_4d_hot_money_dominant_threshold: f64,
    eps: f64,
    clip_limit: f64,
}

impl PIDDecomposer {
    pub fn new(config: &ConfigMap) -> Self {
        let pid_cfg = get_map(config, "pid_decomposer");
        let kf_cfg = get_map(config, "kf_params");
        let mode_name = get_string(&pid_cfg, "mode", "").unwrap_or_else(|| "baseline_4d".to_string());

        let q_default = vec![0.001, 0.01, 0.01, 0.01, 0.005];
        let mut q_diag = get_f64_list(&kf_cfg, "process_noise_diag_anchor");
        if q_diag.is_empty() {
            q_diag = get_f64_list(&kf_cfg, "process_noise_diag");
        }
        if q_diag.is_empty() {
            q_diag = q_default;
        }
        while q_diag.len() < PID_DIM {
            q_diag.push(*q_diag.last().unwrap_or(&0.01));
        }
        let mode_name = normalized_mode(&mode_name).to_string();
        let q_diag = if mode_name == "baseline_4d" {
            [
                q_diag[0],
                q_diag[1],
                (q_diag[2] + q_diag[3]) / 2.0,
                q_diag[4],
                0.0,
            ]
        } else {
            [q_diag[0], q_diag[1], q_diag[2], q_diag[3], q_diag[4]]
        };

        Self {
            mode_name,
            q_diag,
            r_base: get_f64(&kf_cfg, "observation_noise_base", 1e-4),
            init_cov_scale: get_f64(&kf_cfg, "init_cov_scale", 10.0),
            convergence_tol: get_f64(&kf_cfg, "convergence_tol", 1e-4),
            convergence_window: get_f64(&kf_cfg, "convergence_window", 10.0).max(1.0) as usize,
            kappa_i: get_f64(&pid_cfg, "kappa_i", get_f64(config, "kappa_i", 0.5)),
            anchor_error_max: get_f64(&pid_cfg, "capital_anchor_error_max", 0.4),
            baseline_4d_hot_money_dominant_threshold: get_f64(
                &pid_cfg,
                "baseline_4d_hot_money_dominant_threshold",
                get_f64(&pid_cfg, "capital_structural_strong_ratio", 0.46),
            ),
            eps: 1e-8,
            clip_limit: 3.0,
        }
    }

    pub fn decompose_sample(&self, sample: &DailySample) -> DecompositionResult {
        let features = if sample.rows.is_empty() {
            self.extract_from_summary(&sample.feature_summary)
        } else {
            self.extract_from_feature_rows(&sample.rows)
        };
        self.decompose_arrays(&sample.stock_code, &sample.transaction_date, features)
    }

    fn decompose_arrays(
        &self,
        stock_code: &str,
        transaction_date: &str,
        features: DecomposeInput,
    ) -> DecompositionResult {
        let t_len = features.delta_p.len();
        let mode_name = normalized_mode(&self.mode_name);

        let u_ch_norm = self.adaptive_normalize(&features.u_ch);
        let u_q_norm = self.adaptive_normalize(&features.u_q);
        let u_retail_norm = self.adaptive_normalize(&features.u_retail);
        let u_mix_norm = self.adaptive_normalize(&features.u_mix);

        let (psi_filtered, cov_filtered) = self.kalman_filter(&features.delta_p, &u_ch_norm, &u_q_norm, &u_retail_norm, &u_mix_norm, &mode_name);
        let psi = self.rts_backward_smooth(&psi_filtered, &cov_filtered);

        let phi: Vec<f64> = psi.iter().map(|row| row[0]).collect();
        let beta_ch: Vec<f64> = psi.iter().map(|row| row[1]).collect();
        let beta_q: Vec<f64> = psi.iter().map(|row| row[2]).collect();
        let (beta_retail, theta, beta_mix) = if mode_name == "baseline_4d" {
            (
                vec![0.0; t_len],
                psi.iter().map(|row| row[3]).collect(),
                beta_q.clone(),
            )
        } else {
            let beta_retail: Vec<f64> = psi.iter().map(|row| row[3]).collect();
            let theta: Vec<f64> = psi.iter().map(|row| row[4]).collect();
            let beta_mix = beta_q
                .iter()
                .zip(beta_retail.iter())
                .map(|(q, r)| q + r)
                .collect();
            (beta_retail, theta, beta_mix)
        };

        let mut c_p = vec![0.0; t_len];
        let mut c_i = vec![0.0; t_len];
        let mut c_d = vec![0.0; t_len];
        let mut eps_smooth = vec![0.0; t_len];
        let mut capital_ch = vec![0.0; t_len];
        let mut capital_mix = vec![0.0; t_len];
        let mut capital_q = vec![0.0; t_len];
        let mut capital_retail = vec![0.0; t_len];
        let mut anchor_error = vec![f64::NAN; t_len];
        let mut delta_ch_alloc = vec![0.0; t_len];
        let mut delta_q_alloc = vec![0.0; t_len];
        let mut delta_retail_alloc = vec![0.0; t_len];
        let mut w_ch_series = vec![0.0; t_len];
        let mut w_q_series = vec![0.0; t_len];
        let mut w_retail_series = vec![0.0; t_len];

        for t in 0..t_len {
            let delta_prev = if t > 0 { features.delta_p[t - 1] } else { 0.0 };
            let eps_prev = if t > 0 { eps_smooth[t - 1] } else { 0.0 };
            let d_driver = if t > 1 {
                features.delta_p[t - 1] - features.delta_p[t - 2]
            } else {
                0.0
            };
            let u_ch_prev = if t > 0 { u_ch_norm[t - 1] } else { 0.0 };
            let u_q_prev = if t > 0 { u_q_norm[t - 1] } else { 0.0 };
            let u_retail_prev = if t > 0 { u_retail_norm[t - 1] } else { 0.0 };
            let u_mix_prev = if t > 0 { u_mix_norm[t - 1] } else { 0.0 };

            c_p[t] = if mode_name == "baseline_4d" {
                beta_ch[t] * u_ch_prev + beta_q[t] * u_mix_prev
            } else {
                beta_ch[t] * u_ch_prev + beta_q[t] * u_q_prev + beta_retail[t] * u_retail_prev
            };
            c_i[t] = phi[t] * delta_prev + self.kappa_i * eps_prev;
            c_d[t] = theta[t] * d_driver;
            eps_smooth[t] = features.delta_p[t] - c_p[t] - c_i[t] - c_d[t];

            capital_ch[t] = beta_ch[t] * u_ch_prev;
            if mode_name == "baseline_4d" {
                capital_mix[t] = beta_q[t] * u_mix_prev;
                let qr_abs = u_q_prev.abs() + u_retail_prev.abs();
                if qr_abs > self.eps {
                    capital_q[t] = capital_mix[t] * u_q_prev.abs() / qr_abs;
                    capital_retail[t] = capital_mix[t] * u_retail_prev.abs() / qr_abs;
                } else {
                    capital_q[t] = capital_mix[t];
                    capital_retail[t] = 0.0;
                }
            } else {
                capital_q[t] = beta_q[t] * u_q_prev;
                capital_retail[t] = beta_retail[t] * u_retail_prev;
                capital_mix[t] = capital_q[t] + capital_retail[t];
            }

            let ch_anchor = features.ch_anchor[t];
            let mix_qr = features.mix_qr[t];
            let anchor_total = ch_anchor.abs() + mix_qr.abs();
            let external_total = capital_ch[t].abs() + capital_mix[t].abs();
            if ch_anchor.is_finite()
                && mix_qr.is_finite()
                && anchor_total > self.eps
                && external_total > self.eps
            {
                let rule_share = ch_anchor.abs() / anchor_total.max(self.eps);
                let external_share = capital_ch[t].abs() / external_total.max(self.eps);
                anchor_error[t] = (rule_share - external_share).abs();
            }

            let flow_abs_sum = u_ch_prev.abs() + u_q_prev.abs() + u_retail_prev.abs();
            let (w_ch, w_q, w_retail) = if flow_abs_sum > self.eps {
                (
                    u_ch_prev.abs() / flow_abs_sum,
                    u_q_prev.abs() / flow_abs_sum,
                    u_retail_prev.abs() / flow_abs_sum,
                )
            } else {
                let external_abs_sum = capital_ch[t].abs() + capital_mix[t].abs();
                if external_abs_sum > self.eps {
                    let w_ch = capital_ch[t].abs() / external_abs_sum;
                    if mode_name == "baseline_4d" {
                        let mix_weight = capital_mix[t].abs() / external_abs_sum;
                        let qr_abs = u_q_prev.abs() + u_retail_prev.abs();
                        if qr_abs > self.eps {
                            (
                                w_ch,
                                mix_weight * u_q_prev.abs() / qr_abs,
                                mix_weight * u_retail_prev.abs() / qr_abs,
                            )
                        } else {
                            (w_ch, mix_weight, 0.0)
                        }
                    } else {
                        (
                            w_ch,
                            capital_q[t].abs() / external_abs_sum,
                            capital_retail[t].abs() / external_abs_sum,
                        )
                    }
                } else {
                    (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)
                }
            };
            w_ch_series[t] = w_ch;
            w_q_series[t] = w_q;
            w_retail_series[t] = w_retail;

            delta_ch_alloc[t] = beta_ch[t] * u_ch_prev + c_i[t] * w_ch + c_d[t] * w_ch.min(0.1);
            delta_q_alloc[t] = beta_q[t] * u_q_prev + c_d[t] * w_q + c_i[t] * w_q.min(0.1);
            let allocated = delta_ch_alloc[t] + delta_q_alloc[t];
            delta_retail_alloc[t] = c_p[t] + c_i[t] + c_d[t] - allocated;
        }

        let delta_ch_display: Vec<f64> = (0..t_len)
            .map(|i| delta_ch_alloc[i] + eps_smooth[i] * w_ch_series[i])
            .collect();
        let delta_q_display: Vec<f64> = (0..t_len)
            .map(|i| delta_q_alloc[i] + eps_smooth[i] * w_q_series[i])
            .collect();
        let delta_retail_display: Vec<f64> = (0..t_len)
            .map(|i| delta_retail_alloc[i] + eps_smooth[i] * w_retail_series[i])
            .collect();

        let total_pid: Vec<f64> = (0..t_len)
            .map(|i| c_p[i] + c_i[i] + c_d[i] + eps_smooth[i])
            .collect();
        let total_alloc: Vec<f64> = (0..t_len)
            .map(|i| delta_ch_alloc[i] + delta_q_alloc[i] + delta_retail_alloc[i] + eps_smooth[i])
            .collect();
        let total_display: Vec<f64> = (0..t_len)
            .map(|i| delta_ch_display[i] + delta_q_display[i] + delta_retail_display[i])
            .collect();
        let pid_closure_error = max_abs_diff(&total_pid, &features.delta_p);
        let alloc_closure_error = max_abs_diff(&total_alloc, &features.delta_p);
        let closure_error = max_abs_diff(&total_display, &features.delta_p);
        let capital_total: Vec<f64> = (0..t_len)
            .map(|i| {
                if mode_name == "baseline_4d" {
                    capital_ch[i] + capital_mix[i]
                } else {
                    capital_ch[i] + capital_q[i] + capital_retail[i]
                }
            })
            .collect();
        let capital_cp_identity_error = max_abs_diff(&capital_total, &c_p);
        let capital_ci_identity_error = 0.0;
        let capital_cd_identity_error = 0.0;
        let capital_identity_error = capital_cp_identity_error;
        let noise_ratio: Vec<f64> = (0..t_len)
            .map(|i| eps_smooth[i].abs() / features.delta_p[i].abs().max(self.eps))
            .collect();
        let explain_ratio: Vec<f64> = noise_ratio
            .iter()
            .map(|value| 1.0 - value.min(1.0))
            .collect();
        let dominant = self.determine_dominant(&capital_ch, &capital_q, &capital_retail);
        let kf_converged = self.check_convergence(&psi_filtered, &mode_name);

        let mut warnings = Vec::new();
        if mode_name == "diag_5d" {
            warnings.push("diag_5d mode is enabled; theta should be treated as diagnostic-first".to_string());
        }
        if !kf_converged {
            warnings.push("KF did not converge".to_string());
        }
        if closure_error > 1e-7 {
            warnings.push(format!("High display closure error: {:.2e}", closure_error));
        }
        let finite_anchor_errors: Vec<f64> = anchor_error
            .iter()
            .copied()
            .filter(|value| value.is_finite())
            .collect();
        if !finite_anchor_errors.is_empty() && mean(&finite_anchor_errors) > self.anchor_error_max {
            warnings.push("Capital anchor consistency is weak".to_string());
        }
        if capital_identity_error > 1e-7 {
            warnings.push(format!("Capital identity error: {:.2e}", capital_identity_error));
        }

        DecompositionResult {
            stock_code: stock_code.to_string(),
            transaction_date: transaction_date.to_string(),
            phi: phi.clone(),
            theta: theta.clone(),
            inertia: phi.iter().copied().collect(),
            beta_ch,
            beta_q,
            beta_retail,
            beta_mix,
            damping: theta.iter().copied().collect(),
            c_p,
            c_i,
            c_d,
            eps: eps_smooth,
            capital_ch: capital_ch.clone(),
            capital_mix: capital_mix.clone(),
            capital_q: capital_q.clone(),
            capital_retail: capital_retail.clone(),
            price_basis: features.price_basis.clone(),
            u_ch_amount_ratio: features.u_ch_amount_ratio.clone(),
            u_q_amount_ratio: features.u_q_amount_ratio.clone(),
            u_retail_amount_ratio: features.u_retail_amount_ratio.clone(),
            u_mix_amount_ratio: features.u_mix_amount_ratio.clone(),
            capital_anchor_error: anchor_error,
            delta_ch: capital_ch,
            delta_q: capital_q,
            delta_retail: capital_retail,
            delta_ch_alloc,
            delta_q_alloc,
            delta_retail_alloc,
            delta_ch_display,
            delta_q_display,
            delta_retail_display,
            noise_ratio,
            explain_ratio,
            inertia_mean: mean(&phi),
            damping_mean: mean(&theta),
            hot_money_ratio: dominant.hot_money_ratio,
            quant_ratio: dominant.quant_ratio,
            retail_ratio: dominant.retail_ratio,
            dominant_type: dominant.dominant_type,
            dominant_intention: dominant.dominant_intention,
            closure_error,
            pid_closure_error,
            alloc_closure_error,
            display_closure_error: closure_error,
            capital_cp_identity_error,
            capital_ci_identity_error,
            capital_cd_identity_error,
            capital_identity_error,
            dominant_source: "capital_external_force".to_string(),
            display_fields_used_for_dominant: false,
            kf_converged,
            mode: mode_name.to_string(),
            warnings,
        }
    }

    fn extract_from_feature_rows(&self, rows: &[HashMap<String, String>]) -> DecomposeInput {
        let mut max_window = 0usize;
        for row in rows {
            if let Some(window_id) = row.get("window_id").and_then(|value| value.parse::<usize>().ok()) {
                max_window = max_window.max(window_id);
            }
        }
        let t_len = 48usize.max(max_window + 1);
        let mut delta_p = vec![0.0; t_len];
        let mut u_ch = vec![0.0; t_len];
        let mut u_q = vec![0.0; t_len];
        let mut u_retail = vec![0.0; t_len];
        let mut u_mix = vec![0.0; t_len];
        let mut price_basis = vec![0.0; t_len];
        let mut u_ch_amount_ratio = vec![0.0; t_len];
        let mut u_q_amount_ratio = vec![0.0; t_len];
        let mut u_retail_amount_ratio = vec![0.0; t_len];
        let mut u_mix_amount_ratio = vec![0.0; t_len];
        let mut ch_anchor = vec![0.0; t_len];
        let mut mix_qr = vec![0.0; t_len];

        for row in rows {
            let Some(t) = row.get("window_id").and_then(|value| value.parse::<usize>().ok()) else {
                continue;
            };
            if t >= t_len {
                continue;
            }

            let amount = parse_any(row, &["deal_amount", "amount"]).unwrap_or(0.0);
            let close_price = parse_any(row, &["window_close_price", "close_price", "last_price"]).unwrap_or(0.0);
            let buy = parse_any(row, &["signal_deal_buy_amount", "buy_amount"]).unwrap_or(0.0);
            let sell = parse_any(row, &["signal_deal_sell_amount", "sell_amount"]).unwrap_or(0.0);
            let impact = parse_any(row, &["pi_max_price_impact_pct", "price_impact"]).unwrap_or(0.0);
            let burst = parse_any(row, &["rs_burst_ratio", "burst_ratio"]).unwrap_or(0.0);
            let cancel = parse_any(row, &["cb_cancel_order_ratio", "cancel_ratio"]).unwrap_or(0.0);

            let explicit_ch = parse_any(row, &["CH_rule_t", "signed_large_active_amount", "signed_hot_money_amount"]);
            let explicit_q = parse_any(row, &["Q_rule_t", "signed_quant_amount"]);
            let explicit_r = parse_any(row, &["R_seed_t", "signed_retail_amount"]);

            let mut net = buy - sell;
            let has_explicit_anchor = explicit_ch.is_some() || explicit_q.is_some() || explicit_r.is_some();
            if has_explicit_anchor {
                ch_anchor[t] = explicit_ch.unwrap_or(0.0);
                u_q[t] = explicit_q.unwrap_or(0.0);
                u_retail[t] = explicit_r.unwrap_or(0.0);
                mix_qr[t] = u_q[t] + u_retail[t];
                net = ch_anchor[t] + mix_qr[t];
            } else {
                let hot_score = (((amount - 500_000.0) / 2_000_000.0).clamp(0.0, 1.0) + 0.4 * burst).min(1.0);
                let residual_flow = net - net * hot_score;
                let retail_share = (0.35 + cancel * 0.35 + (1.0 - burst).max(0.0) * 0.10).clamp(0.15, 0.70);
                ch_anchor[t] = net * hot_score;
                u_retail[t] = residual_flow * retail_share;
                u_q[t] = residual_flow - u_retail[t];
                mix_qr[t] = residual_flow;
            }

            let sign = if net >= 0.0 { 1.0 } else { -1.0 };
            delta_p[t] = if has_explicit_anchor { impact } else { impact * sign };
            u_ch[t] = ch_anchor[t];
            u_mix[t] = mix_qr[t] * (1.0 + cancel.min(1.0));
            price_basis[t] = close_price;
            if amount.abs() > self.eps {
                u_ch_amount_ratio[t] = ch_anchor[t] / amount;
                u_q_amount_ratio[t] = u_q[t] / amount;
                u_retail_amount_ratio[t] = u_retail[t] / amount;
                u_mix_amount_ratio[t] = mix_qr[t] / amount;
            }
        }

        let ch_anchor = self.adaptive_normalize(&ch_anchor);
        let mix_qr = self.adaptive_normalize(&mix_qr);
        DecomposeInput {
            delta_p,
            u_ch,
            u_q,
            u_retail,
            u_mix,
            price_basis,
            u_ch_amount_ratio,
            u_q_amount_ratio,
            u_retail_amount_ratio,
            u_mix_amount_ratio,
            ch_anchor,
            mix_qr,
        }
    }

    fn extract_from_summary(&self, summary: &HashMap<String, f64>) -> DecomposeInput {
        let t_len = 48;
        let mut delta_p = vec![0.0; t_len];
        let mut u_ch = vec![0.0; t_len];
        let mut u_q = vec![0.0; t_len];
        let mut u_retail = vec![0.0; t_len];
        let mut u_mix = vec![0.0; t_len];
        let price_basis = vec![0.0; t_len];
        let u_ch_amount_ratio = vec![0.0; t_len];
        let u_q_amount_ratio = vec![0.0; t_len];
        let u_retail_amount_ratio = vec![0.0; t_len];
        let u_mix_amount_ratio = vec![0.0; t_len];
        let mut ch_anchor = vec![0.0; t_len];
        let mut mix_qr = vec![0.0; t_len];

        let net_direction = *summary.get("net_direction").unwrap_or(&0.0);
        let deal_amount = *summary.get("deal_amount").unwrap_or(&0.0);
        let burst = *summary.get("burst_ratio").unwrap_or(&0.0);
        let cancel = *summary.get("cancel_ratio").unwrap_or(&0.0);
        let impact = *summary.get("price_impact").unwrap_or(&0.0);
        let tail_ratio = *summary.get("tail_ratio").unwrap_or(&0.0);
        let last15 = *summary.get("last15_return").unwrap_or(&0.0);

        let active_windows = [(10usize, 0.25), (24usize, 0.25), (42usize, 0.2), (45usize, 0.3)];
        for (t, scale) in active_windows {
            delta_p[t] = (if impact != 0.0 { impact * net_direction } else { net_direction * 0.01 }) * scale;
            if t >= 42 {
                delta_p[t] += last15 * scale;
            }
            let net_amount = deal_amount * net_direction * scale;
            let hot_score = if deal_amount >= 500_000.0 {
                (0.35 + burst + tail_ratio).min(1.0)
            } else {
                0.25
            };
            let residual_flow = net_amount - net_amount * hot_score;
            let retail_share = (0.30 + cancel * 0.35 + (1.0 - burst).max(0.0) * 0.10).clamp(0.15, 0.70);
            ch_anchor[t] = net_amount * hot_score;
            u_retail[t] = residual_flow * retail_share;
            u_q[t] = residual_flow - u_retail[t];
            mix_qr[t] = residual_flow;
            u_ch[t] = ch_anchor[t];
            u_mix[t] = mix_qr[t] * (1.0 + cancel.min(1.0));
        }

        let ch_anchor = self.adaptive_normalize(&ch_anchor);
        let mix_qr = self.adaptive_normalize(&mix_qr);
        DecomposeInput {
            delta_p,
            u_ch,
            u_q,
            u_retail,
            u_mix,
            price_basis,
            u_ch_amount_ratio,
            u_q_amount_ratio,
            u_retail_amount_ratio,
            u_mix_amount_ratio,
            ch_anchor,
            mix_qr,
        }
    }

    fn kalman_filter(
        &self,
        delta_p: &[f64],
        u_ch: &[f64],
        u_q: &[f64],
        u_retail: &[f64],
        u_mix: &[f64],
        mode_name: &str,
    ) -> (Vec<[f64; PID_DIM]>, Vec<[[f64; PID_DIM]; PID_DIM]>) {
        let t_len = delta_p.len();
        let mut psi_prev = [0.0; PID_DIM];
        let mut p_prev = diag_matrix(self.init_cov_scale);
        let mut psi_filtered = vec![[0.0; PID_DIM]; t_len];
        let mut cov_filtered = vec![[[0.0; PID_DIM]; PID_DIM]; t_len];
        let mut eps_prev = 0.0;
        let sigma_hist_raw = stddev(&delta_p[1..]);
        let sigma_hist = if sigma_hist_raw > self.eps {
            sigma_hist_raw
        } else {
            1.0
        };

        for t in 0..t_len {
            let d_driver = if t > 1 { delta_p[t - 1] - delta_p[t - 2] } else { 0.0 };
            let x_t = if mode_name == "baseline_4d" {
                [
                    if t > 0 { delta_p[t - 1] } else { 0.0 },
                    if t > 0 { u_ch[t - 1] } else { 0.0 },
                    if t > 0 { u_mix[t - 1] } else { 0.0 },
                    d_driver,
                    0.0,
                ]
            } else {
                [
                    if t > 0 { delta_p[t - 1] } else { 0.0 },
                    if t > 0 { u_ch[t - 1] } else { 0.0 },
                    if t > 0 { u_q[t - 1] } else { 0.0 },
                    if t > 0 { u_retail[t - 1] } else { 0.0 },
                    d_driver,
                ]
            };

            let psi_pred = psi_prev;
            let p_pred = matrix_add_diag(p_prev, self.q_diag);
            let sigma_ewma = if t > 0 {
                stddev(&delta_p[t.saturating_sub(10)..=t])
            } else {
                sigma_hist
            };
            let r_eff = self.r_base * (sigma_hist / (sigma_ewma + self.eps)).powi(2);
            let denom = quad_form(&x_t, &p_pred) + r_eff + self.eps;
            let k_gain = matrix_vec_mul(&p_pred, &x_t).map(|value| value / denom);
            let y_adjusted = delta_p[t] - self.kappa_i * eps_prev;
            let innovation = y_adjusted - dot(&x_t, &psi_pred);
            let psi_update = add_vec(psi_pred, scale_vec(k_gain, innovation));
            let p_update = matrix_sub(p_pred, outer(k_gain, matrix_t_vec_mul(&p_pred, &x_t)));
            eps_prev = delta_p[t] - self.kappa_i * eps_prev - dot(&x_t, &psi_update);
            psi_filtered[t] = psi_update;
            cov_filtered[t] = p_update;
            psi_prev = psi_update;
            p_prev = p_update;
        }

        (psi_filtered, cov_filtered)
    }

    fn rts_backward_smooth(
        &self,
        psi_filtered: &[[f64; PID_DIM]],
        cov_filtered: &[[[f64; PID_DIM]; PID_DIM]],
    ) -> Vec<[f64; PID_DIM]> {
        if psi_filtered.is_empty() {
            return Vec::new();
        }
        let mut psi_smooth = vec![[0.0; PID_DIM]; psi_filtered.len()];
        psi_smooth[psi_filtered.len() - 1] = psi_filtered[psi_filtered.len() - 1];
        for t in (0..psi_filtered.len() - 1).rev() {
            let mut p_pred = matrix_add_diag(cov_filtered[t], self.q_diag);
            for (index, row) in p_pred.iter_mut().enumerate() {
                row[index] += self.eps;
            }
            let inv = invert_matrix(p_pred).unwrap_or_else(|| diag_matrix(1.0));
            let gain = matrix_mul(cov_filtered[t], inv);
            let delta = sub_vec(psi_smooth[t + 1], psi_filtered[t]);
            psi_smooth[t] = add_vec(psi_filtered[t], matrix_vec_mul(&gain, &delta));
        }
        psi_smooth
    }

    fn adaptive_normalize(&self, series: &[f64]) -> Vec<f64> {
        if series.is_empty() {
            return Vec::new();
        }
        let non_zero: Vec<f64> = series
            .iter()
            .copied()
            .filter(|value| value.abs() > self.eps)
            .collect();
        let mut scale = if non_zero.len() > 1 { stddev(&non_zero) } else { 0.0 };
        if scale < self.eps {
            scale = series
                .iter()
                .copied()
                .map(f64::abs)
                .fold(0.0, f64::max)
                .max(1.0);
        }
        series
            .iter()
            .map(|value| (value / (scale + self.eps)).clamp(-self.clip_limit, self.clip_limit))
            .collect()
    }

    fn determine_dominant(
        &self,
        capital_ch: &[f64],
        capital_q: &[f64],
        capital_retail: &[f64],
    ) -> DominantInfo {
        let mut hot = 0usize;
        let mut quant = 0usize;
        let mut retail = 0usize;
        for i in 0..capital_ch.len() {
            let hot_abs = capital_ch[i].abs();
            let quant_abs = capital_q[i].abs();
            let retail_abs = capital_retail[i].abs();
            let key = if hot_abs >= quant_abs && hot_abs >= retail_abs {
                "hot_money"
            } else if quant_abs >= retail_abs {
                "quant"
            } else {
                "retail"
            };
            match key {
                "hot_money" => hot += 1,
                "quant" => quant += 1,
                _ => retail += 1,
            }
        }
        let total = (hot + quant + retail) as f64 + self.eps;
        let hot_ratio = hot as f64 / total;
        let quant_ratio = quant as f64 / total;
        let retail_ratio = retail as f64 / total;
        let dominant_key = if hot_ratio >= quant_ratio && hot_ratio >= retail_ratio {
            "hot_money"
        } else if quant_ratio >= retail_ratio {
            "quant"
        } else {
            "retail"
        };
        let dominant_value = match dominant_key {
            "hot_money" => *capital_ch.last().unwrap_or(&0.0),
            "quant" => *capital_q.last().unwrap_or(&0.0),
            _ => *capital_retail.last().unwrap_or(&0.0),
        };
        let (dominant_type, dominant_value) = if self.mode_name == "baseline_4d" {
            if hot_ratio >= self.baseline_4d_hot_money_dominant_threshold
                && hot_ratio >= quant_ratio.max(retail_ratio)
            {
                ("游资", *capital_ch.last().unwrap_or(&0.0))
            } else {
                (
                    "unknown",
                    capital_ch.last().copied().unwrap_or(0.0)
                        + capital_q.last().copied().unwrap_or(0.0)
                        + capital_retail.last().copied().unwrap_or(0.0),
                )
            }
        } else {
            (
                match dominant_key {
                    "hot_money" => "游资",
                    "quant" => "量化",
                    _ => "散户",
                },
                dominant_value,
            )
        };
        DominantInfo {
            hot_money_ratio: hot_ratio,
            quant_ratio,
            retail_ratio,
            dominant_type: dominant_type.to_string(),
            dominant_intention: if dominant_value > 0.0 {
                "买入"
            } else if dominant_value < 0.0 {
                "卖出"
            } else {
                "中性"
            }
            .to_string(),
        }
    }

    fn check_convergence(&self, psi_filtered: &[[f64; PID_DIM]], mode_name: &str) -> bool {
        if psi_filtered.len() < self.convergence_window {
            return false;
        }
        let start = psi_filtered.len() - self.convergence_window;
        let mut max_diff: f64 = 0.0;
        let state_dim = if mode_name == "baseline_4d" { 4 } else { PID_DIM };
        for i in start + 1..psi_filtered.len() {
            for j in 0..state_dim {
                let diff = (psi_filtered[i][j] - psi_filtered[i - 1][j]).abs();
                max_diff = max_diff.max(diff);
            }
        }
        max_diff < self.convergence_tol
    }
}

struct DecomposeInput {
    delta_p: Vec<f64>,
    u_ch: Vec<f64>,
    u_q: Vec<f64>,
    u_retail: Vec<f64>,
    u_mix: Vec<f64>,
    price_basis: Vec<f64>,
    u_ch_amount_ratio: Vec<f64>,
    u_q_amount_ratio: Vec<f64>,
    u_retail_amount_ratio: Vec<f64>,
    u_mix_amount_ratio: Vec<f64>,
    ch_anchor: Vec<f64>,
    mix_qr: Vec<f64>,
}

struct DominantInfo {
    hot_money_ratio: f64,
    quant_ratio: f64,
    retail_ratio: f64,
    dominant_type: String,
    dominant_intention: String,
}

fn normalized_mode(raw_mode: &str) -> &str {
    match raw_mode.trim() {
        "baseline_4d" => "baseline_4d",
        "diag_5d" => "diag_5d",
        "full_5d" => "full_5d",
        "rule_base" => "baseline_4d",
        _ => "baseline_4d",
    }
}

fn get_map(config: &ConfigMap, key: &str) -> ConfigMap {
    config
        .get(key)
        .and_then(|value| match value {
            Value::Mapping(map) => Some(
                map.iter()
                    .filter_map(|(k, v)| match k {
                        Value::String(name) => Some((name.clone(), v.clone())),
                        _ => None,
                    })
                    .collect(),
            ),
            _ => None,
        })
        .unwrap_or_default()
}

fn get_f64(config: &ConfigMap, key: &str, default: f64) -> f64 {
    config.get(key).and_then(Value::as_f64).unwrap_or(default)
}

fn get_string(config: &ConfigMap, key: &str, default: &str) -> Option<String> {
    config
        .get(key)
        .and_then(Value::as_str)
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| {
            if default.is_empty() {
                None
            } else {
                Some(default.to_string())
            }
        })
}

fn get_f64_list(config: &ConfigMap, key: &str) -> Vec<f64> {
    config
        .get(key)
        .and_then(|value| value.as_sequence())
        .map(|items| items.iter().filter_map(Value::as_f64).collect())
        .unwrap_or_default()
}

fn parse_any(row: &HashMap<String, String>, keys: &[&str]) -> Option<f64> {
    keys.iter()
        .find_map(|key| row.get(*key))
        .and_then(|value| value.parse::<f64>().ok())
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn stddev(values: &[f64]) -> f64 {
    if values.len() <= 1 {
        return 0.0;
    }
    let avg = mean(values);
    let variance = values.iter().map(|value| (value - avg).powi(2)).sum::<f64>() / values.len() as f64;
    variance.sqrt()
}

fn max_abs_diff(left: &[f64], right: &[f64]) -> f64 {
    left.iter()
        .zip(right.iter())
        .map(|(a, b)| (a - b).abs())
        .fold(0.0, f64::max)
}

fn dot(left: &[f64; PID_DIM], right: &[f64; PID_DIM]) -> f64 {
    (0..PID_DIM).map(|i| left[i] * right[i]).sum()
}

fn add_vec(left: [f64; PID_DIM], right: [f64; PID_DIM]) -> [f64; PID_DIM] {
    let mut out = [0.0; PID_DIM];
    for i in 0..PID_DIM {
        out[i] = left[i] + right[i];
    }
    out
}

fn sub_vec(left: [f64; PID_DIM], right: [f64; PID_DIM]) -> [f64; PID_DIM] {
    let mut out = [0.0; PID_DIM];
    for i in 0..PID_DIM {
        out[i] = left[i] - right[i];
    }
    out
}

fn scale_vec(vector: [f64; PID_DIM], scalar: f64) -> [f64; PID_DIM] {
    let mut out = [0.0; PID_DIM];
    for i in 0..PID_DIM {
        out[i] = vector[i] * scalar;
    }
    out
}

fn diag_matrix(value: f64) -> [[f64; PID_DIM]; PID_DIM] {
    let mut out = [[0.0; PID_DIM]; PID_DIM];
    for (i, row) in out.iter_mut().enumerate() {
        row[i] = value;
    }
    out
}

fn matrix_add_diag(
    mut matrix: [[f64; PID_DIM]; PID_DIM],
    diag: [f64; PID_DIM],
) -> [[f64; PID_DIM]; PID_DIM] {
    for i in 0..PID_DIM {
        matrix[i][i] += diag[i];
    }
    matrix
}

fn matrix_sub(
    left: [[f64; PID_DIM]; PID_DIM],
    right: [[f64; PID_DIM]; PID_DIM],
) -> [[f64; PID_DIM]; PID_DIM] {
    let mut out = [[0.0; PID_DIM]; PID_DIM];
    for i in 0..PID_DIM {
        for j in 0..PID_DIM {
            out[i][j] = left[i][j] - right[i][j];
        }
    }
    out
}

fn matrix_vec_mul(
    matrix: &[[f64; PID_DIM]; PID_DIM],
    vector: &[f64; PID_DIM],
) -> [f64; PID_DIM] {
    let mut out = [0.0; PID_DIM];
    for i in 0..PID_DIM {
        out[i] = (0..PID_DIM).map(|j| matrix[i][j] * vector[j]).sum();
    }
    out
}

fn matrix_t_vec_mul(
    matrix: &[[f64; PID_DIM]; PID_DIM],
    vector: &[f64; PID_DIM],
) -> [f64; PID_DIM] {
    let mut out = [0.0; PID_DIM];
    for j in 0..PID_DIM {
        out[j] = (0..PID_DIM).map(|i| matrix[i][j] * vector[i]).sum();
    }
    out
}

fn quad_form(vector: &[f64; PID_DIM], matrix: &[[f64; PID_DIM]; PID_DIM]) -> f64 {
    dot(vector, &matrix_vec_mul(matrix, vector))
}

fn outer(left: [f64; PID_DIM], right: [f64; PID_DIM]) -> [[f64; PID_DIM]; PID_DIM] {
    let mut out = [[0.0; PID_DIM]; PID_DIM];
    for i in 0..PID_DIM {
        for j in 0..PID_DIM {
            out[i][j] = left[i] * right[j];
        }
    }
    out
}

fn matrix_mul(
    left: [[f64; PID_DIM]; PID_DIM],
    right: [[f64; PID_DIM]; PID_DIM],
) -> [[f64; PID_DIM]; PID_DIM] {
    let mut out = [[0.0; PID_DIM]; PID_DIM];
    for i in 0..PID_DIM {
        for j in 0..PID_DIM {
            out[i][j] = (0..PID_DIM).map(|k| left[i][k] * right[k][j]).sum();
        }
    }
    out
}

fn invert_matrix(matrix: [[f64; PID_DIM]; PID_DIM]) -> Option<[[f64; PID_DIM]; PID_DIM]> {
    let mut a = [[0.0; PID_DIM * 2]; PID_DIM];
    for i in 0..PID_DIM {
        for j in 0..PID_DIM {
            a[i][j] = matrix[i][j];
        }
        a[i][i + PID_DIM] = 1.0;
    }

    for i in 0..PID_DIM {
        let mut pivot = i;
        for row in i + 1..PID_DIM {
            if a[row][i].abs() > a[pivot][i].abs() {
                pivot = row;
            }
        }
        if a[pivot][i].abs() < 1e-12 {
            return None;
        }
        if pivot != i {
            a.swap(i, pivot);
        }
        let div = a[i][i];
        for col in 0..PID_DIM * 2 {
            a[i][col] /= div;
        }
        for row in 0..PID_DIM {
            if row == i {
                continue;
            }
            let factor = a[row][i];
            for col in 0..PID_DIM * 2 {
                a[row][col] -= factor * a[i][col];
            }
        }
    }

    let mut out = [[0.0; PID_DIM]; PID_DIM];
    for i in 0..PID_DIM {
        for j in 0..PID_DIM {
            out[i][j] = a[i][j + PID_DIM];
        }
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn baseline_4d_mixed_pool_stays_unknown_without_hot_money_dominance() {
        let decomposer = PIDDecomposer::new(&HashMap::new());

        let dominant = decomposer.determine_dominant(&[0.0, 0.1, 0.0], &[0.0, 0.4, 0.3], &[0.0, 0.2, 0.1]);

        assert_eq!(dominant.dominant_type, "unknown");
        assert_eq!(dominant.dominant_intention, "买入");
    }
}

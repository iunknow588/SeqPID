# -*- coding: utf-8 -*-

import pandas as pd

from adata.stock.market.daily_market_view import DailyMarketViewBuilder, normalize_stock_code, strip_exchange_suffix


class FakeMarketClient:
    def list_market_current(self, code_list=None):
        return pd.DataFrame(
            [
                {
                    "stock_code": "000001",
                    "short_name": "平安银行",
                    "price": 10.5,
                    "change_pct": 1.2,
                }
            ]
        )

    def get_market_min(self, stock_code="000001"):
        return pd.DataFrame([{"trade_time": "09:31", "price": 10.4, "volume": 1000}])

    def get_market_five(self, stock_code="000001"):
        return pd.DataFrame([{"b1": 10.49, "bv1": 100, "s1": 10.5, "sv1": 80}])

    def get_market_bar(self, stock_code="000001"):
        return pd.DataFrame([{"trade_time": "09:31:03", "price": 10.5, "volume": 200, "bs_type": "B"}])


def test_code_normalization():
    assert normalize_stock_code("1") == "000001.SZ"
    assert normalize_stock_code("600000") == "600000.SH"
    assert strip_exchange_suffix("000001.SZ") == "000001"


def test_build_stock_view_reads_model_outputs(tmp_path):
    (tmp_path / "pattern_reco.csv").write_text(
        "stock_code,transaction_date,pattern_type,pattern_explanation\n"
        "000001.SZ,20260715,尾盘突袭,14:30后集中拉升\n",
        encoding="utf-8",
    )
    (tmp_path / "predict_result.csv").write_text(
        "stock_code,transaction_date,capital_type,capital_intention\n"
        "000001.SZ,20260715,游资,买入\n",
        encoding="utf-8",
    )
    (tmp_path / "pid_window_flow_rows.csv").write_text(
        "stock_code,transaction_date,window_id,capital_q\n"
        "000001.SZ,20260715,1,0.8\n",
        encoding="utf-8",
    )

    builder = DailyMarketViewBuilder(model_output_dir=tmp_path, market_client=FakeMarketClient())
    view = builder.build_stock_view("000001", trade_date="20260715")

    assert view["stock_code"] == "000001.SZ"
    assert view["snapshot"]["short_name"] == "平安银行"
    assert view["model_result"]["pattern_type"] == "尾盘突袭"
    assert view["model_result"]["capital_type"] == "游资"
    assert view["window_flows"][0]["capital_q"] == 0.8


def test_build_model_summary(tmp_path):
    (tmp_path / "pattern_reco.csv").write_text(
        "stock_code,transaction_date,pattern_type,pattern_explanation\n"
        "000001.SZ,20260715,尾盘突袭,14:30后集中拉升\n",
        encoding="utf-8",
    )
    (tmp_path / "predict_result.csv").write_text(
        "stock_code,transaction_date,capital_type,capital_intention\n"
        "000001.SZ,20260715,游资,买入\n",
        encoding="utf-8",
    )

    builder = DailyMarketViewBuilder(model_output_dir=tmp_path, market_client=FakeMarketClient())
    summary = builder.build_model_summary(trade_date="20260715")

    assert summary["stock_count"] == 1
    assert summary["pattern_distribution"] == {"尾盘突袭": 1}
    assert summary["capital_type_distribution"] == {"游资": 1}
    assert summary["capital_intention_distribution"] == {"买入": 1}

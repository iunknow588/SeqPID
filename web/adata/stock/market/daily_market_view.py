# -*- coding: utf-8 -*-
"""
Daily market view adapter.

This module combines same-day quote data and competition model outputs into
one structure that can be returned by an API or consumed by a frontend page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from adata.stock.market.stock_market import StockMarket


MODEL_FILE_NAMES = {
    "pattern": "pattern_reco.csv",
    "prediction": "predict_result.csv",
    "window_flow": "pid_window_flow_rows.csv",
    "window_diag": "pid_window_diag.csv",
    "tail_diag": "pid_tail_diagnostics.csv",
    "daily_diag": "pid_daily_diag.csv",
    "window_features": "window_feature_rows.csv",
    "label_distribution": "label_distribution.csv",
}


class DailyMarketViewBuilder:
    """Build page-ready same-day market views."""

    def __init__(self, model_output_dir: Optional[str | Path] = None, market_client: Optional[StockMarket] = None):
        self.model_output_dir = Path(model_output_dir) if model_output_dir else None
        self.market_client = market_client or StockMarket()
        self._csv_cache: Dict[str, pd.DataFrame] = {}

    def build_stock_view(
        self,
        stock_code: str,
        trade_date: Optional[str] = None,
        include_realtime: bool = True,
        include_detail: bool = True,
    ) -> Dict[str, Any]:
        """Return one stock's complete daily view."""
        normalized_code = normalize_stock_code(stock_code)
        return {
            "stock_code": normalized_code,
            "trade_date": trade_date,
            "snapshot": self._get_snapshot(normalized_code) if include_realtime else {},
            "minute_bars": self._get_minute_bars(normalized_code) if include_realtime and include_detail else [],
            "order_book": self._get_order_book(normalized_code) if include_realtime and include_detail else {},
            "trade_ticks": self._get_trade_ticks(normalized_code) if include_realtime and include_detail else [],
            "model_result": self._get_model_result(normalized_code, trade_date),
            "window_flows": self._get_window_rows("window_flow", normalized_code, trade_date),
            "diagnostics": self._get_diagnostics(normalized_code, trade_date),
        }

    def build_stock_list(
        self,
        code_list: Optional[Iterable[str]] = None,
        trade_date: Optional[str] = None,
        include_realtime: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return a compact table model for multiple stocks."""
        codes = list(code_list) if code_list else self._infer_codes(trade_date)
        normalized_codes = [normalize_stock_code(code) for code in codes]
        snapshot_map = self._get_snapshot_map(normalized_codes) if include_realtime and normalized_codes else {}

        rows = []
        for code in normalized_codes:
            model_result = self._get_model_result(code, trade_date)
            rows.append(
                {
                    "stock_code": code,
                    "trade_date": trade_date,
                    "snapshot": snapshot_map.get(code, {}),
                    "model_result": model_result,
                }
            )
        return rows

    def build_model_summary(self, trade_date: Optional[str] = None) -> Dict[str, Any]:
        """Return pattern/capital/intention distributions for the output directory."""
        pattern_df = self._filter_by_date(self._read_model_csv("pattern"), trade_date)
        prediction_df = self._filter_by_date(self._read_model_csv("prediction"), trade_date)
        return {
            "trade_date": trade_date,
            "stock_count": int(
                max(
                    pattern_df.get("stock_code", pd.Series(dtype=str)).nunique(),
                    prediction_df.get("stock_code", pd.Series(dtype=str)).nunique(),
                )
            ),
            "pattern_distribution": value_counts(pattern_df, "pattern_type"),
            "capital_type_distribution": value_counts(prediction_df, "capital_type"),
            "capital_intention_distribution": value_counts(prediction_df, "capital_intention"),
        }

    def _get_snapshot(self, stock_code: str) -> Dict[str, Any]:
        return self._get_snapshot_map([stock_code]).get(stock_code, {})

    def _get_snapshot_map(self, code_list: List[str]) -> Dict[str, Dict[str, Any]]:
        try:
            df = self.market_client.list_market_current(code_list=[strip_exchange_suffix(code) for code in code_list])
        except Exception as exc:  # pragma: no cover - network/provider failures are expected in UI mode.
            return {"_error": {"message": str(exc)}}
        records = dataframe_to_records(df)
        result = {}
        for record in records:
            code = normalize_stock_code(record.get("stock_code") or record.get("code") or "")
            if code:
                result[code] = record
                result[strip_exchange_suffix(code)] = record
        return {code: result.get(code) or result.get(strip_exchange_suffix(code), {}) for code in code_list}

    def _get_minute_bars(self, stock_code: str) -> List[Dict[str, Any]]:
        try:
            return dataframe_to_records(self.market_client.get_market_min(stock_code=strip_exchange_suffix(stock_code)))
        except Exception:
            return []

    def _get_order_book(self, stock_code: str) -> Dict[str, Any]:
        try:
            records = dataframe_to_records(self.market_client.get_market_five(stock_code=strip_exchange_suffix(stock_code)))
        except Exception:
            return {}
        return records[0] if records else {}

    def _get_trade_ticks(self, stock_code: str) -> List[Dict[str, Any]]:
        try:
            return dataframe_to_records(self.market_client.get_market_bar(stock_code=strip_exchange_suffix(stock_code)))
        except Exception:
            return []

    def _get_model_result(self, stock_code: str, trade_date: Optional[str]) -> Dict[str, Any]:
        pattern_row = first_matching_row(self._read_model_csv("pattern"), stock_code, trade_date)
        prediction_row = first_matching_row(self._read_model_csv("prediction"), stock_code, trade_date)
        return {
            "pattern_type": pattern_row.get("pattern_type", ""),
            "pattern_explanation": pattern_row.get("pattern_explanation", ""),
            "capital_type": prediction_row.get("capital_type", ""),
            "capital_intention": prediction_row.get("capital_intention", ""),
        }

    def _get_window_rows(self, file_key: str, stock_code: str, trade_date: Optional[str]) -> List[Dict[str, Any]]:
        df = matching_rows(self._read_model_csv(file_key), stock_code, trade_date)
        return dataframe_to_records(df)

    def _get_diagnostics(self, stock_code: str, trade_date: Optional[str]) -> Dict[str, Any]:
        diagnostics = {}
        for file_key in ("window_diag", "tail_diag", "daily_diag", "window_features"):
            rows = self._get_window_rows(file_key, stock_code, trade_date)
            if rows:
                diagnostics[file_key] = rows
        return diagnostics

    def _infer_codes(self, trade_date: Optional[str]) -> List[str]:
        frames = [self._read_model_csv("prediction"), self._read_model_csv("pattern")]
        for df in frames:
            df = self._filter_by_date(df, trade_date)
            if not df.empty and "stock_code" in df.columns:
                return [normalize_stock_code(code) for code in df["stock_code"].dropna().astype(str).unique().tolist()]
        return []

    def _filter_by_date(self, df: pd.DataFrame, trade_date: Optional[str]) -> pd.DataFrame:
        if df.empty or not trade_date or "transaction_date" not in df.columns:
            return df
        return df[df["transaction_date"].astype(str) == str(trade_date)]

    def _read_model_csv(self, file_key: str) -> pd.DataFrame:
        if file_key in self._csv_cache:
            return self._csv_cache[file_key]
        if not self.model_output_dir:
            df = pd.DataFrame()
        else:
            path = self.model_output_dir / MODEL_FILE_NAMES[file_key]
            df = read_csv_if_exists(path)
        self._csv_cache[file_key] = df
        return df


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def matching_rows(df: pd.DataFrame, stock_code: str, trade_date: Optional[str]) -> pd.DataFrame:
    if df.empty or "stock_code" not in df.columns:
        return pd.DataFrame()
    code = normalize_stock_code(stock_code)
    code_no_suffix = strip_exchange_suffix(code)
    code_series = df["stock_code"].astype(str).map(normalize_stock_code)
    mask = (code_series == code) | (code_series.map(strip_exchange_suffix) == code_no_suffix)
    if trade_date and "transaction_date" in df.columns:
        mask = mask & (df["transaction_date"].astype(str) == str(trade_date))
    return df[mask]


def first_matching_row(df: pd.DataFrame, stock_code: str, trade_date: Optional[str]) -> Dict[str, Any]:
    rows = matching_rows(df, stock_code, trade_date)
    if rows.empty:
        return {}
    return dataframe_to_records(rows.head(1))[0]


def dataframe_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean_df = df.where(pd.notnull(df), None)
    return clean_df.to_dict(orient="records")


def value_counts(df: pd.DataFrame, column: str) -> Dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    counts = df[column].fillna("").astype(str).value_counts()
    return {key: int(value) for key, value in counts.items() if key}


def normalize_stock_code(stock_code: Any) -> str:
    code = str(stock_code).strip().upper()
    if not code:
        return ""
    if "." in code:
        left, right = code.split(".", 1)
        return f"{left.zfill(6)}.{right}"
    if code.startswith(("6", "9")):
        return f"{code.zfill(6)}.SH"
    return f"{code.zfill(6)}.SZ"


def strip_exchange_suffix(stock_code: str) -> str:
    return str(stock_code).split(".", 1)[0].zfill(6)

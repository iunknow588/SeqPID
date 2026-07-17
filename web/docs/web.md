# web 包说明

`web` 目录是 A 股行情数据 Python 包，不是现成前端页面。

## 已有能力

- 行情快照
- 分时行情
- 五档盘口
- 分时成交

## 新增能力

新增了当日行情聚合模块：

- `adata.stock.market.daily_market_view.DailyMarketViewBuilder`

它可以把行情接口和比赛输出 CSV 合并为统一视图，适合后续接：

- FastAPI 接口
- Streamlit 页面
- 内部分析工具

## 推荐用法

```python
from adata.stock.market.daily_market_view import DailyMarketViewBuilder

builder = DailyMarketViewBuilder(
    model_output_dir=r"C:\level-2-ana\output\20260715_20260717_130353"
)

view = builder.build_stock_view("000001.SZ", trade_date="20260715")
summary = builder.build_model_summary(trade_date="20260715")
```

## 返回内容

- `snapshot`
- `minute_bars`
- `order_book`
- `trade_ticks`
- `model_result`
- `window_flows`
- `diagnostics`

## 下一步

如果要做可视化页面，建议先把 API 固定为统一 JSON，再接前端。

# 当日行情数据展示设计

## 1. 当前定位

`web` 目录当前不是完整前端应用，而是行情数据 Python 包。它已经具备以下行情能力：

- `list_market_current(code_list)`：多股票当日行情快照。
- `get_market_min(stock_code)`：单股票当日分时行情。
- `get_market_five(stock_code)`：单股票五档盘口。
- `get_market_bar(stock_code)`：单股票分时成交。

因此，当日行情展示应先建设“数据聚合层”，再接入 Web API 或前端页面。

## 2. 已新增聚合模块

新增模块：

```text
adata.stock.market.daily_market_view.DailyMarketViewBuilder
```

它负责把两类数据合并成统一视图：

- 行情数据：快照、分时、盘口、成交。
- 比赛输出：`pattern_reco.csv`、`predict_result.csv`、`pid_window_flow_rows.csv`、诊断 CSV。

入口方式：

```python
from adata.stock.market.daily_market_view import DailyMarketViewBuilder

builder = DailyMarketViewBuilder(
    model_output_dir=r"C:\level-2-ana\output\20260715_20260717_130353"
)

view = builder.build_stock_view("000001.SZ", trade_date="20260715")
summary = builder.build_model_summary(trade_date="20260715")
```

也可以通过原有入口调用：

```python
import adata

builder = adata.stock.market.daily_view(
    r"C:\level-2-ana\output\20260715_20260717_130353"
)
view = builder.build_stock_view("000001.SZ", trade_date="20260715")
```

## 3. 单股票展示结构

`build_stock_view()` 返回结构：

```json
{
  "stock_code": "000001.SZ",
  "trade_date": "20260715",
  "snapshot": {},
  "minute_bars": [],
  "order_book": {},
  "trade_ticks": [],
  "model_result": {
    "pattern_type": "",
    "pattern_explanation": "",
    "capital_type": "",
    "capital_intention": ""
  },
  "window_flows": [],
  "diagnostics": {}
}
```

页面展示建议：

- 顶部：股票代码、简称、最新价、涨跌幅、成交量、成交额。
- 中部：分时价格线、均价线、成交量柱。
- 右侧：五档盘口、分时成交。
- 底部：模式识别、资金类型、买卖方向、5 分钟窗口资金流。

## 4. 多股票总览结构

`build_stock_list()` 用于 100 股总览表：

```python
rows = builder.build_stock_list(trade_date="20260715")
```

每一行包含：

- `stock_code`
- `snapshot`
- `model_result`

适合用于列表展示、排序和筛选。

## 5. 模型分布统计

`build_model_summary()` 返回：

- 模式分布：`pattern_distribution`
- 资金类型分布：`capital_type_distribution`
- 买卖意图分布：`capital_intention_distribution`

这些统计适合放在行情总览页顶部，快速展示当日盘面结构。

## 6. 后续 Web 展示建议

建议 API 设计：

- `GET /api/trade-dates`
- `GET /api/stocks?date=20260715`
- `GET /api/stocks/{stock_code}/daily?date=20260715`
- `GET /api/model/summary?date=20260715`

建议页面设计：

- 总览页：100 股表格 + 模式/资金类型分布。
- 个股页：分时图 + 盘口 + 成交明细 + 模型解释。
- 图上标注：把 `pattern_type`、`capital_intention`、`window_flows` 映射到分时图中的时间窗口。

## 7. 当前完成度

已经完成：

- GitHub 信息清理。
- 当日行情展示数据结构设计。
- Python 聚合模块实现。
- CSV 输出读取与股票代码归一化。
- 单股票视图、多股票列表、模型分布统计。
- 单元测试覆盖核心合并逻辑。

下一步可以继续做 FastAPI 接口或前端页面。

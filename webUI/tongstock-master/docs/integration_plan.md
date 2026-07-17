# 行情展示整合方案

## 目标

把当前前端与 `自动化交易/web` 中的行情聚合层合并，形成一个完整的行情展示页面。

## 分工

### Python 侧

- 拉取当日行情
- 汇总分时、盘口、成交
- 读取 `pattern_reco.csv`、`predict_result.csv`、`pid_*` 结果
- 输出统一 JSON

### 前端侧

- 展示行情总览
- 展示单股详情
- 展示信号解释和资金类型
- 展示模型结果摘要

## 建议接口

- `GET /api/stocks`
- `GET /api/stocks/{code}/daily`
- `GET /api/model/summary`
- `GET /api/trade-dates`

## 页面结构

- 总览页：股票列表、涨跌分布、模式分布
- 详情页：分时图、盘口、成交、信号卡片
- 解释区：模式类型、资金类型、意图标签

## 合并顺序

1. 固定统一 JSON 数据结构
2. 接入 Python 聚合层
3. 用前端页面消费该 JSON
4. 再做图表联动和筛选

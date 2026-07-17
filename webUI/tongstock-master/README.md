# TongStock 行情前端

这是一个 React + TypeScript + Vite 前端项目，适合作为行情展示页面的基础壳子。

## 当前定位

- 展示当日行情
- 展示个股分时、盘口、成交
- 展示技术指标和信号解释
- 预留和外部行情数据层的对接接口

## 建议对接方式

后续可以把它和 `自动化交易/web` 中的行情聚合层合并：

- Python 侧负责抓取行情、比赛输出、模型结论
- 前端侧负责展示图表、表格、解释卡片

## 本地开发

进入 `web` 目录后运行：

```bash
npm install
npm run dev
```

默认会启动前端开发服务。

## 目录说明

- `web/src/pages`：页面
- `web/src/components`：通用组件
- `web/src/components/charts`：图表组件
- `web/src/api`：接口层
- `web/src/types`：类型定义

## 下一步

建议优先补一层统一行情 JSON 接口，再把这个前端接进去，形成完整的行情展示闭环。

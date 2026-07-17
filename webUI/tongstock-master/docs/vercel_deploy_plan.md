# Vercel 部署方案

## 结论

可以部署，但建议采用“前端上 Vercel，后端独立部署”的方案。

原因：

- `web` 是标准 Vite 前端，适合 Vercel。
- Go 后端当前是常驻服务，带本地状态和缓存，更适合独立部署。
- 前端已经支持通过 `VITE_API_BASE` 配置后端地址。

## 推荐架构

```text
Vercel
  └─ tongstock-web (React + Vite)

独立后端
  └─ tongstock API / 你项目里的行情聚合服务
```

## 前端部署流程

1. 在 Vercel 创建新项目。
2. 选择 `web` 目录作为 Root Directory。
3. 构建命令使用默认值：
   - `npm run build`
4. 输出目录使用默认值：
   - `dist`
5. 配置环境变量：
   - `VITE_API_BASE=https://your-api-domain`
6. 部署后验证：
   - 首页能打开
   - 刷新子路由不 404
   - `/api` 请求能正确指向后端

## 后端部署流程

### 方案 A：独立服务器

1. 保持 Go 服务独立运行。
2. 让前端通过 `VITE_API_BASE` 调用它。
3. 对外提供 CORS 或同域代理。

### 方案 B：函数化改造后上 Vercel

1. 把 API 拆成无状态函数。
2. 去掉本地持久化依赖。
3. 用外部存储替换 SQLite/本地缓存。
4. 再迁移到 Vercel Functions。

## 当前代码需要注意的点

- `web/src/api/client.ts` 已改为读取 `VITE_API_BASE`
- `web/vercel.json` 已加入 SPA rewrite
- 如果后端仍在本地，请不要把 `VITE_API_BASE` 留空

## 建议的上线顺序

1. 先把前端部署到 Vercel。
2. 再把行情 JSON 接口稳定下来。
3. 最后把行情总览、个股详情、模型解释接入统一页面。

## 适合的最终形态

- Vercel：展示层
- Python 聚合层：行情与模型数据层
- Go/TongStock：实时行情和 K 线服务层

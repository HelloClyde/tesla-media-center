# Tesla Owner API 实现对比

本文对比当前项目与 `TeslaMate` 在 Tesla `Owner API` 链路上的实现差异，重点覆盖 token 存储、refresh、区域判定、接口选择和失败处理。

对比基准：

- 当前项目：本仓库当前工作区中的 [`ffvideo/tesla.py`](/root/tesla-media-center/ffvideo/tesla.py)
- `TeslaMate`：本地临时拉取到 `/tmp/teslamate`
  - [`/tmp/teslamate/lib/teslamate/api.ex`](/tmp/teslamate/lib/teslamate/api.ex)
  - [`/tmp/teslamate/lib/tesla_api/auth.ex`](/tmp/teslamate/lib/tesla_api/auth.ex)
  - [`/tmp/teslamate/lib/tesla_api/auth/refresh.ex`](/tmp/teslamate/lib/tesla_api/auth/refresh.ex)
  - [`/tmp/teslamate/lib/tesla_api/vehicle.ex`](/tmp/teslamate/lib/tesla_api/vehicle.ex)

## 总览

| 维度 | 当前项目 | TeslaMate | 当前状态判断 |
| --- | --- | --- | --- |
| token 存储 | 保存在 `config.json` | 保存在数据库 `tokens` 表 | 不同实现，功能等价 |
| access token 恢复 | 启动后按请求时惰性 refresh | 启动时先恢复 token，再尝试 refresh | 我们较简化 |
| refresh 触发方式 | 每次需要时按过期时间 refresh；401 后再强制 refresh | 启动恢复时 refresh；定时器按 `expires_in * 0.75` refresh；401 时触发 refresh 流 | TeslaMate 更完整 |
| refresh 请求体 | `grant_type + scope + client_id + refresh_token`，JSON | 同字段，JSON | 已对齐 |
| refresh issuer 选择 | 优先从 access token 的 `iss` 推导，否则回退默认 auth host/path | 同逻辑 | 已基本对齐 |
| 默认 auth host/path | 由 token issuer 决定，回退到默认 | `TESLA_AUTH_HOST + TESLA_AUTH_PATH`，未配置时也会从 token issuer 推导 | 已基本对齐 |
| 区域判定 | 从 access token issuer 的 host 顶级域判断 `cn/com` | `Auth.region(auth)` 也是从 issuer host 顶级域判断 | 已对齐 |
| API Host 选择 | 根据 region 自动选 `owner-api.vn.cloud.tesla.cn` 或 `owner-api.teslamotors.com` | 同逻辑 | 已对齐 |
| 车辆列表接口 | `/api/1/products` | `/api/1/products` | 已对齐 |
| 单车状态接口 | 先通过 `products` 找 `id`，再请求 `/api/1/vehicles/{id}/vehicle_data` | 同逻辑 | 已对齐 |
| refresh 失败处理 | 当前返回错误给前端，保留旧 access token，但授权状态读取仍可能失败 | refresh 失败时保留旧 token，记录 warning，5 分钟后继续重试 | 我们还不够像 |
| unauthorized 熔断 | 没有 | 有 `fuse` 熔断与重试控制 | 我们未实现 |
| 流式 telemetry / websocket | 未实现 | 有 streaming 集成 | 不在当前范围 |

## 关键链路逐项对比

| 主题 | 当前项目 | TeslaMate | 备注 |
| --- | --- | --- | --- |
| token 持久化字段 | `tesla_access_token` / `tesla_refresh_token` in `config.json` | `access` / `refresh` in DB | 只是存储位置不同 |
| refresh client id | `ownerapi` | `ownerapi` | 对齐 |
| refresh scope | `openid email offline_access` | `openid email offline_access` | 对齐 |
| access token issuer 解析 | `decode_jwt_payload(token)['iss']` | `decode_jwt_payload(token)['iss']` | 对齐 |
| 特殊 OAT 前缀 | 支持 `qts- / eu- / cn-` 回退默认 auth host/path | 同样支持 | 对齐 |
| China region API Host | `https://owner-api.vn.cloud.tesla.cn` | `https://owner-api.vn.cloud.tesla.cn` | 对齐 |
| Global region API Host | `https://owner-api.teslamotors.com` | `https://owner-api.teslamotors.com` | 对齐 |
| China token refresh 实测 | 现有 token 打到 `https://auth.tesla.cn/oauth2/v3/token` 返回 `400 server_error` | 未在本地直接跑 TeslaMate，但其代码会走同一 issuer 推导逻辑 | 现有 blocker 不像是本地 URL 拼错 |
| 授权状态接口 | `/api/tesla/auth/status` 内部调用 `/api/1/users/me` | 没有同名接口，通常通过内部 auth 状态和 API 调用间接体现 | 当前项目额外封装了前端友好层 |
| 401 后行为 | 返回 `not_authorized` 给前端 | 熔断器控制后触发 refresh，严重时删除 auth | TeslaMate 更鲁棒 |

## 当前项目已经对齐到 TeslaMate 的部分

| 项目 | 状态 |
| --- | --- |
| refresh 请求改为 JSON body | 已对齐 |
| refresh 带 `scope=openid email offline_access` | 已对齐 |
| issuer 优先从 access token 的 `iss` 推导 | 已对齐 |
| region 根据 issuer 顶级域推导 `cn/com` | 已对齐 |
| API Host 根据 region 自动切换 | 已对齐 |
| 车辆列表从 `/api/1/products` 获取 | 已对齐 |
| `vehicle_data` 通过 `id` 请求而不是直接拿 `vin` | 已对齐 |

## 当前项目仍未完全对齐的部分

| 项目 | 当前项目 | TeslaMate |
| --- | --- | --- |
| 启动恢复 token | 请求时惰性恢复 | 启动时就恢复并安排定时 refresh |
| 定时 refresh | 没有独立后台调度 | `expires_in * 0.75` 后自动 refresh |
| refresh 失败重试 | 当前主要向前端报错 | 失败后 5 分钟重试 |
| unauthorized 熔断 | 无 | 有 `fuse` 熔断 |
| auth 状态内存缓存 | 无 | ETS 缓存当前 auth |
| 错误分类 | 目前偏前端接口导向 | TeslaMate 更偏内部状态机导向 |

## 这次排查得出的关键结论

| 结论 | 说明 |
| --- | --- |
| 之前确实存在实现偏差 | 包括 refresh body 不是 JSON、issuer 推导不够像 TeslaMate |
| 这些偏差已经修正 | 当前主链路已明显更接近 TeslaMate |
| 当前剩余错误不是简单 endpoint 拼错 | 实测已经走到 `https://auth.tesla.cn/oauth2/v3/token` |
| 现有 token 在正确 issuer 上仍返回 `400 server_error` | 更像是 Tesla 远端对这组 token 的处理问题，或 token 来源/用途不匹配 |

## 建议下一步

| 优先级 | 建议 |
| --- | --- |
| 高 | 把 refresh 失败后的容错改成更像 TeslaMate：保留旧 token，延迟重试，不立刻判死 |
| 高 | 重启本地服务，用当前最新逻辑重新验证一次前端链路 |
| 中 | 补一个“本地解析 token claims”的前端调试面板，仅显示 `iss/aud/ou_code/exp` |
| 中 | 如需继续完全对齐 TeslaMate，再补后台定时 refresh 和 unauthorized 熔断 |

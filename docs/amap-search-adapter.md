# TMC 正式搜索适配说明

## 当前实现：官方 Web SDK 搜索

用户选择使用已有 Web JS API Key。导航页现在调用官方 JS API 1.4.15 的
`AMap.PlaceSearch.search`，不再请求尚未实现的 `/api/amap-app/search`。
地图绘制和路线规划仍使用原有实现。以下 App 静态分析保留为研究记录，
不是当前搜索运行时依赖。

在调试页“高德搜索与行程轨迹”配置 Web JS API Key；按 Key 要求填写配套
securityJsCode。安全密钥使用官方支持的客户端配置方式，会传给浏览器；
需要在高德控制台配置适用的域名权限。生产部署可按官方文档改为服务端代理保护安全密钥。
保存配置后下一次搜索会读取新配置，无需修改源码。

旧版 SDK 在同源隐藏 iframe 中加载，避免与特斯拉页面的其他 SDK 版本冲突。
仅用户提交时执行全国关键词搜索，首批最多 20 条；可在关键词中加入城市名。
不接输入联想、自动重试和分页。结果经 GCJ-02 坐标校验后交给既有选点算路流程。
取消、离开页面、成功、错误或超时均清理 iframe；消息校验来源窗口及同源条件。

验证：类型检查、7 项单元测试、真实浏览器中的模拟 SDK 成功/空结果/错误/取消测试。
本机真实调用检查发现尚未配置 Key，已正确显示配置提示；真实地点查询尚待用户配置后验证。

官方依据：
- https://developer.amap.com/api/javascript-api/reference/search
- https://developer.amap.com/api/javascript-api/guide/abc/prepare

2026-09-27，本地官方 APK 17.00.0.2005 的静态业务层分析。
本文不提供私有 HTTP 调用、签名、设备凭据或验证规避实现；没有发送网络请求。

## 已确认与证据边界

- `SearchBaseRequest.startKeywordSearch` 调用 `natives.keywordSearch.search`，通过回调返回结果；取消调用 `natives.keywordSearch.cancel`。
- `SearchBaseRequestParam.generateSearchKeywordParam` 构建关键词查询对象，分为业务参数与执行选项。它与 suggest 的 BaseSugRequest 不是同一个入口。
- 业务对象涉及关键词、查询类型、分页、地图范围以及位置上下文；还支持按 POI 标识查询和周边查询。
- `SearchResultDataSource` 保存请求、结果类型、首屏数据、历史和展示列表。列表中存在 `item_type`，代码有仅保留 `poi` 项的分支；不能将所有卡片作为地点处理。
- 上述可读资源来自 APK 内 poi 及共享业务模块。搜索主模块中许多文件为 `.js.wlm`，尚未证明当前首页搜索按钮的完整调用链，也未确定原生回调与最终展示对象之间的全部转换。
- 不能把展示层字段当作原始 HTTP 响应协议；没有正式搜索的成功响应样本，不能根据 suggest 的限制推断正式搜索必然受限。

本地证据位于忽略目录 `.local-data/amap-app/`：
`search-SearchBaseRequest.js`、`search-SearchBaseRequestParam.js`、
`search-SearchRequestConst.js`、`search-SearchResultDataSource.js`。

## 建议的 TMC 自有接口模型

以下为设计建议，不是对高德私有协议的复刻，也不是现有功能完成声明。

| 输入 | 用途与约束 |
| --- | --- |
| keyword | 用户明确提交的关键词；去除首尾空白，空值不发请求 |
| city | 可选城市标识；与当前位置分开保存 |
| center | 可选检索中心，带 longitude、latitude、coordinateSystem |
| bounds | 可选地图可视范围；注明坐标系，跨经度边界时需明确处理 |
| page / pageSize | 分页参数；限制由实际数据服务提供方决定 |
| requestId | 标识本轮查询；新查询后丢弃旧响应 |

建议结果包含 `items`、`page`、`hasMore`、`source`；未知总数和未知后续页状态应允许为空，不能从缺少字段推断已经没有结果。

每个地点至少具备 `id`、`name`、`location`；地址、城市、分类和距离为可选字段。
location 必须说明坐标系。距离未知显示为空，不能用 0 代替。
没有有效坐标的条目可以展示，但不得直接启动导航；应通过可用的数据服务补全详情。

## 页面流程

1. 输入文字只更新本地输入状态；本期不接 suggest。
2. 点击搜索或按回车后提交一次正式查询，同时取消上一轮请求或使其结果失效。
3. 展示地点列表及地图标记，选中地点后允许设为终点。
4. 加载下一页时保留关键词、城市和范围，按稳定地点 ID 去重。
5. 区分无结果、网络错误、服务限制、需要登录、服务不可用；只有明确的登录错误才能提示登录。
6. 服务限制出现时停止自动重试。离线数据或测试数据必须明确标记，不能冒充在线成功结果。

## 接入验收

- 正式搜索服务通过其受支持方式接入，并取得成功地点结果。
- 核实坐标系、分页、取消和过期响应处理。
- 验证地点选择可传入现有路线规划。
- 用测试数据覆盖非地点卡片、缺少坐标、空结果和错误状态；真实在线验收单独记录。

本轮仅完成业务结构与适配说明，未实现 TMC 搜索接口，也未验证正式搜索在线可用。

## 分页与结果进一步核对

`SearchResultDataSource.getNewSearchParam` 在已有请求对象上合并新参数，同时更新在线和离线参数，并清除部分旧查询关联状态。这是参数更新工具，不能单独证明下一页请求怎样发出、是否存在游标或如何判断末页。

`setSearchFristPageData` 有两种处理：结果类型为 0 时复制结果、截取 `poi_list` 的前 10 条，并将副本的 `total` 写成 10；其他类型仅在第一页保存结果。此处没有明确给出类型 0 的含义，不能擅自认定它代表在线或离线。
因此，展示对象里的 `total` 不能未经核对就作为服务端总数，首屏缓存也不能用来推断后续页是否存在。

## 与现有 TMC 的对照

已核对 `web/src/views/apps/AmapAppView.vue`、`ffvideo/amap_app.py`、`ffvideo/amap_map.py` 及 `tools/amap-app/tmc_route_helper.py`：

- 前端已经有点击/回车提交搜索、AbortController 取消、查询代次检查，输入变化时清除旧结果；没有输入即请求的 suggest 流程。
- 前端当前请求自有 `/api/amap-app/search`，提交关键词和位置，期望 `status: ok` 与 `data.places`。上述后端文件没有注册该搜索路由，不能把现有输入框描述为已接通搜索。
- 当前 Place 结构为 id、name、address、location，location 顺序为 `[经度, 纬度]`；目前没有逐项校验响应数据，也没有分页 UI。
- `selectPlace` → `setPoint` 已能更新起点或终点、清除旧路线并移动地图。随后由用户点击规划路线，向 `/api/amap-app/route` 提交起终点。
- 浏览器定位在前端从 WGS-84 转为 GCJ-02，路线 helper 的结果声明为 GCJ-02。搜索适配层应统一坐标到 GCJ-02 后才交给当前选点流程，避免重复转换；用户手输坐标的坐标系也应明确标注。

后续实现顺序：确定可用的数据服务与成功样本 → 增加地点规范化和校验 → 接入自有搜索路由 → 验证选点到算路 → 增加分页。不能先把缺少或无效坐标补成默认位置，也不能用空列表掩盖服务未接入或请求受限。

## 本地校验已实现

新增 `web/src/views/apps/amapSearch.ts` 并接入现有页面。自有成功响应现在要求
`data.coordinateSystem` 明确为 `GCJ-02`；适配服务负责提前完成必要转换。
校验器过滤非地点卡片、缺失标识/名称及无效坐标，并按地点 ID 去重。
有原始条目但全部不可导航时显示单独错误，不冒充零搜索结果。
缺少坐标系或未知坐标系直接报错，避免地图偏移和重复转换。

这只是本地响应校验，没有增加在线搜索路由或上游请求。

# TMC 正式搜索适配说明

## 2026-10-04：请求失败的解释边界

登录态复核：`NativesModuleKeywordSearch` 构造正式关键词请求时没有账号登录门槛；`NetworkParam.getNetworkParamMap` 仅在账号提供者返回非 `null` UID 时加入 `uid`。通用网络过滤器 `cc1` 会附带 Cookie，并仅在已有 `sessionid` Cookie 时附带同名请求头。`NetworkParam.getSession()` 则是应用进程生成的数值，不等同于高德账号会话。因而 TMC 的 `/api/login` 与高德账号都不能补出搜索请求缺失的 SecurityGuard V2 动态因子；不能把搜索未接通归因为“用户尚未登录”。

此前把 HTTP 200 的 HTML 结果称为“拦截页面”过于武断。与 APK 源码相比，
先前探针确实缺少 `NetworkParam.getNetworkParamMap` 的多数公共字段、
`getAosCommonParam` 的运行时请求头，且没有成功的原生搜索请求供逐字节核对。
因此“参数不等价”已经成立；但仅凭 HTML 结果，仍不能确定是哪个字段、
签名、设备上下文或服务端校验导致失败。

`search_request.audit_keyword_params` 现可单独列出 TQUERY 正式搜索正文中
缺失或与 APK 固定值不一致的字段；`audit_apk_context` 继续核对公共字段与
已确认的公共请求头。这两项检查通过也不代表请求等价：`geoobj`、
`user_loc`、`user_city` 等运行时值、可选公共字段、正文加密和
SecurityGuard 生成的请求头仍须用成功的原生请求对照。当前不应据此移除
TMC 正在使用的 Web JS Key 搜索。

继续核对实际网络适配层：`NativesModuleKeywordSearch` 用新版
`com.amap.network.api.http.request.AosRequest`，`p60.c` 将其
`RequestFormBody` 转成旧版 `AosPostRequest`；默认
`isCommonParamInQuery=false`，所以公共字段与搜索字段同在加密正文。
`AosRequest.paramsToString` 最终使用 `zv6.a`，它把 `null` 值编码为
只有键名、空字符串编码为 `键名=`。离线构造器现保留这一区别，避免
正文及其 V2 摘要出现确定的字节差异。先前 HTML 响应只证明探针
请求未成功，不能单独定位为哪个字段或签名失败。

进一步沿 `AosPostRequest.processParams` → `AosRequest.securityGuardSignByV2`
→ `uu5.f` 核对：默认 V2 分支传给安全组件的是**已加密的表单正文**，
安全输入 `data` 为 `appkey & MD5(加密正文) & 秒级时间戳`，另带原始 API
路径、环境和 `useWua`。此前只核对 AOS 的 `sign` 及表单字段，不能据此
声称动态请求头已一致。离线构造器新增 `virtual_v2_factors_input` 来复核
这一层输入；它不产出 `x-sign`、`x-mini-wua`、`x-umidtoken` 等实际请求头。
固定 APK 的配置中该签名开关和 V2 模式默认开启，运行时可能由云配置更改。
本机两个模拟器仍停在“操作过于频繁”的安全页，无法取得成功搜索响应作为
等价性样本；因此搜索继续保留现有 Web JS Key 路径。

固定 APK 的压缩包只包含 `arm64-v8a` 原生库，无法在现有 x86 Python
进程中直接加载 SecurityGuard。`audit_virtual_v2_headers` 单独检查默认
V2 分支成功签名时应出现的动态头（包括 `x-sign`、`x-t`、`x-appkey`、
`x-umidtoken`）；它不伪造头值，也不把头名齐全当成签名有效。

离线校验脚本 `python tools/amap-app/verify_search_body.py` 使用合成的地点、
位置及公共字段，经已提取的 `libserverkey.so` 字符串编码入口构造正式搜索
POST 正文，再经对应解码入口核对。当前样本是 66 个表单字段、1448 字节
编码正文，往返一致。它能发现本地序列化或编码回归，但不证明 APK 运行时
字段的真值、SecurityGuard 因子或服务端接受；脚本不发送请求。

同日做了两次无凭据、无重试的主机对照：向 `m5.amap.com` 的不存在路径
发送 GET 得到 404 空正文；向正式 `infolite` 路径发送空 POST 得到 HTTP
200、`text/html`，正文指向 `deny_pc.html`。这排除了“该主机所有路径
都返回相同页面”的简单解释，但空 POST 本身不是有效 APK 请求；此对照
既不能证明参数错误是唯一原因，也不能证明正确参数即可通过。两个已连接
研究实例的前台活动仍是 SecurityGuard 的 `ContainerActivity`，未提供可
逐字段核对的成功原生搜索请求。

TMC 现有的 `tmc_route_helper.py` 与 `tmc_map_helper.py` 只从 APK 材料中
读取 AOS `channel` 和签名所需材料，用于各自已验证的路线或地图请求；
它们没有生成搜索所需的设备、会话、位置等 `NetworkParam` 运行时值，
也没有搜索的 SecurityGuard V2 因子。因此不能把“路线接口可用”直接
当成“搜索接口已有同一套公共参数”。

APK 的 `g30` 给 `NetworkClient` 注册 `zg4` 过滤器。其 `by6` 分支在请求
缺少 User-Agent 时写入 `Android ` 加系统版本；`cc1` 分支还读取 App 的
Cookie，并在已有会话 Cookie 时附带 `sessionid`。`audit_apk_context` 现将
User-Agent 列入必查结构；Cookie 和 `sessionid` 的值依赖 App 运行时，
不能据静态代码编造。用当前研究实例的 Android 11 值，只改变空 POST 的
User-Agent 做一次对照，仍得到同样的 `deny_pc.html` 页面。因此 UA 缺失
是探针与 APK 的一项确定差异，却不是该空请求被拒的充分解释。

## 2026-10-03：APK 原生关键词搜索复核

固定版 APK 的 `SearchBaseRequest.startKeywordSearch` 调用 `natives.keywordSearch.search`。
`NativesModuleKeywordSearch` 将 `onlineParams` 交给 `AosRequest`：通常为 POST，
目标是 `ws/mapapi/poi/infolite`；当 `isNewPath=1` 时改为
`ws/shield/search_poi/search/sp`。它的签名字段为
`id, longitude, latitude, keywords, category, geoobj`。回调中的线上结果
保留原始 JSON，`InfoliteResponse` 定义了 `poi_list`、`code`、`total`，
`PoilistPoiInfo` 包含 `id`、`name`、`address`、`longitude`、`latitude` 和
`item_type` 等字段。这是**正式关键词搜索**，不是输入联想 `search/sug`。

早期 GET 与编码 POST 探针将部分公共参数和 `sign` 放在 URL 的 `in=`
参数中；静态复核 `p60.c` 与 `AosPostRequest.processParams` 后确认，
普通 `RequestFormBody` 且默认 `isCommonParamInQuery=false` 时，APK 会把
公共参数和业务参数合并，编码到 POST **请求体**，URL 仅附 `ent=2`、
`csid` 等参数。因此早期探针的格式确实不对，不能用来判断正式搜索
服务是否可移植。

按上述主体位置修正的一次 POST 仍返回 HTTP 200、HTML，而非地点 JSON。
它也不是完整的 APK 请求：`SearchBaseRequestParam` 默认附带地图范围
`geoobj`、位置 `user_loc`、行政区 `user_city` 和大量搜索选项，而本次
仅包含少量字段；`NetworkParam.getNetworkParamMap` 还会附加设备、版本、
会话等公共字段；非启动场景下 `AosRequest.securityGuardSign` 可能生成
`x-sign`、`x-mini-wua`、`x-pv` 等请求头。这些差异均未经过成功的
App 搜索样本比对。HTML 结果不能证明究竟是哪个字段、请求头、签名
或访问条件造成失败，也不能把 HTTP 200 解释为接口已打通。

进一步逐行对照固定 APK 的 `NetworkParam.getNetworkParamMap`，发现该方法
无条件写入 22 个公共键（值可能为空或由运行时提供）；此前只给探针传入
`channel`、`div` 等少量键。`getAosCommonParam` 另增加 `x-gen`、`Ap-Tid`
头；搜索使用 HTTPS，不能把只带 `Content-Type` 的探针当作等价请求。
`tools/amap-app/search_request.py` 现在提供 `audit_apk_context`，列出
缺失的公共键、头，以及在线参数覆盖公共参数的冲突。例如在线 `siv` 为空
而公共 `siv` 非空时，POST 合并顺序会让空值覆盖非空值。该检查只比较
结构，不能验证运行时字段的真值或 SecurityGuard 因子，也不能由此推断
服务端具体拒绝原因。`prepare_post` 允许注入实际采集的公共头以便本地
逐项对照；并未生成或伪造这些头。

`AosPostRequest.processParams` 将公共参数、业务参数放入新的 Java
`HashMap` 后才序列化加密；此前 Python 保留插入顺序，生成的明文 POST
字节与 APK 不同。请求构造器现在按 Java 字符串哈希和桶顺序排列键；
用独立 Java 11 `HashMap` 运行结果核对了碰撞键及一组 84 键搜索参数的顺序。
这只消除了一个确定的字节级差异：原生 `JSONObject.keys()` 的初始顺序、
实际公共值和 SecurityGuard 请求头仍没有成功 App 样本可对照。

APK 中还没有可直接供 Python 查询的全国离线 POI 数据库。当前 TMC
关键词搜索仍使用 Web JS API Key；取得原生成功响应并核对等价请求前，
不应切换到未验证的 Python 实现。

`tools/amap-app/search_request.py` 现单独还原了 APK 的 TQUERY 关键词
默认字段、`zv6` 表单转义、AOS 签名输入顺序，以及普通 FormBody POST
的参数位置。`test_search_request.py` 与既有签名测试已通过。该模块只
构造请求，不发送网络流量、不生成 SecurityGuard 请求头，也不接入
Flask 搜索路由；它是后续逐字段对照的基线，而非已可用的无 Key 搜索。

`tools/amap-app/search_response.py` 另按 APK 的 `InfoliteResponse` 和
`PoilistPoiInfo` 字段建立了有界的候选结果解析器：拒绝 HTML、非成功
状态和异常结构，仅保留带有效坐标的 POI。它目前只用合成样本测试；
坐标系与线上结果外层格式仍须用成功响应核对，不能据此上线。

APK 的 `PoilistPassageway` 保留入口经纬度，`AddressListHelper.formatSearchPoiToNative`
会把 `entrances` 转入路线 POI 的 `entranceList`，语音导航分支也优先使用第一个
有效入口。候选原生结果解析器现在单独保留首个有效入口；TMC 搜索合同也允许
返回可选入口坐标，选点后算路以入口为终点，地图仍展示 POI 中心。现有网页
SDK 只有在结果自带 `entrances` 时才会传递该字段；这不代表原生无 Key 搜索
已经接通，也不能据此推断网页 SDK 必定返回入口。

本机两个模拟器均安装了高德 App，但当前前台活动是
`com.alibaba.wireless.security.open.middletier.fc.ui.ContainerActivity`；
现存抓包仅有实时红绿灯事件，没有搜索成功样本。`uu5.f` 静态链路
通过 `SecurityGuardManager` 的 `IUnifiedSecurityComponent` 生成
安全因子；固定 APK 含相应原生库，但现有 Python 请求构造器并未移植
这一运行时组件。下一步仍需获取或复现一条能返回 POI JSON 的等价
请求，然后才能核对结果和接入 TMC。

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

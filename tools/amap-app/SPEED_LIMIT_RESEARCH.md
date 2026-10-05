# APK 限速事件数据源追踪

目标：把高德 APK 的道路限速牌、前方限速与超速语音迁移到仅有车机浏览器和 Python 后端的 TMC。不能把路况速度、绿波速度或道路等级当作法定限速。

## 已确认的事件路径

- AJX `TripNaviStateEyrieEventManager.registerSectionSpeedLimit` 订阅 `NaviEventTypeSpeedLimitSection`（452），读取 `Number(e.speed)`。正值立即更新 UI，0 延迟约 250 ms 清除。
- APK 的语音查询另走 `QueryGuideInfoTypeSpeedLimit`（8）：`SpeedLimitDirective` 读取原生查询结果的 `roadSpeedLimit`、`cameraSpeedLimit`、`distToCamera` 和 `carSpeed`，道路限速非正值时返回 `CODE_NO_SPEED_LIMIT`。这说明原版不会用当前路况速度代替未知限速；TMC 也必须保留“未知”的状态。
- 原版的**前方限速摄像头牌**不是 452 路段事件：`TripNaviStateEyrieEventManager` 另订阅 `NaviEventTypeShowNaviCameraExt`（95），缓存 `naviCamera[]`；HUD 的 `TripNaviCameraUtil.getIconViewData` 从每项 `type`、`speed[]`、`distance` 读取，过滤速度哨兵值 255 后取最大值。数字牌仅用于摄像头类型 7、25、26、27。必须把此事件与当前道路限速 452 区分；截图中的前方 80 牌不能由 452 的路段值直接证明。
- APK `libamaphorus.so` 包含 `GuideBridge::onSpeedLimitSection(const dice::tbt::drive::NaviSpeedLimitSectionEvent&)`、`NaviSpeedLimitSectionInfoData`、`component.sectionspeedlimit`。事件由原生导航引擎产生，浏览器无法直接订阅 APK 进程。
- APK 的 `com.autonavi.jni.ae.route.route.Route.getAllCamera()` 是 JNI 原生方法，返回 `RouteCamera[]`，包含 `cameraType`、`carSpeedLimit[]`、`distance`、`segmentIndex`、`linkIndex`、经纬度等字段。`libamaptbt.so` 注册表把它指向 `0x4a2e5c`，该函数从原生路线对象的虚方法读取每项约 `0xb8` 字节的摄像头记录，再复制速度数组和位置字段到 Java 对象。这证明摄像头详情可以存在于原生路线对象中，但还不能证明 5.1 网络响应的哪一字段、或哪一次增量请求填充这些记录。
- `getAllCamera()` 的 JNI 方法在 `0x4a2ea0` 调用 `0xcf7e5c` 获取运行时路线管理器；随后由路线对象的虚表 `+0x40` 取路线标识，调用管理器虚表 `+0x10` 输出 `0xb8` 字节摄像头记录数组。`0xcf7e5c` 使用 `0xf93658` 的缓存指针及 `0xf93660` 的运行时提供者，后者由 `0xcf81d8` 设置；在当前库内找到的 `0xcf81d8` 直接调用仅是清理时置空。因此下一步应追踪提供者的注册方和摄像头数组的填充方，不能把 JNI 读取函数本身视作网络解码器。
- 对原版 APK 在杭州导航中与位置变化后的两份 Java HPROF 逐项解析 class/instance 记录，`RouteCamera`、`RouteCamera3d`、`Route`、`CalcRouteResult` 类均已加载，但各自存活实例数为 0；同一解析器分别数出约 12 万个 `java.lang.String` 实例。另一份原版路口导航快照也没有这些包装对象。这只说明快照时没有可直接读取的 Java `RouteCamera`，不能排除对象曾短暂存在或原生内存里的摄像头数组仍在使用；获取真实样本应优先追原生路线对象或网络解码，而非重复扫描同样的 Java 包装类。
- TMC 已按路线进度复现 452 事件的进入／清除处理，并将 95 的摄像头速度数组、哨兵值和距离独立适配到前方测速牌及本地 TTS。后端只接受有界、可验证的路线区间／摄像头类型与速度。数据源已在二次导航 `routeguide` 的 kind=3 NCP 记录中找到，见下文；普通 App 5.1 算路响应本身不含这些资料。

## 已排除的候选

- App 5.1 算路响应的 link 字段 4 是随路况变化的速度，字段 5 与耗时对应；不能作为法定限速。当前解码的 route/segment/link 字段尚未识别出道路限速值。
- 对本地杭州道路与高架路线的 5 份原始 5.1 响应作了字段盘点：各候选路线的顶层扩展字段形状一致，`route.16` 固定为两条短记录，`route.17` 为空载荷，`route.31`／`route.33` 为空；segment 也没有额外字段。这些样本没有可直接对应上述 12 字节限速区间的记录。此结论仅限已保存的路线样本。
- 复核 `signed-v51-hangzhou.bin` 和杭州至嘉兴高速样本的 5.1 封套，每份仅有一个 `kind=1` 的压缩路线记录，没有被当前解码器跳过的摄像头／限速附加记录。`route.16` 的两项结构在两条路线间只改变个别路线相关字段，并未随路线长度出现可映射的摄像头数组。
- 对高速样本的所有 262 条 link 逐项盘点：`link.3` 仅为 0/1；`link.4` 从 5 到 115 且随路况细粒度变化；`link.5` 为耗时相关值；`link.11` 全为 0；`link.12` 的 9 个非零值与 `link.6` 的信号灯标志配对。只有一条 link 含 `link.9` 的 37 字节扩展，不能对应沿途完整的限速区间或摄像头列表。地图 BMD 道路瓦片的已解析属性是绘制样式和高度标记，也不能替代法定限速。
- 5.1 `link.12` 的非零值曾是摄像头 ID 候选，但石桥路样本的 6 个非零 link 均同时有 `link.6 & 4` 红绿灯标志，且数量恰与路线的 6 处信号灯一致；不能将它当作测速摄像头或限速值。
- 又以杭州至嘉兴约 80 公里的高速路线做了一次在线对照。普通 TMC 参数、加入 APK `RouteCarParamUrlWrapper` 的 `contentoptions=65664`、再加入 `threeD`／`playstyle`／`soundtype` 等默认值和 `sdk_version=17.00.0.1007`，都得到成功的 5.1 路线，但 `route.16/.17/.31/.33`、segment 和 link 的字段形状未增加限速区间。该路线的 `segment.6` 是收费站名称。缺少这些已确认的 Java 请求默认参数并不能单独解释限速缺失；其他请求上下文或本地路网数据仍待核对。
- APK 包中还有另一条 AJX 路径：`XbusRouteRequestLogic.action()` 调用 `OnlineServiceProto.calcRoute()`，后者向 `ajx.business` 的 92 号通道发送 `NaviGlobalCommandTypeCalcRoute=99040`；`XbusRouteParamAdapter` 构造 `routeType=1`、`switchRoutePB=1` 的结构化请求，默认 `strategy=17`、`invoker=navi`。TMC 目前调用的是 Java `RouteCarParamUrlWrapper` 对应的 `/ws/mapapi/navigation/auto/` GET 5.1 接口。尚未证明车机截图中的那条导航使用哪条 APK 路径；上述 GET 参数对照不能排除 Xbus／navikit 路径取得更完整的原生路线或本地路网限速数据。
- `libamaphorus.so` `0xc6f7b4` 使用的原生算路地址前缀为 `/ws/transfer/navigation/auto/?sloc_precision=1.0&sloc_speed=10&t=carroute&invoker=`；`0xc6f7a0` 在差异算路时另选带 `diff=1` 的同一路径。`0xc4b1e0 → 0xc6f464` 把调用方提供的字符串作为 `x1` 传入，`0xc6f80c` 再将其接到前缀后面；`0xc6f8bc` 将完整地址、请求对象和回调交给原生网络调度器。这个路径与 Java 5.1 GET 不是同一个请求契约。用后者的查询参数对原生路径发空体 POST 返回 HTTP 400／业务 `code=2`，因此仍需追踪调用方生成的字符串、原生请求体和响应解码，不能直接将这个 URL 替换进现有适配器。
- 原生 `RouteManager` 的虚表地址点为 `0xe21168`，`+0x50` 槽经 `0xc4859c → 0xc4b17c` 到上述 `0xc6f464`，确认这是原生请求派发而不是可直接从网页订阅的事件。另一条可核实的 POST 构造路径是 `0xc4ae5c` 在 `0xc4af24` 调用 `0xc65420`，把 `RouteOnlineHttpParamDrive` 生成的字符串写到栈上；随后 `0xc4b054 → 0xc4b2c0` 组织 `RouteParam`、观察者和字符串，`0xc4b4e4 → 0xc6ddb8` 进入原生 HTTP 调度。
- 从官方 App 的 Java 堆快照恢复了两份实际原生 `AosPostRequest`：分别是 `Invoker=plan` 的初始算路 XML 和 `Invoker=navi` 的重算路 XML，经 APK 的 `amapEncodeBinaryV2` 编码作为 POST 体。实际主机为 `nvg.amap.com/ws/transfer/navigation/auto/`；外层查询使用 `ent/in/csid`，`in` 是 APK 编码后的 AOS 参数，`mSignParams` 列表只有 `channel`，已核实签名等于 `MD5(channel + "@" + APK AOS key)`。研究脚本只保存于忽略的 `.local-data/amap-app/`，不保存或输出设备标识与签名 URL 到仓库。
- 按上述原生 XML **结构**重新生成标识、杭州起终点与签名，用 Python 对 `nvg.amap.com` POST，取得 HTTP 200、14,351 字节非空二进制路线。此响应直接从 5.1/v31 路线体开始；旧 GET 适配器另有 10 字节封套。加封套作离线盘点后，得到 3 条路线，每条约 80 公里、260 余条 link。其 `route.16/.17/.31/.33`、segment、link 属性分布与旧 GET 样本基本相同，没有新增可确认的道路限速或摄像头数组。`message.1=1` 与旧适配器要求的 `0` 不同，尚未确认其业务含义，所以暂未替换 TMC 的在线算路。后来在二次导航 `routeguide` 而非这份初始算路响应中找到了限速事件源。
- 再以原版 `navi` 的 `ContentOptions=283842552479774` 替换 `plan` 位请求同一杭州路线，仍取得非空 5.1 响应；三条路线的 route/segment/link 字段形状不变。响应 `message.6` 是 UTF-16LE 的 `ShowInfo` JSON（23 条地图展示提示），不含可辨认的道路限速／测速速度键；不能把这块忽略的扩展误认为限速数据。
- 从原版导航堆快照中的 `AosPostRequest` 恢复了 `/ws/transfer/navigation/routeguide` 的二次导航请求体，核对其编码后的 `PostRequest.r` 与 APK `amapEncodeBinaryV2` 输出一致。请求内层为 zstd 压缩的 JSON，包含路线 `naviID`、`pathArray`、分段、link ID 和主辅动作。用新生成的设备标识与同版本签名，对一份新获取的 5.1 杭州至嘉兴路线发起请求，取得 HTTP 200 的原生 v31 二进制响应。
- `routeguide` 的 kind=2 路线扩展中，link 字段 7 的 type=10 记录包含速度数字及坐标（经纬度整数除以 7,200,000）。高速样本中 43 个此类点的坐标与独立解码的路线几何相差不到约 2 米，数字为 20–120。TMC 已将其作为**沿途限速标志点**独立投影到路线，开始实时导航时按路线会话请求，并对即将到达的点显示“前方限速标志”及播报。标志点与 kind=3 NCP 中的连续道路限速区间／测速摄像头类别是独立资料，不混用。
- 对同一份二次导航响应的三条高速方案逐 link 盘点，type=10 点数分别为 43、46、47，另有 type=2/6/14/16/31 点，其速度字段均为 0；这些类别不能混成限速牌。kind=2 的 link 字段 4 虽有 1200、4200、5600 等重复数值，但第一条 5.1 link 长 85 米、拥堵速度 5 km/h 时该字段为 1200，其他 link 也不能直接对应 type=10 的 30/60/80/120 数字；它不是已证实的法定道路限速。二次响应里 route ID 的四字节值与算路 route ID 逐方案相等，TMC 解码器已据此拒绝错配响应。
- `auto` XML 体直接改发 `routeguide` 返回 HTTP 400／业务 `code=2`；必须使用上面的二次导航请求契约。二次请求不可用时，基础算路和导航保持可用，限速与测速信息保持未知。
- `/ws/transfer/navigation/etatrafficupdate/` 的成功响应里，`greenMaxSpeed` 是绿波速度，不是法定限速；本地样本未带道路限速。
- APK AJX 会在导航中定期 POST `/ws/perception/drive/navigation`，把返回的 `data.tbt` 转交原生 TBT 引擎。本机用同版本 APK 参数、编码和已验证的 AOS 签名在杭州样本获得 HTTP 200、`code=1`，但返回的 `tbt` 只有 `channel: 2`；先请求 `/ws/perception/drive/routeInfo` 再随路线中的红绿灯位置请求 navigation，也没有得到限速区间。该端点在这些样本中不是可用的限速源；不能推断所有路线都没有。
- 用杭州至嘉兴高速路线再次按先 `routeInfo`、后 `navigation` 的顺序查询，前者 `data.tbt.event[]` 只有通用 `custom_type=3` 语音提示，后者的 `data.tbt` 仍只有 `channel`。没有 452／95 事件或摄像头速度数组；HTTP 成功不能解释为导航事件已经接通。
- `libamaptbt.so` 的 `cameraSpeedLimitInfos` 是摄像头资料结构，可能含摄像头限速，但与整个道路路段限速是两类数据。本机上述导航响应没有这个字段。
- `libamaptbt.so` 的导航状态 JSON 序列化器在 `0x4fde6c` 从结构 `+0x350` 读取 `currentSpeedLimit`。状态构造路径 `0x512860` 从其输入结构 `+0x56c` 拷贝它，但尚未追到该输入的生产者。另一处 `+0x56c` 写入 `0xb657fc` 属于不同结构；`0x4ebdf8` 将该结构的同一偏移序列化为 `changePlayType`，因此不能把这次写入当作限速来源。
- `libamaptbt.so` 注册了 `PathModuleSpeedLimitSection`（`0xb62828` 构造）。模块处理器 `0xb81668` 遍历 12 字节记录；`0xb8172c` 从路径接口读取每个 80 字节的 link 对象，检查 `+0x48` 的标志，再由 `0xb81bb4` 对 link `+0x08` 的 `uint16` 向量求最大值，生成连续区间；`0xb819e4` 将该区间和向量导出的数值写为 12 字节记录。这里的第三个字不是已定位的网络字段，必须先找到 link 对象及其 `uint16` 向量的生产者。`libamaphorus.so` 的事件转发路径 `0x61631c` 和 `NaviSpeedLimitSectionInfoData` 序列化器 `0x621108` 均从事件结构起始处读取 32 位值，支持 AJX 事件中的 `speed` 是原生事件载荷。
- 复查 `0xb8172c` 的调用点：`0xcdcbbc` 是桥接包装，调用内部路径对象虚表 `+0x2d0`，把导航 link 的 80 字节记录填入临时数组；随后 `+0x08` 的半字数组才被限速区间模块读取。已验证的原生 POST 响应仍未直接携带这一数组，因此后续要定位该虚方法及其写入来源，尤其是路线组装阶段是否合并另一份路网属性。
- 又定位到模块路径对象的注入点：`libamaptbt.so` `0xb62900` 把入参 `x1` 写入注册的每个路径模块 `+0x28`，并在变化时触发模块虚表 `+0x10`；其唯一直接调用点 `0xa7bc60` 从导航管理结构 `+0x08` 取该路径对象。这证明限速模块读的是已建立的导航路径状态，而不是自行请求网络。后续需要追管理结构 `+0x08` 的赋值及具体路径对象虚表 `+0x2d0` 的实现，找出 80 字节 link 记录中 `+0x08` 速度数组的填充代码。
- 管理结构 `+0x08` 的赋值点也已找到：`0xa7b404` 接收路径对象参数 `x1`，在 `0xa7b49c` 保存到 `+0x08`；`0xa7bc2c` 随后调用上述 `0xb62900` 广播给各模块。`PathModuleSpeedLimitSection` 读取的路径因此沿 `调用方路径对象 → 导航管理结构+0x08 → 模块+0x28 → 桥接虚表+0x2d0 → 80 字节 link 数组` 传递。仍需定位 `0xa7b404` 调用方提供的具体路径实现与其限速半字数组写入点，不能从函数名推断网络响应已含限速。
- 对同一条杭州至嘉兴高速路线调用 APK 内另一候选 `/ws/transfer/navigation/auto/`，带已验证的 App 签名、5.1 和前述默认参数时 HTTP 200 但响应体为 0 字节，未取得可供解码的路线。把旧端点的 `output` 改为 `json` 得到业务 `code=2`、空 `path_list`；这不是成功的 JSON 算路响应。两次实验都不能作为限速数据源，也不能排除原生请求体与当前 GET 参数不同。
- Java 算路器在起点接近车辆位置时可能额外置 `contentoptions` 的 16384 位，并在特定请求置 512 位；同一高速样本分别用 82048、82560 请求均成功，但 route、segment、link 的字段形状及 `route.16/.17` 仍未出现可识别限速记录。不能把缺失这两个已知标志当作唯一原因。

## 二次导航 NCP 事件源与验证

- 同一份 `routeguide` v31 响应的 kind=3 记录包含 route ID 与 `ncp0` 原生事件块。事件块由长度前缀的 MessagePack 字典组成；`NCPEvent` 描述触发条件和剩余路线距离，`_ds` 是事件 JSON。解码器核对导航会话 ID、逐方案 route ID、原生路线总长和 segment 数，不接受错配路线。
- 限速事件的 `_ds` 仅含 `speed`，其 `((distance>0) && (distance<=N))` 条件给出区间长度；`_rd` 是终点到该区间末端的剩余原生里程。区间边界始终落在 `_ss/_es` 指定 segment 内。杭州至嘉兴约 80 公里新路线解出 21 段，其区间长度与 5.1 对应 segment 的 link 长度之和吻合；因此用每个 segment 的原生长度与已验证地图几何长度分别换算路线进度，作为网页端 452 数据。
- 摄像头事件有带 `type`／`speed[]`／`distance`／坐标的直接记录，也有 `cameraId` 主记录及 `subCamera[]`。后者的 segment、link、`distToLink` 定位与 `_rd` 换算的原生里程相等。摄像头经纬度投影到 5.1 路线的误差低于 1 米，剩余里程换算与几何进度差约 3.2 米。只接收原生数字测速类型 7、25、26、27 和合法速度数组；同一新路线得到 66 个唯一测速事件，其中固定测速 46 个、区间测速起终点各 10 个，作为网页端 95 数据。
- 后端在开始实时导航时使用已规划的原始路线会话发一次二次请求，返回限速区间、摄像头和 kind=2 标志点；前端依据可信定位和路线进度更新当前限速、前方测速及播报。后端解析或请求失败时返回空数据，基础导航继续。合成 NCP 边界／错配样本、后端输出契约、前端事件规则均有测试；实车位置和发声尚未复测。

## 原版模拟器局限

蓝叠模拟器内的原版导航在接收 `LocationManager` 测试定位后，位置图标能移动，但速度圆牌仍为 `--`，即使测试定位包含 30 m/s；因此该实验不能证明原版 452 限速区间事件实际触发。Python 已取得原生二次导航响应中的区间和摄像头数据；车机上的事件位置及语音仍需实测。

运行环境只有车机浏览器和 Python 后端。APK 的 `ajx.business` 导航事件总线存在于 Android App 进程，不存在可让网页直接订阅的同进程桥；因此“接导航事件”在 TMC 中是移植**事件产生所需的数据与计算**，再输出同语义的 452／95 状态，而不是在前端注册 APK 事件名。NCP 未提供区间或位置匹配不可信时页面仍显示未知，不得以路况速度填充。

后续又沿预生成的 45 个连续 GPS 点推进蓝叠 `LocationManager` 测试提供者，`dumpsys location` 确认系统末次定位变为 `30.331624,120.182624`，但原版导航画面的车辆仍停在原处，当前速度圆牌仍为 `--`，没有足够证据认为导航引擎消费了这些点。需要通过原生运行时插桩或能驱动引擎的位置输入取得事件样本，不能把系统层 mock 成功等同于高德导航引擎收到定位。

本轮复核仍在运行的蓝叠导航画面：已进入石桥路至秋石高架的实景导航，车速圆牌为 `-- km/h`，尚未触发可采集的道路限速事件。虽然能看到禁压线、摄像头图标，这不能证明摄像头限速 `speed[]` 已进入路线对象；不能凭图标制造测速限速数值。

研究时还发现 5.1 route 的 link 长度字段可大于 16 位（杭州样本 66,600 cm）；`v51_dynamic_route.py` 的边界已修正，保证长高架路段不会阻断后续动态请求分析。

## 严重超速红色警告

APK 的 AJX 定义了速度控件状态 `WidgetSpeedStateNotOverSpeed=0`、
`WidgetSpeedStateOverSpeed=1`、`WidgetSpeedStateOverSpeedSerious=2`，并在
`TripNaviSpeedView` 中准备超速 Lottie 图层。`TripNaviRenderWidgetConfig`
为资源 220001 配置 `halo-left.json`、`halo-top.json`，横竖屏分别沿左右、
上下边缘镜像铺设。APK 的 `assets/horusAssets/horusAssets.pack` 内实际包含
两个 20 fps／40 帧动画及 `red-left.png`、`beam1.png`；图像已原样复制到
`web/public/amap/overspeed/`，TMC 用 CSS 按两秒一轮复现边缘红光和扫动。

浏览器无法订阅 APK 运行时的速度控件状态 87 事件，原生严重级别的数值
分界尚未确认。TMC 的普通超速仍按 APK 默认的 1.1 倍限速判断；边缘特效
暂以 `车速 ≥ max(1.3 × 道路限速, 道路限速 + 20 km/h)` 作为保守触发条件，
且仅在可信的实时定位车速和已知道路限速时显示。模拟导航、估算车速、
未知限速和偏离路线时不显示。此阈值是 TMC 的显示策略，不能标作 APK
原生严重超速判定。

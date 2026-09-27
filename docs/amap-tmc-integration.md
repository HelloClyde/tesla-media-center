# 高德 App 地图导航接入

2026-09-27：已从旧的道路摘要实验页切换为地图导航。算路仍使用消费者 App 的接口，没有替换成开发者路线 API。

## 使用

访问 `/#/apps/amap`，底图为高德地图瓦片（Leaflet 显示，不需要网页 Key）。初始北京坐标明确标为示例。点击「定位」设置当前位置，选择「终点」后在地图点击选点，也可输入 GCJ-02 经度、纬度并回车。当前不含地址/POI 关键词搜索。

「规划路线」发出真实 App HTTP 请求，显示候选路线；选择方案后「开始导航」使用浏览器实时定位，提供位置跟随、剩余距离、转向提示、中文语音和偏航重算。「模拟导航」使用同一条真实算路结果回放，始终显示模拟标识，不读取车辆定位。

浏览器定位先通过 `coordtransform` 将 WGS-84 转为 GCJ-02。精度超过 60 米不推进引导；连续 3 次偏航且距离超过 40 米/1.5 倍精度时重算，重试间隔至少 20 秒。过期定位不处理，15 秒无新定位提示信号中断。退出或卸载页面会清理定位监听、回放/信号定时器、请求、地图与语音。

## 调用链

`AmapAppView.vue → POST /api/amap-app/route → 隔离 Python 子进程 → /ws/mapapi/navigation/auto/ (route_version=5.1) → 32 字节分帧 → Zstandard → Protobuf → 有界路线 DTO → Leaflet / 浏览器引导`。

原 `/probe` 路径保留兼容，使用同一新版解码器。`/status` 的 configured 仅表示本地资源可用。只有新版解码和几何检查通过才返回 ready/navigationAvailable。

- APK 17.00.0.2005 的 `libamaptbt.so` getRouteVersion JNI 位于 0x4a8bd4，读取 0xcb863 的字符串 `5.1`；旧 Java 构造器的 `2.5.3` 只是默认值。
- `libassembly_kit.so` DrivePathCodecImpl 0x714e0 → 0x7124c / 0x71378 → DrivePBPathDecoder 0xb60c8，提供分帧与解压链证据。
- Protobuf 版本字段 51；逐段坐标为 zigzag 增量，每段首点重新起算，比例 3,600,000 单位/度。逐 link 的坐标索引和数量须完整覆盖所属段。
- 长度、压缩大小、坐标范围、起终点邻近关系、逐段连接差异、坐标覆盖和总距离交叉检查；未知或不一致结构拒绝导航。
- 上游部分路口留有连接间隙。保留分段、记录 breaks，不生成虚假连接线；超过 100 米的间隙拒绝。显示距离按已解码几何计算，转向由相邻路段方位计算。
- 签名材料仅在子进程内存中使用；固定 HTTPS 主机、禁用重定向、40 秒执行上限、响应 4 MiB 上限、解压 16 MiB 上限。前后端需要 TMC 登录且返回字段白名单过滤。

## 本机依赖

Python 3.11+，安装可选依赖 `python -m pip install -r tools/amap-app/requirements.txt`。本机研究资源 `amap-release.apk` 和 `libserverkey.so` 放在 `.local-data/amap-app/`，或设置服务端 `TMC_AMAP_APP_ASSETS`。固定 SHA 校验；不随代码/镜像分发 APK 或反编译产物。WSL 服务环境已安装依赖并启动。

## 验收与限制

- 新版真实 HTTP 样本：北京两组起终点和杭州一组；共 5 条候选路线，52/48/85/140/138 个坐标，全部完成解析与 link 覆盖检查。
- 本机浏览器实际完成：真实请求 → 地图折线 → 模拟车辆跟随 → 路口提示变化 → 到达目的地；检查 773×601 布局。
- 研究工具 52 项、后端 12 项、前端几何 4 项测试；类型检查和生产构建。
- 实时定位/偏航逻辑已接入，但当前机器未做特斯拉 GPS 路测。浏览器权限、定位精度、语音支持取决于车机。
- 这不是原生高德引擎的完整复刻：没有车道级指引、复杂路口图、限速摄像头、实时交通着色、可靠 ETA、离线地图或地址关键词搜索。转向是几何推导，不宣称已复刻原生全部机动语义。

底图接口参考：[高德 TileLayer 文档](https://lbs.amap.com/api/maps-javascript-api/reference/layer/tilelayer)；显示层参考：[Leaflet API](https://leafletjs.com/reference.html)。

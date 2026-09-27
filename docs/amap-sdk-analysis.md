# 高德 Android 导航 SDK 11.3.100 静态分析

分析日期：2026-09-24。此文记录本地包的静态证据，不代表内部接口已经调用成功，也不代表 WeMate 使用相同实现。

## 样本与方法

- 来源：https://lbs.amap.com/api/android-navi-sdk/download
- 官方完整包：`AMap_Android_Navi_SDK_All.zip`，235869749 字节。
- SHA-256：`7a877997cd432bfeed0c821087792bc49ed3ca22151d7f4dbca17c98ce539f59`。
- 实际 JAR：`AMap3DMap_11.3.100_AMapNavi_11.3.100_AMapSearch_9.8.1_AMapLocation_11.3.101_20260924.jar`。
- 解包、JAR 常量扫描、`javap -p -c` 字节码反汇编、ARM64 ELF 可打印字符串扫描。未运行 SDK、未发起内部接口请求、未验证请求签名或响应编码。
- 完整包通过 ZIP CRC 检查。样本及反汇编输出位于 `.local-data/amap-sdk/`，不纳入 Git。

## 确认的边界

Java API 提供 `AMapNavi.calculateDriveRoute`、`reCalculateRoute`、`startNavi` 等入口。`AMapNaviCoreManager` 声明以下 JNI 方法：

- `nativeCalculateDriveRoute` / `nativeReCalculateDriveRoute`
- `nativeStartNavi` / `nativeGetRoute`
- `nativeSetGpsInfo`
- `nativeNetworkCallback(int, int, byte[], String, byte[])`
- `nativePushDriveRoute` / `nativePushRouteGuideforVer5`

据此可以确认算路入口、位置输入和网络结果处理进入原生层；不能把 Java 外壳直接翻译成 JavaScript 就获得完整导航。包内包含 `libAMapSDK_NAVI_v11_3_100.so` 等 ARM64/ARMv7 原生库，不能原样在浏览器加载。

观察到的请求链路为：原生核心通过 `AMapNaviCoreObserver.onRequestSend` 回调 → `com.amap.api.navi.core.d.onRequestSend` Java 处理 → 网络任务。网络结果通过 `networkCallback` 进入原生核心。具体底层编解码仍需进一步分析。

## 网络分析入口

`com.autonavi.ae.guide.NaviNetworkRequest` 明确包含：

`isRouteRequest`、`serverType`、`transType`、`reqId`、`byte[] data`、`url`、`requestHeader`、`requestParameters`、`isPostMethod`、`needLoginCookie`。

这提供了采集算路请求及其响应的明确边界。`byte[]` 只能证明传递原始字节，不能单凭类型断言它一定加密、压缩或使用 Protobuf。

公开接口 `AMapNaviNetWorkProxy` 只有三个方法：

- `getHostByPath(String, String)`
- `getExtRequestParamByPath(String, String)`
- `onResponseExtParam(String, String, String)`

它允许定制主机及扩展参数，但不是完整的请求体/响应体拦截器。仅实现该接口不足以获得全部网络数据。

原生库出现了导航交通上报、ETA 路况更新、语音音频、路口图及地图资源等 URL 字符串。混有测试地址和其他业务地址，因此字符串清单不能直接当作可用接口目录；没有确定一个已验证可独立调用的完整驾车算路端点。

## 额外能力的证据

`AMapNaviCoreObserver` 中存在如下回调：

| 回调 | 表明 SDK 暴露的能力 |
| --- | --- |
| `onUpdateNaviInfo` | 动态导航信息 |
| `onShowNaviLaneInfo` | 车道提示 |
| `onShowCrossImage` | 路口图 |
| `onUpdateSAPA` | 沿途设施更新，具体设施类型需结合数据验证 |
| `onReroute` | 重算通知 |
| `onSuggestChangePath` | 建议切换路线 |
| `onPlayTTS` / `onPlayPCMData` | 语音文字/音频相关回调 |
| `onUpdateBackupRoute` | 备选路线更新 |

这些证据支持“SDK 暴露的导航能力很丰富”，不证明每个回调都对应一个独立 HTTP 接口，也不证明账号默认拥有全部能力。

## 移植判断与下一步

1. 优先验证独立算路：在可运行 SDK 的 Android 环境中，用本人申请并正确配置的 Android Key，执行固定起终点的最小算路示例，记录请求和响应边界。当前尚未建立该运行环境，PATH 中未找到 adb。
2. 对比不同起终点、策略和车牌条件下的请求；区分业务字段、设备/会话字段及授权字段，不把别人的 Key 或会话写进实现。
3. 使用相同合法凭据在 Python 中验证能否重放请求，并确认返回数据是否能独立解析；在这一步成功前，不把内部协议接入生产页面。
4. 首个验证目标为：取出至少两条路线的坐标、耗时及交通信息，转换成项目自己的 DTO，在 Web 地图绘制。
5. 语音时机、位置匹配、偏航及车道引导分别判断是否依赖原生状态机。即使算路协议移植成功，这部分也可能需要独立实现或保留 Android 引擎作为服务端桥接；后者是候选架构，尚未验证可部署性。

当前结论：已找到明确的请求/响应分析边界，值得继续做动态验证；尚不能承诺仅靠内部 HTTP 接口还原完整 SDK。

## 动态验证准备进展

已新增 `tools/amap-probe/`：固定路线测试应用、可复现 APK 构建脚本、请求/响应采集脚本。APK 已编译、打包并通过签名校验，但尚未实际运行。用户没有安卓手机，已转向模拟器方案；官方 Android 30 镜像元数据与下载内容大小不一致，环境下载已停止，详见该目录 README。Android Key 仍待绑定测试包名与签名。

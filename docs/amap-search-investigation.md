# App 目的地搜索核对（2026-09-27）

## 当前结论

已定位 APK 中的一条地点联想搜索链路，尚未取得有效的线上地点结果。
不能将 HTTP 200 当作接口成功：本次验证返回的是 HTML 访问拦截页，而非 JSON。
没有证据证明拦截原因是缺少账号登录；也没有证据证明匿名 Python 请求已满足服务器要求。

## 静态证据

研究资源为本地 `amap-release.apk`，固定版本校验见
`tools/amap-app/tmc_route_helper.py`。从 `assets/ajx.bundle/bundles.oajx`
经现有 SPX 提取器读取以下资源（这里只记录文件名和行为，不提交提取的 App 源码）：

1. `SinglePoiSearchLogic.js` 的 `fetchSuggPoiData` 获取搜索参数，然后调用
   `SuggPoiSearchRequest.fetch`；未见调用前必须登录的检查。
2. `SuggUtils.js` 的 `getSuggParam` 使用 `words`，而不是 `keywords`；
   附带 `city`、`user_city`、`user_loc`、地图中心坐标、地图范围等。
   `city` 来自坐标对应的行政区代码，并非固定城市。
3. `BaseSugRequest.js` 使用 POST 调用 `$aos.m5$/ws/shield/search/sug`，
   明确指定签名字段顺序为 `channel`、`city`、`words`。
4. `CLNetwork.js` 构造 AosRequest，设置 `aos_params: true`，发布包默认
   `ent: true`，最后通过 `natives.XMLHttpRequest.fetch` 交给原生层。
   仅复制业务参数和签名不能证明已复现原生线上请求。
5. `NetworkParam.java#getNetworkParamMap` 附加版本、设备及会话等公共参数；
   `uid` 仅在非 null 时附加。`session` 是通过独立的 `getSession()` 获取的数值，
   不能仅凭字段名称把它解释成账号登录 Token。
6. `SinglePoiSearchLogic.js` 仅在 JSON `code === 1` 时读取 `tip_list`，
   或汇总 `city_list[].tip_list`。失败还可能回退到 App 本地离线搜索，
   所以手机界面显示结果也不直接证明某次网络请求成功。
7. `SuggPoiParse.js` 将结果 `x/y` 解析为经纬度，并处理可选的入口坐标
   `x_entr/y_entr`。后续适配必须区分有坐标 POI 与无坐标联想词。

另发现导航业务 `TripSearchDriveSugRequest.js` 使用独立的
`/ws/aos/route/search/sugList`（JSON POST），不能混用这两条请求的参数和签名规则。

## 本轮 HTTP 验证

先前 GET + keywords 的探测与上述调用链不符，不能用于判断是否需要登录。
本轮按已确认的 POST、words/city、位置及签名字段进行一次验证，结果为：

- HTTP 200；Content-Type 为 `text/html;charset=UTF-8`。
- 内容为访问拦截页，不是 `code: 1` 的地点结果。
- 未携带真实用户账号、登录 Cookie 或伪造设备标识。
- 未实施验证码绕过、代理轮换或重复重试。
- 脱敏结果保存在本地 `search-post-verification.json`；不保存签名 URL 或密钥。

## 尚待验证

原生请求层如何附加公共参数、执行 ent 处理，以及业务响应与访问拦截之间的区别，
仍需核对。下一步应对照原生实现或在获授权的 App 运行环境观察匿名请求，
而不是把登录账号当作默认解决方案。拿到真实成功响应前，不宣称目的地搜索已经可用。

## 原生网络层追踪补充

已继续追踪到 `com.autonavi.minimap.ajx3.modules.net.ModuleRequest`，
它继承 `AbstractModuleXMLHttpRequest`，不是先前只看到的方法声明。

调用顺序：

```text
BaseSugRequest.fetch
  → CLNetwork.AosRequest / Request.send
  → natives.XMLHttpRequest.fetch
  → ModuleRequest.fetch / optionsToRequestInfo
  → ModuleRequest.c.a（构造 AosPostRequest）
  → AosRequest.buildHttpRequest
  → AosPostRequest.processParams
  → AosRequest.securityGuardSignByV2
  → 网络发送
```

确认的请求结构差异：

- `bodytransfer` 默认开启，原生层先将表单拆为业务参数，URL decode 值；
  并不是把 JavaScript 中的 body 原样发送。
- `aosSign.ent` 被映射到 `setEncryptStrategy(2)`；它确实是加密策略，
  不是账号状态。
- `aos_params_inbody` 默认 false。此分支把公共参数放到 URL 侧，
  业务参数放到 body 侧；具体分配还受是否已有原始 body 等分支影响。
- `AosPostRequest.processParams` 对业务参数调用 `xxTeaEncrypt`。
  `AosRequest.buildHttpRequest` 对 URL 参数也有独立的加密封装。
- 常规业务 `sign` 与后续 `securityGuardSign` 是两个不同阶段。
  后者受 `withSecurityGuardSign()`、启动场景及运行时签名模式等条件控制，
  会使用客户端安全组件。未证明本次搜索实际启用了哪条运行时分支。
- `wua` 默认 false 不等于跳过全部安全校验；它只是传给安全组件的一个选项。
- 找到 `IAosEncryptor` 实现 `rf2`：其字符串 `xxTeaEncrypt` 委托给
  `serverkey.amapEncodeV2`，字节版本委托给 `amapEncodeBinaryV2`。
  `withSecurityGuardSign` 在没有配置提供者时默认 true，有提供者时使用其值；
  `isVirtualV2Sign` 和启动场景仍依赖运行时状态。这里没有账号登录判断。

本轮没有再向服务器反复发送试探请求，也没有生成或伪造安全组件证明。
结论仍是“普通 Python 表单请求不等价于 App 请求”，而非“已确定风控原因”。
仍缺成功的匿名 App 请求观测，才能确认线上实际参数和分支。

## 默认配置和安全组件入口（后续核对）

继续检查固定 APK 中的 `vu5` 与 `uu5`，确认：

- `vu5` 实现 `ISecurityGuardSignConfigProvider`。首次读取
  `network_config` 本地配置时，安全签名开关和 V2 签名模式的默认值均为 true。
  这些默认值可能被云端配置更新，不能等同于某台实机的最终值。
- `rf2.isVirtualV2Sign()` 读取该配置，而 V2 执行入口位于 `uu5.f`。
- V2 执行通过 Android Application 初始化 SecurityGuard 的
  `IUnifiedSecurityComponent`，最终调用 `getSecurityFactors`。
  它依赖 App 运行环境中的组件和配置，不只是前文的业务 MD5 签名。
- `uu5.f` 组件初始化失败、返回为空或抛异常时返回 null；这不表示请求一定成功，
  也不提供服务器接受缺省安全字段的依据。
- 这段初始化和调用链没有显式要求用户账号登录。它与运行环境校验有关，
  不能用“缺少账号 Cookie”解释所有失败。

本机已找到用于早期探针编译的 Android SDK（build-tools、platform-tools、platforms），
但该 SDK 目录未包含 emulator 和 system-images。拥有编译 SDK 并不代表已经具备
可运行完整 App 的环境。本轮未安装模拟器，也未请求用户账号。

截至目前，业务请求、参数组织和安全组件调用入口已明确；未验证的关键点是
实际 App 的运行时配置、组件输出，以及成功的匿名搜索响应。
普通 Python HTTP 尚不能被视为完整替代；本轮未尝试伪造安全组件输出或绕过拦截。

## 官方 App 运行验证准备

- Windows Hypervisor Platform 的 InstallState 为 1，系统 HypervisorPresent 为 true。
  WMI 的处理器虚拟化字段为 false，不能单凭该字段判断 BIOS 未启用虚拟化。
- adb 未列出连接设备；本地 APK 只包含 arm64-v8a 原生库。
- 计划验证 Google APIs Android 11 x86_64 镜像与该 ARM64 APK 的兼容性，
  尚未把转译可用性当作已验证事实。
- 官方 SDK 清单的稳定版 emulator 包为 `emulator-windows_x64-15917651.zip`，
  标注大小 441926448、SHA-1 `54fa750822ff462d57e04fc8e98e60f08df2bb61`。
  单连接下载缓慢；分段下载的范围校验随后失败。
- 独立请求 bytes=0-1023 返回 HTTP 206，但 Content-Range 总大小为 441830240。
  重新获取官方清单仍为 441926448。来源元数据与下载响应不一致，原因未确认，
  没有忽略校验或执行该安装包。
- 下载任务已经结束；部分文件只在忽略目录 `.local-data/amap-sdk/downloads`。
  没有安装系统镜像、修改虚拟化设置或启动高德 App。

下一步需取得与官方清单一致且通过校验的模拟器包，再验证启动、ARM64 兼容性，
最后才是未登录官方 App 的实际搜索。当前仍没有成功搜索样本。

## 更换模拟器版本：已完成

改用官方归档的 Android Emulator 36.4.9 Stable（build 14788078）。
来源：https://developer.android.com/studio/emulator_archive

- 下载入口：官方归档链接的 `redirector.gvt1.com/edgedl/android/repository/`。
  对相同文件，`dl.google.com` 的范围响应仍报告不同总大小，原因未确认；
  官方归档入口的大小为 419394474，与归档元数据一致。
- 使用 1 MiB 分段下载并检查 Content-Range，整包 SHA-256 校验通过：
  `f93b0d51b3ea443ba7a068f2bc39cfdb30fae3ad0c98d001a7790d9acc85c6d5`。
- 已解压至忽略目录 `.local-data/amap-sdk/android-sdk/emulator/`。
- `emulator.exe -version` 实测返回 36.4.9.0、build_id 14788078。
- `emulator.exe -accel-check` 返回 0，报告 WHPX(10.0.19045) installed and usable。
- 未修改系统虚拟化功能，未重启电脑。

模拟器程序现已可用；Android 系统镜像尚未安装，因此还未启动 Android、
验证 ARM64 转译或在官方高德 App 内完成未登录搜索。不要将加速自检通过
表述为 App 搜索已经成功。

## Android 系统镜像已安装

- Google APIs Android 11 / API 30 / x86_64 revision 16 镜像下载、校验和解压完成。
- 官方镜像大小 1438186618 字节，整包 SHA-1 实测与清单一致：
  `6ae21030eaadc041078444d3798e4b399f3e787d`。
- 安装目录：`.local-data/amap-sdk/android-sdk/system-images/android-30/google_apis/x86_64`。
- 已准备独立的 `tmc-amap` AVD 配置和后台启动脚本，均在本地忽略目录。
- 用户要求先处理 QQ 音乐首页按钮，下载在后台完成；尚未启动此 AVD、
  安装高德或确认 ARM64 转译和未登录搜索。

## Android App 首次运行验证（2026-09-27）

- 独立 AVD 已完成启动，`sys.boot_completed=1`。
- 系统报告 `x86_64,x86,arm64-v8a,armeabi-v7a,armeabi`，原生桥接为
  `libndk_translation.so`；APK 安装返回 Success。
- 官方 App 可展示首次使用协议页；继续后退出到 Android 桌面。
  再次正常启动也返回桌面，尚未进入搜索页面。
- crash 日志记录主进程和 locationservice 的 SIGILL（SI_TKILL），
  回溯经过 libndk_translation 的 GuestThread / ExecuteGuest / RunGuestCall。
  这说明目前运行环境没有通过实际兼容性验证；不能仅凭回溯判断
  是不支持的 ARM 指令还是 App 主动触发信号，更不能据此断言需要登录。
- 原始日志保存在忽略目录 `.local-data/amap-sdk/amap-native-crash.log`。
  本轮没有修改 APK、绕过检测或生成安全组件凭据。

下一步应先解决运行环境兼容性（对照更新的官方 Android 镜像），
再验证匿名搜索。当前没有新增可供 Web 接入的成功搜索样本。


## Android 13 对照验证（2026-09-27）

为排查 Android 11 转译兼容性，下载官方 Google APIs Android 13 / API 33 /
x86_64 revision 17 镜像 `x86_64-33_r17.zip`。官方清单来自
`https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-3.xml`，
下载使用官方 redirector.gvt1.com 入口。完整大小 1707857511 字节，SHA-1
`2b96f5bd5c79bfe1cc645e70b3e630b5755d9711` 实测匹配。

独立 AVD `tmc-amap-33` 在端口 5556 启动，最终 `sys.boot_completed=1`。
此镜像运行时 ABI 仅为 `x86_64`，`ro.dalvik.vm.native.bridge=0`，没有
`/system/lib64/libndk_translation.so`。完成启动后安装同一份官方 ARM64 APK，
明确返回 `INSTALL_FAILED_NO_MATCHING_ABIS` / res=-113。

结论：该 Android 13 镜像不能运行此 APK，不能用于判断原 Android 11 SIGILL
是否消失。不能把系统版本更新等同于 ARM64 转译更完善。当前仍没有官方
App 未登录成功搜索样本，没有新增可接入 Web 的搜索接口。

下一轮先验证候选环境确实提供 ARM64 执行能力，再下载或启动；不要继续盲换
x86_64 镜像。可行方向是可用的 ARM64 Android 环境或具有经验证 ARM64 转译
能力的环境。此次未改 APK，也未修改现有 Web 地图、算路或缓存实现。


## ARM64 候选环境核对（2026-09-27）

优先候选：BlueStacks 5 的 Android 11 实例，ABI 选择 Custom / ARM 64 bit。
官方 ABI 文档明确列出 ARM 64 bit；官方 Hyper-V 文档说明新版本 Android 11
可在启用 Hyper-V 的 Windows 环境运行，适合当前仍需要 WSL 的主机。
这是文档层面的候选，尚未安装或验证高德启动/搜索，不承诺其转译一定兼容。

- https://support.bluestacks.com/hc/en-us/articles/360058929011-What-is-Application-Binary-Interface-ABI-in-BlueStacks-5
- https://support.bluestacks.com/hc/en-us/articles/4415238471053-System-requirements-for-BlueStacks-5-on-Hyper-V-enabled-Windows-10-and-11

备选：Genymotion SaaS 原生 ARM64 云设备，可通过 gmsaas 连接 ADB。
需用户自己的服务账号及确认可用额度后再创建实例；本轮未创建云资源。
其 Windows/Intel Desktop 版本不是等价替代，官方明确不支持 ARM64-only App。

- https://www.genymotion.com/blog/genymotion-arm64-devices/
- https://docs.genymotion.com/usage/saas/connect_adb/
- https://support.genymotion.com/hc/en-us/articles/360010029677-How-to-run-applications-and-games-for-arm-arm64

后续验收：运行时 ABI 包含 arm64-v8a → 官方 APK 安装成功 → App 首页稳定 →
未登录搜索成功 → 核对线上请求而非离线结果。任何前一步失败都不能称搜索接口已打通。

### 2026-09-27 本机 BlueStacks Android 11 实测

- 官方 5.22.280.1025 主安装器签名有效；Rvc64 镜像 690081621 字节，MD5 与官方 metadata.txt 的 cf5045f7c9d3719a9471f34a969c97ef 一致。安装到 E:\BlueStacks_nxt，日志确认安装完成。
- 旧 Android SDK 模拟器占用 5555，早期连接实际命中旧设备，不能算 BlueStacks 测试。已关闭旧模拟器。BlueStacks 默认端口未正常监听，使用 BstkVMMgr controlvm 添加仅 127.0.0.1:5585 → guest:5555 的 NAT 转发后连通；远程 ADB 仍关闭。
- 核对新设备运行时 ABI 包含 arm64-v8a，官方高德 17.00.0.2005 APK 安装返回 Success。
- 首次进入地图出现 ANR：SplashActivity Input dispatching timed out，等待焦点事件 5005ms。重启后成功显示地图首页及可关闭的登录提示，未登录任何账号。
- 关闭登录提示、尝试进入搜索后，官方 App 显示“你的操作过于频繁，请稍后再试”。停止继续重试，尚未取得成功搜索请求。该提示本身不能确定是 IP、设备环境或其他策略原因，也不能证明必须登录。
- 本地证据：.local-data/bluestacks-rvc64/{activity.log,screen.png,retry.png,search.png}。其中 retry.png 为地图首页，search.png 为限制提示。
- 当前结论：本机 ARM64 转译环境与官方 App 首页已跑通；匿名搜索仍未验证成功，不能宣称 TMC 搜索接口已接通。后续需在限制解除后低频复核，并区分网络出口与模拟器兼容性问题。
### 2026-09-27 搜索限制的静态排查

本轮仅读取本地 APK / 已提取资源，没有发送搜索请求，也没有修改验证逻辑。

已确认的联想业务链（不等于已证明截图使用此入口）：
`SinglePoiSearchLogic.fetchSuggPoiData` → `SuggPoiSearchRequest.fetch` →
`BaseSugRequest.fetch` → `NetworkBase.ajax.post` → `CLNetwork.Request.send` →
`natives.XMLHttpRequest.fetch`。BaseSugRequest 指向 `/ws/shield/search/sug`。

- SinglePoiSearchLogic.js:25–38：空关键词直接返回；非空关键词取消上一个请求，构造参数，非强制离线时发起联想请求。此方法内部没有固定延时；尚未追到输入组件的触发/防抖，不能断言每个按键必定请求一次。
- SinglePoiSearchLogic.js:42 起：仅 `resText.code === 1` 视为在线业务成功，其他情况尝试离线联想。离线结果不能充当在线成功证据。
- CLNetwork.js:58：HTTP 2xx 或 304 判为传输成功；368–374 行随后执行 JSON.parse，HTML 会走解析失败分支。因此 HTTP 200 与可用的搜索 JSON 是两回事。
- ModuleRequest.java:174–249：AOS 成功回调将状态、响应正文、响应头与 csid 传回 JS；目前已读的这个回调中没有直接展示“操作过于频繁”的逻辑。
- 对 APK 的 dex/html/js/so 明文扫描未找到完整限制提示。未覆盖压缩 AJX 内容、动态下载模块和服务器页面，因此不能根据未命中断言提示必定来自服务器。
- classes4.dex 中发现 `X-Auth-Block` 字符串；反编译 ob1.java:191 仅看到读取响应头并调用 TextUtils.isEmpty，未建立与当前搜索入口/限制页面的连接，不能据此认定原因。classes4 JADX 输出有 9 个反编译错误，不能视为完整源码。

结论：联想请求和 JSON 失败/离线回退链已确认；截图限制页的打开者、对应实际响应、模拟器/IP/频率判定原因仍未定位。仅静态客户端代码无法还原服务端实际命中的规则。后续应优先找限制页的导航来源及正常错误日志，不通过修改判断或伪造验证结果来推测成功。
# 高德 SDK 最小动态测试

独立于媒体中心的 Android 测试应用，用固定起终点验证高德 SDK 11.3.100，不索取 GPS 权限，不自动导航，不修改请求或绕过鉴权。SDK 包、APK、调试签名和采集结果均保存在项目忽略目录 `.local-data/amap-sdk/`。

## 已完成的验证

- Java 源码针对实际 SDK 和 Android 33 编译通过。
- D8 转换、APK 打包及签名验证通过，生成 `.local-data/amap-sdk/probe-build/amap-probe.apk`。
- D8 提示 SDK 的地图 Fragment 类缺少 support-v4。测试应用不使用这些 UI 类；是否存在运行时间接依赖仍需实际启动验证。
- `capture.js` 通过 Node 语法检查；类名及方法签名经 javap 核对。尚未在 Android 进程内验证 Hook。
- 尚未完成原生库加载、SDK 初始化、真实算路和请求重放。不能将生成 APK 等同于运行通过。

## 本地 Key 绑定资料

- 包名：`com.helloclyde.amapprobe`
- 当前调试签名 SHA-1：`31:14:57:00:E8:3E:00:C0:D9:9D:02:A2:2F:B5:B5:2A:FA:AD:E0:D2`
- 在高德控制台申请 **Android 类型** Key，绑定以上包名与 SHA-1。网页 Key 不作为替代品。
- Key 在测试应用界面输入，不提交到仓库。重新生成调试 keystore 后指纹会变，应以 `build.py` 输出为准。
- 点击测试按钮前阅读应用内说明及高德 SDK 隐私政策：https://lbs.amap.com/pages/privacy/ 。SDK 必要设备信息及固定路线请求可能发送至高德；本应用不保存输入 Key。

## 构建

需 Java 11、Android platform 33、build-tools 33.0.2，以及本地已解包的高德 JAR 和 ARM64 原生库：

```powershell
python tools/amap-probe/build.py
```

默认 Android 工具目录为 `.local-data/amap-sdk/android-sdk`；可用 `AMAP_PROBE_ANDROID_SDK` 环境变量指定。生成 APK 包含 SDK 自带 assets，只有 ARM64 原生库。

## 运行与采集

先用 ARM64 安卓设备，或支持 ARM64 转译的 Google APIs 模拟器。不要假设任意 x86 模拟器都可运行该 SDK。

```powershell
$adb = '.local-data/amap-sdk/android-sdk/platform-tools/adb.exe'
& $adb install -r .local-data/amap-sdk/probe-build/amap-probe.apk
& $adb shell am start -n com.helloclyde.amapprobe/.MainActivity
```

启动时仅测试原生库加载。填写自己的 Android Key 后，再手动同意并执行固定路线测试。成功结果写入应用私有文件，可用 `adb shell run-as com.helloclyde.amapprobe cat files/routes.json` 读取。

网络采集使用匹配版本的 Frida 16.x Python 包与 Android server（该版本自带 Java bridge），需要可调试/已具备相应调试权限的测试环境。工具不安装 server、不提权，不绕过 TLS 或修改鉴权。17.x 需要另行打包 Java bridge，不能直接套用此脚本。

```powershell
python tools/amap-probe/capture.py --device <明确的测试设备ID>
```

先启动测试应用、附加采集，再点击算路。采集请求的 URL、头、参数及数据，以及原生核心收到的响应字节。响应参数目前使用位置编号命名，尚未断言它们分别是什么协议字段。

采集文件可能含 Key、签名或会话数据，仅保存在 `.local-data/amap-sdk/captures/`；不要提交或公开。终端只打印事件种类，不打印内容。

## 当前环境限制（2026-09-24）

Windows x64，已启用虚拟化，adb 未检测到设备；用户没有安卓手机。Google 官方说明 Android 11 Google APIs 模拟器支持 ARM 转译，因此计划使用此路径。

下载 Android 30 Google APIs x86_64 r16 时，仓库 XML 声明大小为 1438186618 字节，下载地址的 GET/Range 实际返回 1431250880 字节。重新请求不同版本的官方 XML 后仍不一致。没有取消完整性校验或将不匹配镜像投入运行。已停止剩余环境下载，部分文件以 `.partial` 后缀保留；platform-tools、platform 33、build-tools 33.0.2 已通过官方清单 SHA-1 校验。

后续先解决镜像与官方校验信息一致性，再验证原生库加载。真实算路还需要上述 Android Key。当前没有可重放的真实算路样本。

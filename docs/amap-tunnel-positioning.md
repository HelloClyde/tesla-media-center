# 高德 App 隧道定位静态核对

> 当前方向（用户最新明确要求）：直接反汇编算法并移植 JS/Python，不再把完整 Android 原生运行时复现作为接入前提。下面的运行环境探测是历史记录。接入目标仍是高德逻辑移植，不能用自行设计的匀速外推代替。

2026-09-28，检查本地 `amap-release.apk`（17.00.0.2005，样本信息见 amap-app-analysis.md）。本次只检查能力和接口，不代表已移植、动态调用成功或接入 TMC。

## 已确认的证据

- `com.amap.bundle.location.floatview.LocationLogFloatView` 的状态 21 显示进入隧道、卫星信号被遮挡，并提示启用智能定位持续导航。
- `lib/arm64-v8a/libamaploc.so` 包含 `EnforceTunnelDR`、`TunnelMatching`、`MgcVdrHandler:vdrMgcFusMain:tunnelMatchMain`、`tunnel_main_route_weight`、`tunnel_rpe_offroute_conf`、`tunnel_alg_file/tunnel_finger_file` 等字符串。结合定位 UI 和信号接口，强烈支持存在隧道推算/匹配能力；字符串本身不能证明具体分支的启用条件或算法行为。
- `com.amap.location.locationkit.ILocationKit.setSignInfo(LocSignalBase)` 调用 `nativeSetSignInfo` 输入信号；`addPosEngineLocationInfoObserver`、`getLatestLocInfo` 提供结果观察和读取接口。这里 Sign 是定位信号接口名，不是网络安全签名。
- `ELocSignalType` 列出 GNSS、ACCE3D、GYRO、MAGNETIC、ORIENTATION、AIR_PRESSURE 等输入。`LocSignalGyro` 有 X/Y/Z 原生访问器，`LocSignalGnss` 有速度与速度精度访问器。接口支持这些信号，不意味着每个隧道算法都必须同时输入所有信号。
- `libamaptbt.so` 另有 tunnelRemainLen、tunnellane、tunnelexit 等隧道导航/播报内容，不能把这些内容等同于惯性定位算法。

## 对 TMC 的含义

这是 App 内部定位引擎能力，不是已经找到一个可请求的 HTTP 隧道定位 API。现有 Java 包装层将工作委托给原生代码，还没有追通初始化、传感器采集、隧道模型加载、算法选择与结果输出的完整调用链。

TMC 当前浏览器定位提供经纬度、速度、航向；车机是否对网页提供可用、持续的加速度/陀螺仪数据尚未实测。不能以旧 GPS 值冒充实时惯性输入。即使复用原生引擎，也需要验证输入数据、时钟、坐标系和恢复 GPS 后的融合过程。

后续追踪入口：ILocationKit 的创建及 nativeSetSignInfo JNI 实现 → libamaploc 的隧道模式入口与输入 → PosEngineLocationInfoObserver 输出；分别确认无 IMU 的沿路线推算和有传感器的融合定位，不能将前者标成实测惯性导航。

## 第二轮：接入条件核对

已读到以下包装层链路，但尚未动态证明它们在隧道模式下串联执行：

1. `LocationKitServiceAssembler.init()` 要求 Android Context 与配置，调用 `AmapLocationService.init()`。
2. `AmapLocationService` 初始化 `NativeLocationRequst`，传入环境状态、外部/内部存储路径和原生回调对象；后者调用 `nativeInit`。
3. `INativeLocationCallback.onRequestSensor(boolean, int[])` 是引擎请求传感器的回调契约。`AmapSignalFacade.addSensorEventListener()` 通过传感器管理器注册监听。
4. `SensorProvider.onSensorChanged()` 读取 Android SensorEvent 的类型、精度、时间戳和数值，再转交监听器。另有 `NativeLocationRequst.sendSensor()` → `nativeSendSensor()`，且受 `sInit` 初始化状态保护。尚未定位连接两者的具体监听器，不将其写为已追通。
5. 输出契约包含 `onBaseLocationChanged`、`onMatchLocationChanged`、`onGnssLoss`；新版接口另有 `PosEngineLocationInfoObserver.onPosEngineLocationInfoUpdate`。
6. `LocationKitService.setupLocationKitPointer(long)` 接收原生指针并包装为不拥有指针的 `ILocationKit`，不是一个可以独立创建引擎的 Java 工厂。

TMC 的 `web/src/stores/geoLocation.ts` 目前仅使用 `navigator.geolocation.getCurrentPosition`，没有惯性传感器输入。浏览器是否能暴露车机 IMU、可用采样率与时间戳质量均未知；不能据此断言硬件没有传感器，也不能将最后一次 GPS 速度当作持续测得的车速。

结论：暂不满足用户“确认没问题后接入”的条件，因此本轮没有修改实时导航或启用未经验证的推算位置。剩余验证是原生初始化和传感器中间连接、可回放的输入/输出测试，以及车机真实传感器数据验证。仅沿路线匀速推进是另一种降级方案，不等于移植高德惯性定位。

可复查二进制证据：`python tools/amap-app/inspect_tunnel_positioning.py .local-data/amap-app/amap-release.apk`。脚本只输出允许列出的定位标识和库校验信息，不输出内部密钥、完整二进制字符串或第三方源码。

## TMC 接入：使用车机持续返回的 H5 定位

用户随后明确确认：进入隧道后，H5 返回的数据仍随车辆变化，并要求直接接入。基于该设备行为，TMC 使用车机提供的定位结果，不再以前述原生引擎移植为接入前提。此确认不用于推断车机内部具体使用哪一种定位算法。

- 实时导航订阅 `watchPosition`，保留原有 `getCurrentPosition` 轮询作为兼容回退；退出导航、重新定位、切换到模拟导航和卸载页面时释放订阅。
- 新位置驱动地图、路线匹配、转向提示和 2D/3D 跟随；航向使用 H5 heading，导航栏显示 speed 换算后的 km/h。
- 两种采集方式按定位时间戳去重，拒绝倒序、过期和无效位置；静止但时间戳更新的位置仍有效。内部 `source: 'gps'` 是既有浏览器定位标记，并不能证明底层仅使用卫星定位。
- 连续有效定位间隔超过 15 秒后恢复时，允许重新匹配路线进度，纠正先前进度；真正停止更新时暂停提示，不编造新的实时位置。
- 不声称检测到了隧道，也不声称移植了高德原生惯性引擎。本次没有实现失联后的匀速外推。

验证：12 项定位接收、几何与航向单元测试通过；浏览器注入连续 H5 位置，验证 17.78 m/s 显示 64 km/h、过期样本不推进进度、2D/3D 切换和退出时清除定位订阅。车机隧道内持续更新行为来自用户确认。

## 第三轮：用户明确要求原生引擎，离线创建入口探测

上面的 H5 接收改动不满足用户要求的原生引擎接入。后续任务目标恢复为 H5 输入 → 高德原生引擎 → 引擎结果输出。

本次已从固定 APK 的 ELF 动态符号和反汇编定位：

- `liblocation_kit.so!CreateLocationKitInternal`，地址 `0x1f46c`。分配 0x50 字节对象，再调用 `0x1ede0` 构造函数；第一个参数被作为服务指针表使用，不是直接传入经纬度。
- 构造过程中 `0x1ee44` 开始读取参数表的多个偏移，将服务指针转交给 posEngine/locEngine。解析导入符号确认涉及日志、网络、线程工厂、时间、配置、文件/资源加载等服务。还存在地图数据提供者与工作路径等导入，具体调用阶段尚需追踪。
- `libamaploc.so!PosInterface4LocationBundleImpl::init` 地址 `0x5869cc`，参数类型包含 `DicePosWorkPath`、`IDataProvider`、`LocModeType`；内部转交引擎虚函数。
- 同类 `setSignInfo(PosSignalBase*)` 地址 `0x586a50`，同样会检查并转交底层接口，不是一个独立的经纬度计算函数。

新增 `tools/amap-app/probe_location_factory.py`，使用 Unicorn 执行真实 ARM64 工厂入口。仅实现有界内存分配和 memset，其余未知导入立即停止；使用空服务表探测依赖，不假造服务就绪或导航结果。运行结果依次经过 `_Znwm`、`memset`、`_ZnwmRKSt9nothrow_t`，停在 `_ZN9posEngine12setAlcLogPtrEPN3alc7IAlcLogE`。结果明确为 `engine_ready=false`、`position_output_verified=false`。

这次停点是探测器尚未装载/实现依赖服务，不证明原生引擎不能运行，也不证明日志服务就是唯一缺口。未绕过初始化，未将该探测器加入生产请求路径。下一阶段需要解析工厂服务表并装载实际引擎依赖，再验证配置、定位信号结构和结果回调；目前不能宣称 GNSS/H5-only 模式已获原生支持。

## 第四轮：原生依赖链接和内部服务创建成功

离线探测器现在装载并重定位四个 APK 原生库：location_kit、amaploc、loc_base、libc++_shared。可选加载本机 Android build-tools 33.0.2 附带的真实 ARM64 Bionic libc；所有库按 SHA-256 固定。未打包或提交第三方二进制。

执行的是原生服务注册函数和原生 C++ 容器实现。探测环境仅提供有界堆、单线程锁/TLS/once、时钟、动态库枚举等运行时机制；未知接口停止。文件系统为空，缺失库返回加载失败，不伪造工作目录、地图数据或定位输出。该环境尚不支持导航工作线程调度，不能用于生产。

验证中发现：直接跳过 ELF 全局初始化会在构造期间触发 `std::overflow_error`；这属于不完整装载环境，不能作为定位算法不支持 H5 的证据。补齐初始化流程后，163 个初始化函数完成，真实内部服务创建函数 `libamaploc.so+0x87fd98` 返回 `1`，其全局指针 `+0xa542b0` 非空。外层工厂也正常返回。探测器仍明确报告 `engine_ready=false` 和 `position_output_verified=false`。

继续调用模块启动入口 `liblocation_kit.so+0x1f0c4` 后，当前准确停点为 `libamaploc.so+0x5676dc`：读取空的消息线程工厂虚函数表。反汇编链为 `+0x5676d8` 调用 `+0x882338` → 读取全局 `+0xa54380` → `+0x5676dc` 解引用。对应写入口 `+0x88232c` 的导出符号是 `posEngine::setMessageThreadFactory(amap_app::IMessageThreadFactory*)`，与工厂参数服务表中的消息线程工厂一致。

因此下一步应提供真实可调度的 IMessageThreadFactory 适配，或定位 App 现有线程工厂实现并装载。不能通过让线程创建返回成功但不执行消息来宣称导航已启动。之后仍需工作路径、地图/路线输入与 H5 信号回放、位置输出验证。

复现命令（在项目根目录，研究环境安装 unicorn 2.1.4、pyelftools 0.33）：

```sh
python tools/amap-app/probe_location_factory.py .local-data/amap-app/amap-release.apk \
  --bionic .local-data/amap-sdk/android-sdk/build-tools/33.0.2/renderscript/lib/intermediates/arm64-v8a/libc.so
```

本轮证据保存在本机 `.local-data/amap-app/location-factory-probe.json`。当前不修改 TMC 导航为原生模式，不将已有 H5 跟随能力视作原生惯性引擎接入完成。

## 第五轮：原生线程工厂与独立配置入口

已定位并装载 APK 的 `libamapmain.so`，执行其 `nativeInitMessageThreadFactory`（`+0xe05a0`），将真实工厂返回值放入外层创建参数的 `+0x38`。当前总计完成 227 个 ELF 初始化函数。

新增 `native_thread_scheduler.py`：在共享内存中执行原生 ARM64 工作线程，保存各自寄存器、栈和 TLS，提供有界协作调度及 futex 等待/唤醒。探测中创建了 6 个线程，其中 5 个实际执行到等待阶段；第六个在主线程遇到下一处缺失依赖时仍排队。不是只返回线程创建成功。两线程执行 ARM64 指令修改共享计数器的独立测试通过。该调度器仍是研究工具，不能作为完整 Android 运行时用于生产。

另确认模块的配置入口 `liblocation_kit.so+0x1ef28` 与创建入口使用不同参数表。`+0x1f03c` 读取配置表，已对照 PLT 重定位确认：

| 配置偏移 | 原生接收接口 |
| --- | --- |
| `0x18` | `posEngine::setDataProviderSD` |
| `0x20` | `posEngine::setDataProviderHD` |
| `0x28` | `posEngine::setWorkPath`、`locEngine::setWorkPath` |
| `0x30` | `posEngine::setLocModeType` |
| `0x50` | 可选 `posEngine::setIMLFactory` |

探测已补上配置调用，空配置返回 `1`，但这不代表依赖有效或引擎就绪。继续启动仍在 `libamaploc.so+0x866f38` 解引用空对象。第五轮最初将其误判为工作路径；第六轮通过导出符号核对纠正：全局 `+0xa54350` 对应 `setDataProviderSD`，实际缺失的是标准地图数据提供者。`setWorkPath` 则写入 `+0xa54368`。配置表字段解析仍有效，但不能据此推断本次故障对象类型。

下一步追踪工作路径接口对象的原始构造和文件服务，再推进输入信号与输出回调。当前报告依然为 `engine_ready=false`、`position_output_verified=false`；尚未接入 TMC 生产导航，尚无原生惯性位置输出。

## 第六轮：纠正故障对象，执行原始地图数据模块工厂

对 `libamaploc.so` 动态符号逐项核对：`+0x8822a8` 是 `setDataProviderSD`，写 `+0xa54350`；`+0x8822f0` 才是 `setWorkPath`，写 `+0xa54368`。故障函数 `+0x866e64` 把参数 x2 保存到 x23，缺省时调用 `+0x8822b4` 取得 SD 数据提供者。前一轮关于工作路径导致当前崩溃的推断不成立。

现已从 App 装配库得到原始调用链：

1. `libassembly_kit.so+0x6bce8` 经 PLT `+0x103b90` 调用 `dice::data_createModulePtr()`，实际导出位于 `libamapr.so+0x15e4460`。
2. 装配流程配置数据模块后，在 `+0x6be18` 调用数据模块虚表 `+0x160`，通过 `+0x6d7c8` 将结果保存在依赖对象 `+0x80`。
3. 定位模块装配在 `+0x6c0fc` 调用 getter `+0x6d754`，将该结果写入配置表 `+0x18`，传入定位模块配置入口。
4. 数据模块的 `+0x160` 虚方法是 `libamapr.so+0x15e4cec`，读取内部对象的 `+0x168`。当前工厂创建后这里为零，仍需执行数据模块配置。装配库调用的配置虚表槽 `+0x140` 对应 `libamapr.so+0x15e48a0`，下一步从此继续。

探测器增加 `--data-module`，按固定 SHA-256 装载真实 `libamapr.so`。598 个原生初始化函数完成，真实数据模块工厂成功返回对象，随后实际调用 SD getter 返回零。探测器据此报告 `data_provider_not_initialized` 并停止，不把空提供者塞入定位引擎，也不把工厂成功解释为地图数据就绪。

复现：在前述命令末尾加 `--data-module`。报告保存在本机 `.local-data/amap-app/location-data-module-probe.json`。这条路径尚未进行数据模块配置、地图内容加载、定位信号注入和位置回调验证；原生惯性导航接入仍未完成。

## 第七轮：执行地图模块配置与启动

确认配置槽 `+0x140` 只复制配置；提供者实际在启动槽 `+0xe8`（`libamapr.so+0x15e45d4`）中创建。该入口调用 `+0x15e5104`，后者在 `+0x15e5230` 调用提供者工厂 `+0x15f1618(1, 0)`，将结果保存到内部对象 `+0x168`，随后配置其路径等参数。

探测已按此顺序调用：真实数据模块工厂 → 配置入口 → 启动入口。配置结构按装配库的 `0x160` 字节初始化，`+0x158` 写入原始值 `0x1ed`，字符串暂为空，与研究环境的空文件系统一致。配置返回 `1`，不解释为地图内容已加载。

启动进一步触及 `libamapnsq.so` 的真实导出 `irjzjyiyymeygpjmkcsh`，现已按固定哈希装载该库。补充了有界匿名 mmap、现有保留区内 MAP_FIXED、mprotect、完整映射 munmap、匿名映射名称记录，以及 Linux CLOCK_MONOTONIC_COARSE。文件映射和未知系统调用仍停止，不伪造文件内容。

最新执行越过了上述缺口，当前停止在真实 Bionic libc `+0x98348` 调用 `pthread_setspecific(0, ...)`：该 key 尚未在探测器 TLS 注册表创建。记录为 `Unknown TLS key`，未将未知 key 静默当作有效项。需继续核对 Bionic 内部分配器初始化与探测器 TLS/分配器的边界；这是运行环境缺口，目前不能据此断言导航引擎不支持该输入。

当前仍无 SD 提供者就绪或原生定位输出证据，尚未修改 TMC 为原生导航模式。

## 第八轮：统一内存分配，取得真实 SD 提供者

新增原生栈回溯，确认前一轮 TLS 错误的调用链经过 `libamapnsq.so+0x8daf8`：它调用 realloc，而探测器此前仅接管 malloc/free，导致研究堆的指针进入 Bionic 自身分配器。现补齐 calloc/realloc，共用分配记录，扩容保留原有数据，拒绝重新分配未知指针，不再让两套分配器混用。没有将未知 TLS key 直接放行。

继续执行补齐真实主机 BOOTTIME 时钟、空研究文件系统的 stat/access 缺失返回及独立虚拟 umask 状态。最新报告证实：数据模块启动返回到调用者，原生 SD getter 返回非零 `0x30cce50`；定位模块配置接收该指针，实际启动越过 `libamaploc.so+0x866f38` 原停点。

当前新停点为定位模块启动中的 `mkdirat(AT_FDCWD, "pb_data", 0755)`。探测器尚未提供可写工作目录，所以明确停止，不伪造目录创建成功。下一步需要提供隔离的工作文件系统及其元数据、读写语义，再继续追踪地图资源和定位输入输出。

上述指针非零仅证明提供者对象创建和传入成功，不代表地图内容加载完成、引擎就绪或惯性位置已输出。`engine_ready` 与 `position_output_verified` 继续保持 false。

## 第九轮：隔离工作文件系统与文件工厂缺口

新增 `native_probe_filesystem.py`，使用独立内存文件系统，不访问主机路径。支持目录创建、访问权限检查、ARM64 stat 元数据、文件创建/读写/偏移/关闭，设置文件数、句柄数及内容大小限制。未知标志和操作明确停止，缺失文件保持 ENOENT，不生成虚构地图资源。测试覆盖目录元数据、写入覆盖与读回、追加/截断、只读权限、关闭后的无效句柄、缺失父目录和主机文件不可见。

重新执行原生启动，`mkdirat("pb_data", 0755)` 已实际创建研究目录 `/pb_data`，引擎越过该调用。新停点是 `libamaploc.so+0x867280`：调用 `+0x88268c` 取全局 `+0xa543a8`，再解引用其虚表。已结合导出符号确认 `+0x8826d0 posEngine::setFileFactory(amap_app::IFileFactory*)` 写入同一全局，因此此处缺少文件工厂对象，不是目录创建失败。

Java `com/amap/jni/app/InterfaceAppImpl.java` 的 `initFileFactory(long)` 接收外部创建的原生指针，`getFileFactory()` 只返回该指针。下一步应追踪这个原始文件工厂的创建和装配，并连接已实现的隔离文件系统。当前仍无定位输出。

## 第十轮：排除存储模块误接，追到启动接口容器

单独反编译 `com.autonavi.jni.startup.AmapStartup`，确认 `CoreAbility` 中 `fileFactory` 与 `amapStore` 是两个独立 long 字段，默认均为零。`SandboxManagerProxy.nativeCreateAmapStore()` 位于 `libamapstore.so+0x83f28`，转到 `+0x34650` 创建 24 字节模块对象；其虚表含大量空的模块生命周期方法。因此没有将这个存储模块对象当作 IFileFactory 注入。

从 `libamapmain.so` 的 `fileFactory` 字符串交叉引用追到 `+0x84a58` 调用 `+0xe64a4`，返回空时进入带 `fileFactory` 字符串的断言分支 `+0x84c40`。`+0xe64a4` 从全局 `+0x120480` 取得接口容器，再读取容器 `+0x80`。另一个字符串引用 `+0xde5d8` 位于启动参数 JNI 字段描述构造中。后续应追接口容器的填充及 CoreAbility 原生装配，不再沿 amapStore 模块工厂猜测。

探测报告现针对已核对的停点额外读取真实 `+0xa543a8` 全局指针：重跑值为零，报告 `missing_dependency=amap_app::IFileFactory` 和 setter/getter 证据。该诊断没有补空实现、绕过调用或改变引擎就绪标记。原生文件工厂的创建入口仍未找到，仍无定位输出。

## 算法移植第一轮：模式选择原语

用户要求直接静态分析后以 JS/Python 实现。已停止继续扩充完整原生运行环境，新增 `tunnel_mode_selection.py`，翻译固定样本 `libamaploc.so+0x45dfbc` 的分支逻辑。该函数包含 `EnforceTunnelDR` 日志调用，返回三项选择结果，而非经纬度：

- 上下文不存在或输入结构 `+0xd0` 状态值不为 5，返回原三项结果。
- 当前算法查找失败或类型低 8 位为 2，返回原结果。
- 按候选缓冲区的原始顺序查找第一个类型低 8 位为 2 的有效算法，返回 `(1, candidate_id, 0)`；没有匹配项则保持原结果。
- 数值 5、2 的完整枚举名称尚未确认，移植代码保留数值，不擅自命名为“已进入隧道”等状态。

新增 `verify_tunnel_selection_native.py`，从固定哈希 APK 提取这段原始 ARM64 指令，在独立小内存环境执行；仅算法注册表查询和日志是测试夹具。200 组确定性随机输入比较原始指令与 Python 结果，全部一致。该对照不加载地图模块，不模拟整个 App，也不证明位置推算正确。

定位到另一条日志 `MgcVdrHandler:vdrMgcFusMain:tunnelMatchMain, t = %.3f, start = %d , end = %d`，字符串地址 `+0x8a33d`，引用在 `+0x6acca4/+0x6acca8`。下一步沿此处追踪隧道匹配输入、状态更新和数学公式。模式选择移植尚未启用到 TMC，实际位置推进、定位恢复校正及页面接入都未完成。

## 算法移植第二轮：隧道匹配调用与局部坐标转换

`+0x6acc44` 按输入 w1 分支：值为 1 时记录上述 tunnelMatchMain 日志并尾调用 `+0x6ae6e0`；值为 2 时检查两个计数差（14 和 76），符合条件再调用 `+0x6aeb34`。尚未确认这些计数的时间单位，不能解释成秒或直接作为 TMC 超时阈值。

`+0x6ae6e0` 的匹配前处理调用 `+0x69f404`：从输入结构 `+0x18/+0x20` 读取两个 double，从状态 `+0x108/+0x110` 读取局部原点，从 `+0x120/+0x128` 读取轴缩放。算法为 `(输入角度 * 0.0174532925199433 - 原点弧度) * 轴缩放`，其中乘减使用 ARM64 FNMSUB 融合运算。该常量实读自 `+0x7bc78`，没有以其他常量替换。

已移植到 `tunnel_local_coordinates.py`。`verify_tunnel_coordinates_native.py` 执行这 8 条原始指令及实际常量，与 Python 比较 1000 组输入，全部通过，最大绝对差约 `1.47e-9`（Python 无 math.fma 时的舍入差）。这只验证局部坐标数学原语；轴顺序、缩放初始化、完整路线匹配仍需确认。

随后 `+0x6ae780` 调用 `+0x695e64`，传入局部坐标、候选区间、输出结构及 double 常量 20；成功后进入第二阶段 `+0x6b45d0` 和历史匹配结果处理。下一步追踪 `+0x695e64` 的筛选和投影计算，并确认原点/缩放的建立方式。没有把常量 20 擅自认定为距离或速度阈值，也未用该原语单独冒充完整导航。


## 算法移植第三轮：候选区域与边界距离

`+0x695f40` 按 0x68 字节步长遍历候选项，每项 `+0x50` 为二维顶点向量，调用 `+0x691afc` 计算定位点到区域的距离。严格小于才替换最优项，因此并列保留首项。`+0x695e64` 在写出最优候选后判断距离是否不超过输入阈值；上层传入 20，单位仍取决于局部坐标缩放。

距离逻辑：少于三个顶点返回 DBL_MAX；`+0x6918f4` 判定内部时返回零，否则遍历闭合边界，调用 `+0x691bf4` 求线段投影，再调用 libc hypot 求距离。已核对 PLT `+0x9f4050` 的重定位 `+0xa28b68` 确为 hypot。线段长度平方小于 `1e-6` 时退化到起点，投影参数限制在 [0,1]。

内部判断保留原始整数行为：`+0x6919b4` 的叉积经 FCVTZS 转为有符号 32 位整数，检查各边符号是否一致，非零更新阈值为 `1e-7`。这不是通用凹多边形算法，近边界行为也不能直接用浮点点在多边形库替代。

新增 `tunnel_polygon_matching.py` 和 `verify_tunnel_polygon_native.py`。验证执行原始 ARM64 内部判断、叉积、投影和距离控制流，仅替换 libc hypot；1036 组原始指令/Python 对照全部通过，本轮最大差为零，包含顺逆时针、边界、近边界、重复点、退化区域及随机矩形。额外 Python 检查覆盖候选并列、距离阈值相等/超出、空候选；候选选择本身尚未做原始指令差分。此有限样本不保证所有融合浮点舍入边界等价。

尚未完成：候选区域的数据来源和构造、局部坐标轴/尺度初始化、匹配后的状态融合与位置输出、TMC 页面接入。上述三个数学/选择原语不能称为完整惯性导航，尚未启用到车机导航。

## 算法移植第四轮：历史匹配统计

第二阶段 `+0x6b45d0` 是共享尾调用片段，跳入 `+0x69dca0`，后者从环形缓冲区收集 0xc0 字节记录，调用 `+0x69de18`。此阶段不能仅按当前点到区域的距离替代。

`+0x69de18` 在滑动窗口中调用 `+0x6a892c` 比较两个 double 历史序列。两序列必须非空且等长；各自减去首项，调用 `+0x69f424` 反复加减 360 将值归入 [-180,180]，再计算两序列差并同样归一化。差序列送 `+0x6a889c` 求总体标准差；各序列送 `+0x6a8908` 求欧几里得范数，计算逐项乘积除以两范数后的和。接受分支使用标准差严格小于 20、常量 `+0x7c3e0=0.8`。零范数产生 NaN 的 ARM 条件码行为仍需完整差分，未以普通 Python 比较擅自替代。

新增 `tunnel_history_matching.py`，保留这部分统计和角度归一化。新增 `verify_tunnel_history_native.py` 对标准差及范数的原始指令进行 2010 次对照，全部通过。这只覆盖两个无依赖数学原语；整段历史匹配、序列字段含义、候选构造、状态融合和实际位置输出仍未验证，尚未接入 TMC。

## 算法移植第五轮：接受分支及后续状态追踪

`verify_tunnel_history_native.py` 现直接执行 `+0x6a8b58..+0x6a8b70`，额外完成 36 组条件码边界对照（20、0.8 的相邻 double、NaN、无穷）。确认接受条件为标准差严格小于 20 且相关值严格大于 0.8；NaN 拒绝。新增 `accepts_statistics`、`history_matches`，但整个容器/历史数据流未做差分，不能据此声称历史匹配完整验证。

回溯 `+0x6ae7bc` 的第二阶段调用后，成功结果进入 `state+0x7d8` 的 0x150 字节记录向量。恰好两条时比较记录 `+0x30` 和 `+0x50` 的差，绝对差以 15 为分界，计算并更新 `state+0x808`；若 `state+0x890` 的绝对值低于某阈值，还从候选 0x48 字节记录的 `+0x18` 取值进行初始化。三条及以上时另走计数分支，累计更新 `state+0x7d0`、`+0x7c8` 和标志 `+0x7cc`。字段语义仍未知，不能将这些数值直接当作经纬度、秒数或速度。

`+0x69c018` 已确认只是结果结构拷贝（头部字段、嵌套对象及 0x38 字节尾部），不是位置融合函数。下一步应继续沿 `+0x6aea00` 后的结果消费和 `state+0x808/+0x890` 的读取追踪，避免在拷贝函数上寻找不存在的数学计算。TMC 接入未完成。

## 分支身份核对：当前数学原语属于地磁辅助匹配

沿结果消费追踪确认 `+0x6aead8` 调用 `+0x6a9388`，其日志字符串 `+0x94c41` 明确为“地磁信号 %lf,%f,%f,%.3f”。它读取结果 `+0x18/+0x20/+0x28`，经仅保存三项 double 的 `+0x767a68`，传入 `+0x76dd28` 打包并调用下游虚表 `+0x10`。这里不是新发现的通用坐标变换。

进一步读取原始日志：`+0x94c71` 为“距离和索引的平均值”，`+0x97221` 为“根据定位点确定初始惯导距离”。因此此前 `MgcVdrHandler` 历史匹配应明确标注为地磁辅助分支，而不能当成仅需 H5 经纬度/速度/方向的完整普通车辆惯导算法。现有移植原语及其差分证据仍有效，但输入来源没有闭合，不得直接启用到 TMC。

候选输出门槛 `+0x6aeabc` 使用常量 `+0x7c558=10000000.0`，随后才消费匹配结果。原始库还存在独立线索：`TunnelCorrection`（文件偏移 0x97c25）、`TunnelMatching`（0x8c1c2）、`carplay_tunnel_fix`（0x98368）、`@VDR_RUNNING`（0x9a36d）、`VDR REROUTE` 多个方向分支。下一步优先定位这些调用，区分普通 VDR/车载输入路径与地磁指纹路径；不继续将地磁序列直接替换为浏览器 heading。

## 普通 VDR 线索与交叉引用校正

`carplay_tunnel_fix` 快速扫描原有两处命中。逐条反汇编排除 `+0x7e36dc/+0x7e36f8`：中间重新 ADRP 写入 x1，因此后面的 ADD 实际指向 0x8c368，不是 carplay 字符串。唯一已确认引用 `+0x7f10b4/+0x7f10b8` 是向结构 +0x1290 注册配置名称，不能当成车辆惯导算法入口。

新增 `find_native_string_refs.py`，通过 Capstone 寄存器写集跟踪 ADRP 页地址，寄存器重写和控制流边界时失效，避免旧扫描跨寄存器覆盖误配。工具只覆盖局部基本块内直接引用；未找到不代表不存在间接调用。

`TunnelCorrection` 有效引用在 `+0x469da4/+0x469da8`，调用算法注册表 getter `+0x820388`，记录日志后返回 `(1, candidate_id, extra)` 形式的选择结果，前置依次尝试 `+0x469dec`、`+0x469ec8`。这仍属于算法选择层，未发现这里直接计算经纬度。接下来需沿候选算法类型及其位置生产者定位普通 VDR 核心；当前 TMC 仍未启用这些研究代码。

## 普通 VDR 状态分发入口已定位

区别于地磁分支，原始 `@VDR_RUNNING\n` 字符串引用位于 `+0x77bf80/+0x77bf84`，所属函数 `+0x77bf70`；`@VDR_RUNNING_UNSTABLE` 引用位于 `+0x77bd2c/+0x77bd30`，所属函数 `+0x77bd0c`。直接分支扫描及反汇编确认两者均由 `+0x77b628` 状态分发函数调用。

已证明的状态映射：对象 `+0x2c` 为 0x10 时调用 RUNNING；为 8 时调用 RUNNING_UNSTABLE；为 0x20 时调用带 `@VDR_RETAINING` 日志的 `+0x77bfc4`。其他 2、4 状态尚未完整命名。RUNNING 本身只检查输入 `+0x278`，为零时调用 `+0x77ae18` 切换至 0x20，并传入原因位 0x10；它不是位置积分函数。

真正重要的上游：`+0x77b628` 在状态分发前读取对象 `+0xa78` 的组件，调用其虚表 `+0x38`，同时传递本对象 `+0x1c0/+0x440/+0x430`，随后调用 `+0x7b4a78`。需要追踪此组件的构造和虚表，才能找到位置生产者。没有把状态机分支当成完成的惯导实现。

另确认 TunnelCorrection 的候选类型 getter 是对象 `+8` 所指结构的 `+0x38` 组件虚表 `+0x10`，返回低字节与 2 比较。该选择层和 VDR 位置生产组件之间的对应关系仍需验证。目标继续保持未完成。

## 普通 VDR 组件间接调用已解析

扫描对象 +0xa78 的实际写入：`+0x77a9dc` 分配 0x790 字节，`+0x77a9e8` 调用构造函数 `+0x776c60`，`+0x77a9f4` 将组件保存到 +0xa78。构造函数 `+0x776c7c..+0x776cac` 安装虚表 `+0xa18558`。ELF 重定位证明虚表槽 +0x38（地址 +0xa18590）指向 **+0x777ba0**，所以此前状态分发前的间接调用已闭合。

`+0x777ba0` 对当前结构及 0x138 字节历史记录逐项调用 **+0x78b9b8**。该函数首先调用 `+0x7cf360` 计算输入 +0x260 与 +0x264 两个 32 位字段之差，再调用 `+0x764628` 转成 double 并乘以常量 +0x7c0b0。随后调用 +0x7cf454、+0x7cf408、+0x7cf380，分别更新对象 +0x60、+0x48 及对象开头的数据，通过矩阵表达式辅助函数执行。已找到真正的状态推进调用路径，数学表达式和各字段物理含义仍需展开。

已验证调用链：77b628 → [a78].vtable[38] → 777ba0 → 78b9b8。这里的“闭合”只指上述间接调用解析，不表示整个导航输入输出或 TMC 集成已完成。

## 普通 VDR 状态表达式首段移植

`+0x78b9b8` 的第一段写入目标为状态 +0x60，经过 +0x78b964 → +0x7934dc 组装表达式，再经 +0x793518/+0x793560 求值。标量尾元素的实际计算在 +0x7937e8/+0x79382c，可写为 `((a+b)+s*c)+(w*d)*t2`，全部为分离的乘加。a、b、c、d 的物理含义仍待沿构造追踪；其中 b 的构造经过 +0x5a5c5c → +0x37b388 的矩阵运算，不能简单等同于原始加速度。

新增 vdr_state_expression.py；verify_vdr_expression_native.py 执行这两段原始函数，1000 组受控操作数与 Python 逐位相同。该验证覆盖算术及存取位置，不覆盖输入来源或完整向量推进。已确认上层将 0.5 和时间差平方带入表达式；尚未完整验证物理单位、坐标系和矩阵含义，未启用到 TMC。

## VDR 前置矩阵乘法已核实

`+0x5a5c5c → +0x37b388` 最终进入 `+0x37b754/+0x37b788`。该运算确为 3×3 列主序矩阵乘三维向量，每行严格按 `m[r]*v[0] + (m[r+3]*v[1] + m[r+6]*v[2])` 求和，使用独立 FMUL/FADD，不是融合乘加。已加入 `vdr_state_expression.transform_vector`。

扩展 `verify_vdr_expression_native.py` 执行原始矩阵点积指令，1000 组三维矩阵向量乘法（3000 行输出）与 Python 完全一致；原有 1000 组状态算式对照同时通过。验证证明了存储顺序和求和顺序，尚不证明矩阵来自哪一种姿态坐标系。

前置修正量 +0x7cf454 从输入 +0x1c8、+0xd8、+0x120、+0x1e0、+0x1f8 组装表达式；+0x7cf408 使用对应的 +0x1b0、+0x48、+0x90 及同一尾部字段。下一步展开 +0x7cfe5c 及这些字段的写入者。H5 字段适配、完整状态输出与 TMC 接入仍未完成。

## 输入修正量表达式已展开

+7cfe5c 分配三维结果，+7cff50 先复制基向量，再通过 +7cffbc/+7d0020 加入第一项；+7cfee4 随后加入第二项。两项经 +5a5998 构造，调用 +38e4c8/+38c334 计算两个输入向量之差，再进行已验证的 3×3 矩阵乘法。+38c3f8/+38c430 明确按首指针减次指针，+7d0108/+7d014c 按新乘积加已有输出。

由 +7cf454 调用点的栈布局推得：结果 = input[1c8] + input[d8] × (state[78] - input[1e0]) + input[120] × (state[90] - input[1f8])，求值按先第一乘积加基值、再第二乘积加前一结果。对应 +7cf408 使用 input[1b0]、input[48]、input[90]，其余引用结构相同。偏移均为原始对象布局，不代表已确认的物理量名称。

新增 corrected_input 组合实现，明确注明整函数差分尚未完成。各项究竟是传感器观测、校准状态还是其他运动量，仍需追踪写入；未将浏览器 speed/heading 直接填入这些未知字段。TMC 接入仍未完成。

## 整段输入修正差分通过，并纠正 SIMD 舍入假设

新增 verify_vdr_input_native.py 直接运行原始 +7cfe5c 及其完整子调用，不替换算术、不 hook 子函数。首次运行出现约 1e-12 的差异，沿 +5a5a38 → +37b530/+37b59c 查明前两行使用 SIMD FMLA，累加顺序为 fma(m2,v2,fma(m1,v1,m0*v0))；只有第三行使用之前验证的标量 m0*v0+(m1*v1+m2*v2)。因此上一节“全部独立 FMUL/FADD”只适用于单独执行的标量尾路径，不适用于完整三维乘法。

增加 transform_vector_simd，保留标量工具用于原始标量函数对照。Python 无 math.fma 时使用高精度 Decimal 保留融合后一次舍入。修正后 1000 组完整输入修正调用（含向量差、两个矩阵乘法、基值累加）与原始函数逐位一致。此验证仍只使用有限输入，尚未验证真实传感器数据来源及完整导航；TMC 未接入。

## 状态推进的样本入口继续上溯

已找到输入修正字段更新函数 +7cf4a0：在已有数据时先使用旧参考值修正 input[168]、[1b0]、[1c8]，随后将两组新参考向量复制到 [1e0]/[1f8]。实际样本积分入口 +7cf594 由 +773adc 调用，读取两组样本各自的 +0x10/+0x14/+0x18 三个 float，并读取 +0xc 的 32 位时间字段。+7d2d90 将三项 float 转 double，不能把一次 ldr d0 错读成原生 double 观测。

+773adc 还计算首组三维样本的欧几里得模长最大值，并维护时间差最大值，随后按标志决定是否调用 +7cf594。入口上溯链为 +77c358 → +7dbebc → +773adc → +7cf594，其中 +77c358 将时间写入主对象 +0x24，并转交主对象 +0xf20 子组件。另一路 +7745fc 从相隔 0x20 字节的成对记录调用 +773adc；当时 w3=0，仅存储不积分。

这证明当前普通 VDR 路径消费成对的三维浮点样本及时间，而非直接消费 H5 经纬度。样本的传感器类型和其他可用车载输入支路仍需核实；尚未认定必然需要某种特定传感器，也没有伪造这些输入。完整输入输出与 TMC 接入未完成。

## 成对样本入口追到接口虚表

直接调用上溯：+7811b8 在 +781258 调用 +77c358，保留第三、第四参数为两组样本；第二参数是复制到栈上的定位类记录（从原记录 +0x10 拷贝 0x68 字节，并设置 +a17ec0 虚表）。这是定位记录与两组运动样本并行进入的接口，不能把三者合并成一份 H5 位置对象。

ELF 重定位确认 +a18ae8 → +7811b8；接口调整桩 +7812d8 将 this 减去 0x9d88 后跳入 +7811b8，其槽位位于 +a18ba0。构造代码 +77f624..+77f648 安装主虚表 +a18a80，并将其 +0x110（即 +a18b90）写入子接口；因此此接口 +0x10 槽正是上述成对样本方法。已将数据入口的多重继承调整关系闭合，下一步找持有该接口并调用 +0x10 的传感器分发对象。

当前证据表明有一份定位类记录和两份三维运动样本，但运动样本的类型标签尚未确认。未虚构加速度/角速度枚举，也未将 H5 速度或航向强塞入未知结构。TMC 接入尚未完成。

## 分发对象查找：排除不相关持有者

核对 +77f5dc 构造函数，主对象 +0x9d88 的三槽接口在 +77f648 安装，并将构造参数 x1 紧邻存储到 +0x9d90。+0xa4f8 子组件由 +7c80b0 创建，保存构造参数 x2/x1 于 +0x30/+0x38，保存主对象指针 x3 于 +0xb0；它持有主对象而不是直接持有 +0x9d88 接口，不能仅凭这一引用认定它是成对样本分发方。

对完整可执行段进行两种立即数扫描：MOVZ 0x9d88 仅命中构造位置；ADD 0xd88 的命中没有直接发现这个接口的注册调用。这个阴性结果只说明不能用这两种简单地址形成模式定位持有者，不排除通过继承指针、成员偏移或其他计算注册。下一步应跟随接口邻接管理器指针 +0x9d90 的使用及初始化入口，而不是重复扩大同一关键词搜索。

没有新增传感器类型结论，没有更改 TMC 运行路径。现有已验证算术保持不变；完整惯导移植仍未完成。

## 管理器方向判定：+9d90 是消息输出路径

核查 +9d90 的多处真实读取后，应纠正其可能是输入分发方的猜测：+780910 构造栈上消息（虚表 +a18be0）并通过该对象虚表 +0x10 发送；+780a1c 构造类型值 0x68 的消息并同样发送；+7823ac 辅助构造类型 0x69 的消息。+780f6c 和 +782370 也使用同一发送槽。当前证据支持它是消息输出/通知管理器，不能据此建立传感器输入链。

补查基类 this+0x30 下可能的接口偏移 0x9d58，MOVZ 模式无命中。以上仅排除两条定位策略，不证明样本接口未注册。下一步应从主对象创建调用及输入消息入口反向关联，避免继续围绕输出管理器查输入来源。数学原语验证未变化，TMC 集成仍未完成。

## 真正的成对样本分发已接通

从 VDR 构造函数 +77f5dc 的调用者追踪，+76cf80 将 VDR 放在外层对象 +0x970，故输入接口实际外层偏移为 0xa6f8。+76d088..+76d094 将该接口注册到 +0x8f0 组件的 +0x68 监听向量；+76d0a4..+76d0ac 又经 +76d118 注册到外层 +0xc728 组件的 +0xc8 向量。此前只搜相对 VDR 的 0x9d88 因而漏掉此注册。

+0xc728 组件由 +78897c 构造。其输入函数 +7889ec 检查记录 +8 类型值，处理 0/1/2；只有类型 1/2 进入 +78870c 取配对结果。+788ab0 遍历监听列表，+788ac0/+788ac4 将结果 +0x78/+0x98 的两组样本作为 x2/x3，结果起始定位记录作为 x1，通过监听接口虚表 +0x10 调用。

由此闭合：+7889ec → +78870c 配对 → vtable[10] → +7812d8 → +7811b8 → +77c358 → +7dbebc → +773adc → +7cf594。类型 1/2 的枚举物理含义及样本来源还要上溯；已有证据足以排除“没有分发入口”，但仍不证明仅 H5 定位即可满足原算法。未启用 TMC。

## 输入消息广播到配对器的链路确认

ELF 重定位 +a18ce0 → +7889ec，证明配对器使用虚表 +0x10 接收输入消息。外层构造函数通过 +76da30/+7683a4 注册多个子组件，包含 +0xc728 配对器；外层 +76d344 在处理自身消息后调用 +768434。后者遍历外层 +8/+0x10 指针区间，对每个注册组件调用虚表 +0x10，并原样传递同一个消息指针。因此配对器的无直接调用是虚表广播所致，并非入口丢失。

+7889ec 的类型 0 分支经 +78a290 拷贝消息 +0x10 起的 0x68 字节，重建定位记录；类型 1/2 分支经 +78a2ac 保留样本字段及 +0x1c 标志。类型数值属于此内部消息系统，不应直接套用 Android Sensor.TYPE_* 枚举；需要继续追外层 +76d344 的消息构造者或 JNI nativeSendSensor 的映射。

当前已贯通外层广播 → 配对器 → VDR 接口 → 推进函数。缺少输入类型映射、真实数据适配、其余状态计算和端到端导航验证，目标仍未完成。

## JNI 空入口排除与精确取样移植

`libloc_base.so` 的 JNI 注册表将 `nativeSendSensor` 指向 +d7818；它转换数组后调用 +dc330，而 +dc330 只有 RET。因此这个版本不能沿该入口建立实际 VDR 输入链。Java SensorProvider 确实传递 Android 类型、accuracy、timestamp、values，但尚未证明它们如何进入 libamaploc 的内部 1/2 消息。

进一步反汇编 +7885e4、+78870c：类型 1 入队 this+10，类型 2 入队 this+28。配对器分别以同一目标时间调用 +788568。输出记录 +78 来自类型 2，+98 来自类型 1，故交给 VDR 的 x2/x3 顺序是 2/1，不能按枚举顺序猜测。其物理传感器含义仍未确认。

+788568 是精确时间戳查找，不是插值：比较记录 +c 的 32 位时间，命中第一条相同记录后复制 +8..+1c 字段，并删除队首至命中记录（含）；未命中时队列和输出不变。已移植至 tools/amap-app/vdr_sample_queue.py。verify_vdr_sample_queue_native.py 运行原始函数及其队列移动/析构代码，应用原 ELF 相对重定位，不使用函数钩子；1000 组空队列、重复时间、命中/未命中和 32 位边界案例全部一致。

此处验证的是样本取队列过程，不能代替完整惯导或证明 H5 输入兼容。实际传感器映射、完整状态推进和 TMC 接入仍待完成。

## 外部消息到 VDR 样本的真实转换与偏置校验

+76a61c/+76a628 分别调用 +769cbc/+769da8。前者要求外部消息 +8 == 2，读取 +40/+44/+3c 三轴，任一绝对值大于 1e-6 才转发，将主值及 +4c/+50/+48 三项备用值乘 float32 9.800000190734863（常量 +a076c），生成内部类型 1。后者要求外部类型 3，读取 +40/+44/+3c，备用值 +4c/+50/+48，不作上述缩放，生成内部类型 2。两者经 +767e30 生成记录后进入已确认的广播链。外部类型 2 的 9.8 缩放强烈提示加速度单位转换，但仍需类型定义或独立入口映射来证实，不能仅凭常量宣称所有传感器已认定。

+767e30 已实现于 vdr_sample_calibration.py：三项备用值都严格大于 900 时使用主值且输出标志为 0；否则复用已有偏置，或首次以备用值减主值建立偏置，再输出备用值减偏置并置标志为 1。各减法按 float32 舍入。verify_vdr_calibration_native.py 对完整原函数作 2000 次无钩子对照，覆盖三轴 900 边界、全无效备用值、偏置初始化及跨调用复用，输出与状态字节均一致。

另发现有别于 libloc_base 空 nativeSendSensor 的 JNI 注册：libamaploc +9f9188 名称 setGyro（字符串 +84d53），签名 +84d5b，函数 +327e44。该函数构造原始类型 4 消息，经全局 +a31ba0 对象虚表 +a0 发送。它与上述外部类型 3 之间尚有一层未核对，不能直接等同。下一步应追这一明确命名的输入到外部类型转换，或读取其消息类型适配函数。尚未把此研究模块启用为 TMC 导航。

## setGyro 命名入口经虚表到定位服务的路径

已核对 JNI 表相邻项：setAcce 位于 +9f91a0，函数 +327f28，签名 (IFFFFFFIJ)V，创建 PosSignalBase 类型 2；setGyro 位于 +9f9188，函数 +327e44，签名 (IFFFFFFFIJ)V，创建类型 4。二者进入全局 +a31ba0 所指对象的 +a0 虚方法。

须区分模块对象和输入接口对象：createPosModulePtr(+327750) 经 PLT +9f2c00 调用 posEngine::getIPosEngineModulePtr(+87f4c0)，构造函数 +881b34 创建总模块，其虚表 +a212e0。fetchPosModulePtrForNativeUse(+327754) 调用总模块槽 +1c0（+a214a0 重定位至 +882038），读取成员 +50。该成员由 +881c54 经 PLT +9f3ea0 创建 PosInterface4LocationBundleImpl（构造 +586584）。总模块的 +a0 实为 setPerfDetectorPtr，不能拿它当输入槽。

LocationBundleImpl 虚表由 GOT +a27848 指向符号 _ZTVN9posEngine31PosInterface4LocationBundleImplE(+a0caf0)，有效起点 +a0cb00。其 +a0 槽位 +a0cba0 重定位到具名函数 setSignInfo(PosSignalBase*)，地址 +586a50。setSignInfo 获取 IPosService 后调用其 +20 虚方法。GPosService 构造 +866204 在 +8662b0 将主虚表改为 +a202f0，+a20310 对应 +8678c4。

+8678c4 在 +867ae8 取队列节点，经原信号虚表 +18 克隆（+87dd30/+87dc18），+867afc 写入节点，+867b04 设置线程消息类型 0x1f00 后发送。服务消费函数 +869xxx..+86a644 检查 0x1f00 并取消息 +20 的节点、节点起始的原始信号，说明实际接收入口已经从 JNI 追到工作线程队列。尚需继续定位 PosSignal 类型 4 到 VDR 外部类型 3 的适配，不能因两者名字相似就当作已闭合。

本段是静态调用与重定位证据，不是运行中的完整导航验证；现有 TMC 不启用未完成的惯导实现。

## 已闭合具名传感器到内部 1/2 的类型转换

服务消费端 +86a594 判别原始信号类型 2/4 等，在 +86a5cc 调用 +812ae0。该转换函数使用 +c6a94 的 uint16 跳转表：原始类型 2 跳 +812c9c，最终 +81358c；原始类型 4 跳 +812c5c，最终 +8135cc。+81358c/+8171c8 写事件类型 2，+8135fc/+813604 写事件类型 3。因此已证明 setAcce(原始2) → 外部事件2 → 内部VDR类型1；setGyro(原始4) → 外部事件3 → 内部VDR类型2。配对器交给积分入口的 x2 是陀螺仪、x3 是加速度。

JNI 结构先按 z,x,y 排列（加速度主值 +30/+34/+38，备用值 +3c/+40/+44；陀螺仪分别 +34/+38/+3c、+40/+44/+48）。事件转换及 VDR 入口再按 +40/+44/+3c 取值，净效果恢复 JNI 三个浮点参数的原顺序，而非新增坐标旋转。加速度入口额外乘 float32 9.8；这与 g 单位转换一致，但尚未独立读取 Java 调用者的单位约定，陀螺仪也不能擅自标注为度或弧度。

新增 prepare_sensor_sample 于 vdr_sample_calibration.py。verify_vdr_sensor_adapter_native.py 串联原 +81358c/+8135cc 转换与 +769cbc/+769da8 处理，再同 Python 对照。2000 组结果一致：类型、时间、三轴、零值过滤、输出标志及跨调用偏置均通过。替换边界只有事件池获取/分配及下游广播；为隔离独立的消息延迟监控，每次输入将其状态 +c87c 置零，不重置偏置。该测试不验证延迟监控、消息过滤器、后续积分或完整导航。

当前已确认这条普通 VDR 链的输入需要三轴陀螺仪和三轴加速度，不能把 H5 geolocation 的 speed/heading 直接填入。后续仍需还原状态推进与输出，并核对浏览器可提供的真实输入或原引擎其他车载输入支路。TMC 原生惯导接入未完成。

## 完整 IMU 预积分与局部状态推进已移植并对照

新增 tools/amap-app/vdr_preintegration.py，不再只实现孤立表达式：Preintegration.advance 对应完整 +7cf594，advance_pose 对应完整 +78b9b8。前者使用成对陀螺仪/加速度，计算相对旋转、速度增量、位移增量及对偏置的五组导数矩阵；后者按当前偏置修正预积分结果，加上局部重力项，更新姿态、速度、位置。初始定位、局部坐标建立和 GPS 融合仍不在此模块中。

确认字段：预积分 +000 为旋转对陀螺偏置导数，+048/+090 为速度对陀螺/加速度偏置导数，+0d8/+120 为位移对相应偏置导数；+168 为相对旋转，+1b0/+1c8 为速度/位移增量，+1e0/+1f8 为参考偏置，+210/+228 为输入均值。+260 为当前时间，+264 为初始时间，+268 为已积分样本数。首次输入只设时间，不积分。+764628 本身即完成 signed32 毫秒差乘 0.001，不可再次缩放。原函数在此层不拒绝零或负时间差。

旋转指数映射 +763320 及右雅可比 +7639ec 以模长 1e-8 分支：小量分别用 I+[φ]× 与 I−0.5[φ]×；其余使用正弦余弦表达式。状态传播的 +a524a8 是输入到方程的三维重力向量；验证中明确供应该向量，未宣称已还原它的现场初始化。

verify_vdr_preintegration_native.py 装载原 ELF，连续执行原始 +7cf594 与 +78b9b8，对比 Python 全部六个矩阵、六组三维向量、三个计数/时间字段和局部姿态状态。50 条轨迹 ×20 样本，1000 次完整预积分和1000次完整状态推进通过；最大绝对误差 5.68e-14。覆盖零/小角度、一般旋转、零/变化采样间隔、非零初始矩阵/偏置和当前偏置修正。仅替换 libc memcpy、memset、sincos，没有替换原算法函数。sincos 使用宿主 math 实现，因此结果是指定容差下算法一致，不是 Android libm 位级一致证明。

此结果证明两段核心数值逻辑已经移植，不证明整套导航可运行。下一步需追踪初始姿态和重力、局部坐标原点与经纬度输出、定位恢复融合，并解决 TMC 实际传感器输入；仍未启用 TMC 的原生惯导。

## 普通 VDR 地图坐标正反转换与重力初值

已从输出路径 +780540 → +78b2e0 定位普通 VDR 的坐标转换，而非之前的地磁候选匹配坐标模块。姿态状态对象 +110/+118/+120 保存原点三项坐标，+128/+130 保存东西/南北比例。+78b238 设置原点并计算比例；+78b278 投影为局部位置，+78b2e0 做逆变换。比例为 east=cos(latitude*pi/180)*111319.49079327358，north=111319.49079327358，up直接相减/相加。因纬度余弦在第二维，经纬顺序可确认。输入沿用来源定位的坐标基准，不实施 WGS84/GCJ-02 转换，来源基准仍需追踪。

新增 vdr_local_frame.py，verify_vdr_local_frame_native.py 调用原始三个函数。1000 组原点初始化、2000 次正反转换与 Python 精确一致；覆盖南北半球、接近高纬和高度变化。仅 cos 使用宿主数学库，未替换坐标计算。该验证不证明 Android libm 位级一致或地理基准正确。

重力全局 +a524a8 的静态初始化在 +7b30f0：+7b3134 清前两项，+7b3144 写第三项位型 0xc0239d013a92a305，即 -9.80665，故初值为 (0,0,-9.80665)。已保存 INITIAL_GRAVITY 常量，不将其当作所有设备姿态已确定的证明。

+78b39c 对局部位移模长与100比较，大于等于阈值时将原点更新为逆投影位置并清局部位置，同时输出旧位移供调用方调整其他状态。已找到该重设原点行为，但尚未移植其对历史状态的调用链，不应只清当前位置而忽略历史。

初始姿态入口进一步定位到 +77b86c：读取历史0x138字节记录中的候选矩阵，与输入 +8 的方向构造矩阵（+762d8c）组合，随后向 +78b140 提供姿态、速度、经纬高和偏置。此处说明不能简单以当前 heading 代替全部初始姿态；历史矩阵来源、GPS恢复融合与真实浏览器输入仍待接通。完整 TMC 目标未完成。

## 初始姿态历史的实际写入链

继续静态追踪确认 +77b58c 将扩展预积分记录的 +290/+2d8 分别复制到历史记录 +d0/+88；+77b86c 优先使用 +d0（首元素小于100），否则使用 +88。构造函数 +7737dc 经 +77679c/+77680c 写入的是无效初值，不能当作姿态估计算法。

实际写入入口为 +77a3e0：输入 x1 是扩展预积分，x0 是姿态估计组件。组件 +2e9 有效时，将 +2a0 矩阵写到预积分 +290；+2e8 有效时，将 +258 写到预积分 +2d8。该函数还在预积分 +284 等于1时合并陀螺均值和样本计数，累计至少26个样本后写入 +320 偏置。配置位控制这些路径，并有后续矩阵修正分支，尚不能将前半段当作完整函数替代。

姿态组件 +77a3c0 在 +2e9 未置位时，将组件 +38、定位记录与两路传感器样本传给 +7bd1a4。后者累计 x3 样本三轴至统计器 +160；经过时间门限且 +2b0 未置位时，取统计结果调用 +762898，将矩阵写到内部 +220（即外层 +258），随后置 +2b0（外层 +2e8）。因此备用姿态的生成链已定位到 +762898；其数学定义仍需反汇编与原函数对照。另一路 +7bd500 使用定位与传感器历史进行矩阵估计，仍待完整移植。

这些新发现是静态证据，尚未对姿态初始化执行差分验证。此前预积分、状态推进和局部坐标转换的验证范围不因此扩大；TMC 运行时仍未接入完整原生惯导移植。

## 备用初始姿态矩阵完成原函数对照

新增 vdr_initial_attitude.py，对应完整 +762898。一般分支将输入加速度向量归一化为第三列，将 (-y,x,0) 归一化为第二列，第一列为第二列与第三列的叉积。此处列方向和乘法顺序来自反汇编及原函数对照，不按常见姿态公式自行替换。若 abs(x)、abs(y) 均严格小于1e-9，使用原函数固定矩阵；z正/零和z负分别处理。尤其零向量仍返回固定矩阵，不能误认为原算法在这里拒绝无效传感器输入，上游有效性检查仍需保留。

verify_vdr_initial_attitude_native.py 执行完整原函数及其调用的归一化/矩阵工具，不替换任何函数、无 hook。1048次调用通过，覆盖1000组一般向量和48组阈值、零向量、正负z边界；最大误差1.11e-16（Python普通乘加与ARM64融合乘加的舍入差）。该结果仅证明备用矩阵构造，尚未覆盖上游统计窗口、有效标志更新、另一条定位辅助姿态估计 +7bd500 或完整导航初始化。运行时接入和GPS恢复融合仍未完成。

## 定位辅助姿态估计：360方向评分已验证

追踪 +7bd500 → +7bc014，确认先把传感器旋转到重力对齐的坐标系，再分块平均。+7bc014 还构造陀螺第三轴乘速度的序列，并检查水平加速度均方根至少0.4、平均速度变化量乘配置速率至少0.2，随后同时调用 +7bc524 与 +7bc6f8，再由 +7bcba4 检查结果。后续两组统计器需积累足够次数，才更新保存的方向候选。不能把一次最低分直接视为完成标定。

新增 vdr_heading_alignment.py，对应 +7bc524：75个分块样本产生74个相邻速度差，分别乘配置速率；针对0至359度，每个候选计算 ax*cos(angle)+ay*sin(angle) 与速度差的均方误差（74项）。只使用前74个加速度样本，保留原程序窗口约定。角度构造顺序为 (angle/180)*pi。Python入口明确要求75个样本，原函数依赖调用方满足固定窗口且未自行检查长度。

verify_vdr_heading_alignment_native.py 执行完整 +7bc524，包括矩阵/向量分配及评分循环；只提供 malloc/free/new/delete，未替换算法。三角表由宿主生成并同样供应两端，因此未覆盖Android sincos实现与构造函数。40组调用共14400个分数通过（含静止零误差），最大绝对误差2.91e-11，按相对1e-13、绝对1e-12比较；误差来自融合乘加舍入。该验证不覆盖 +7bc6f8、候选交叉检查、历史累计和完整姿态标定，TMC原生惯导目标仍未完成。

## 方向候选交叉检查已完成原函数对照

vdr_heading_alignment.py 新增 heading_extrema（+7bcce8）和 select_heading（+7bcba4）。前者从全局最小值开始环形扫描360项，保留升降趋势变更处的极值，平台延续原趋势；按与两侧极值差均大于全局极差的15%标记显著性。原函数最低值初始哨兵为10000，Python显式拒绝所有值都不低于此哨兵的输入，避免原函数负索引路径；不宣称覆盖这种无效输入。

交叉检查必须恰好四个极值，且首个最低分不大于1000；取第一个和第三个极值对应的两项车速评分。若一项至少为另一项两倍，选择较低者；差异不足则返回无候选。两者同为零时，按原分支顺序选第三个极值。显著性标记在此函数内没有参与拒绝条件，未擅自添加。

verify_vdr_heading_selection_native.py 完整执行上述两个函数，包括动态极值列表与销毁，只有内存分配、释放及memcpy运行时替身。500组极值提取与500组完整交叉检查和Python精确一致，205组接受；覆盖两谷曲线、平台、常数曲线、随机噪声、比例恰为2以及零车速评分。尚未覆盖高分阈值全部边界与异常数值。

第二组评分 +7bc6f8 已定位到75行、5列输入的矩阵计算，包含消去一列及后续求解；该模型与历史统计累计尚未移植，故候选筛选通过不代表完整姿态标定已接通。TMC运行时与定位恢复融合仍未完成。

## 第二组姿态评分模型完成移植

新增 model_heading_scores 对应完整 +7bc6f8，输入75×5矩阵，调用方各列为旋转后的ax、负ay、常数1、车速、旋转后的gz乘车速。计算前四列转置乘全部五列所得4×5矩阵，先消去速度列对前三行的影响，再消去常数列对前两行和第四行的影响；按候选方向求两个附加系数，回代原75行求残差平方均值。保留原代码的消元顺序，没有用通用最小二乘库替代。两个主元检查分别是绝对值大于1e-15、绝对值至少2.220446049250313e-16，不满足即拒绝窗口。

verify_vdr_heading_alignment_native.py 增加 --model，完整运行原 +7bc6f8，只提供分配/释放/memcpy，未替换矩阵函数、消元或评分。40组中37组产生13320个方向分数，3组因零速度、恒定速度或近零速度导致主元检查失败；全部与Python一致，最大评分误差2.73e-12。共享测试框架修改后也复验原车速评分40组14400项通过。三角表沿用宿主生成并提供给两端的限制，不覆盖Android数学库差异。

历史统计器入口进一步定位为 +76848c/+7684a4/+7685dc：有衰减系数、衰减权重、累计向量、是否初始化及不衰减总权重。调用方对两路评分各维护一个统计器，等累计总权重达到配置次数再重新交叉筛选。该历史累计尚需完整翻译和状态连续调用验证，不能以单窗口通过替代整套姿态标定。运行时接入、定位恢复融合仍未完成。

## 连续历史累计已移植并验证

新增 vdr_weighted_history.py，原 +7684a4 的累计权重为 decay*旧权重+本次权重，向量为 decay*旧向量+本次权重*本次向量；首次输入直接加权赋值。+28另存不衰减的权重总和。+7685dc 仅当累计衰减权重绝对值至少1e-6时返回向量除该权重。reset对应 +7685cc 的逻辑重置，不要求释放旧存储。

verify_vdr_weighted_history_native.py 完整执行初始化、更新、重置和取均值；400次连续更新与取值对照通过，覆盖decay=0/0.5/0.95/1、零权重、1e-6边界及中途重置。核对累计向量、衰减权重、不衰减总权重和均值；只有分配/释放/memcpy运行时替身。原构造 +7bbe34 对两路历史均使用常数0.95。

HeadingHistory 已按 +7bc014 后半段连接两路评分：单窗口交叉检查通过才加入历史；总权重达到构造参数指定门槛后，对历史均值再交叉检查；失败保留上次有效候选。此组合类还未执行整个 +7bc014 的连续差分验证，参数门槛仍由调用方明确提供。不能将统计器400次测试当作组合标定链或TMC导航验证。下一步为窗口预处理、组合链连续验证与姿态初始化连接，定位恢复融合仍未完成。

## 完整窗口标定 +7bc014 连续对照通过

新增 HeadingAlignment：按构造器 rate 推导 block_size=int(25/rate)，对75个块计算三轴加速度均值、速度均值及逐样本gz*速度的均值（不能先各自平均再相乘）。执行水平加速度RMS及速度变化门限，再运行两路评分、单窗口交叉检查和历史累计/重筛选。输入是上游已经重力对齐的传感器窗口，不是直接浏览器原始IMU。显式限制75个完整块，避免原实现内部固定75项访问导致越界。

新增 verify_vdr_alignment_window_native.py，直接执行完整原 +7bc014，未替换任何评分、门限、历史或候选算法。48个连续窗口覆盖rate=5/25（块大小5/1）、有噪声的合成变速转向、间插静止窗口及累计门槛前后；42次返回已建立或更新的候选，候选角度、两项评分和两路历史权重均与Python一致。原函数的动态内存分配/释放、memcpy/memmove由宿主提供；构造参数及三角表显式设定，未执行原构造器。测试门槛3仅用于验证，未声称是生产配置。

此验证首次覆盖组合窗口标定，而非独立评分函数。尚未覆盖 +7bd1a4 的定位/传感器窗口采集与 +7bd500 的重力对齐、最终矩阵组合；姿态初始化、GPS恢复融合、真实传感器输入及TMC运行时仍未接通。完整目标保持未完成。

## 窗口前的重力方向对齐已验证

vdr_initial_attitude.py 新增 align_vectors，对应 +7632c8 → +763188 → +763320：输入两个向量分别归一化，以叉积确定旋转轴，夹角由点积上限截到1后acos给出，旋转向量为 angle*cross/|cross|，最后指数映射为矩阵。+7bd500 的实际调用是历史平均加速度方向到 (0,0,1)。此处算法与备用初始姿态 +762898 不同，不可互换。

verify_vdr_gravity_alignment_native.py 执行完整原 +7632c8，1048组输入通过，最大误差1.22e-15；仅acos/sincos使用宿主库，未替换归一化、叉积、旋转向量或指数映射。包括零/竖直、接近竖直、正负z及1000组一般向量。原函数对零向量或完全平行向量没有除零恢复，产生NaN；Python保留此行为，验证对NaN显式比较。未来运行时必须在调用边界拒绝/延后这类结果，不可假定任何输入都会产生有限旋转。

后续矩阵组合路径已确认 +7bd500 根据接受角的负值构造绕z矩阵，经 +76356c 与重力对齐矩阵相乘，再写入两份姿态矩阵与有效标志；完整上游统计、窗口采集和该组合仍待连续验证。目标仍未达到TMC可用的完整原生惯导。

## 完整批次姿态标定 +7bd500 对照通过

新增 vdr_attitude_calibration.py，将窗口平均加速度的历史统计、重力方向对齐、原始IMU旋转、完整方向窗口标定和最终矩阵写回连接。实际构造链 +7bd09c..+7bd0c8 给出 rate=5、方向接受累计门槛2、重力统计衰减0.99，两路评分历史仍为0.95。375个配对样本形成75块。此前测试门槛3仅为测试参数，现在模块使用已确认的实际参数。

verify_vdr_attitude_calibration_native.py 直接执行完整原 +7bd500，连续24个输入批次与Python对照通过，22次已有有效姿态；检查两份矩阵全部元素、两个有效标志及历史累计权重。覆盖标定建立前后、带噪声变速/转向与间插静止批次。测试显式设置构造后的状态，未执行构造函数；宿主仅提供分配/复制及acos/sincos。未替换重力对齐、窗口评分或矩阵算法。

整段测试纠正了一个单函数测试无法发现的约定：写出的两份姿态矩阵对应 transpose(yaw(-accepted_angle)*gravity_alignment)，不能直接保存乘积。原始矩阵组合及写回存在转置约定，Python已按实际原函数输出修正。

Python在重力对齐产生非有限矩阵时显式保留上次姿态，这是接入边界保护，不宣称原 +7bd500 有相同恢复；该分支未用于宣称原函数逐值一致。尚缺 +7bd1a4 的定位/IMU时间窗口采集、主导航状态初始化与定位恢复融合，TMC运行时仍未完成。

## 定位与IMU窗口采集连续验证

新增 CalibrationWindow，翻译 +7bd1a4 在定位有效性过滤之后的排队/车速插值：以收到配对IMU时的时间戳记录定位端点；两有效定位间隔必须为[1,3000)毫秒，按两端车速对先前积累的IMU时间线性插值；每次接受定位后清待配对队列，再加入当前IMU。待配对队列超过100条清空且重置前次定位；已配对样本严格超过375条才调用一次批次标定并消费前375条。常量来自构造 +7bd064 的 (5000,3000,100,375)，5000另用于独立备用姿态超时。

verify_vdr_calibration_window_native.py 执行真实构造器 +7bd064 与1200次完整 +7bd1a4，包括原 +7bd500 调用。每步对照待配对陀螺时间戳/三轴、配对后的两路IMU、插值车速和队列长度，确认2次批次触发。包含25Hz采样、1Hz定位和超过队列容量的定位中断。初始化ELF相对重定位；只提供分配/释放、复制/清零和acos/sincos的宿主运行时，未替换窗口算法。此测试对输入定位采用已知有效字段夹具，没有证明H5字段到原定位质量门限的映射，也未对照独立备用姿态输出。

因此设备采样到批次标定之间的窗口行为已有证据，但不等于主导航惯导状态机接通。下一步为有效姿态如何初始化主导航状态、定位恢复融合，以及TMC实际输入与运行时适配。完整目标仍未完成。

## 主导航初始状态构建已验证

新增 vdr_pose_initialization.py：按 +77b86c 读取的历史记录，首选矩阵首项小于100时使用首选，否则使用备用矩阵；以原生solution+8方向构造yaw，初始旋转为 yaw*transpose(calibration)，速度为yaw*(speed,0,0)，位置与加速度偏置清零，陀螺偏置来自历史+118。保留标定矩阵、辅助向量(1.5,0,0)、flags=0x7f及经纬高原点/比例。方向参数明示为原生解算字段，尚不等同于浏览器compass heading。

verify_vdr_pose_initialization_native.py 从 +77b86c 入口执行到 +77b990，包含实际矩阵选择/组合、速度计算、+78b140构造与最终复制；在日志尾部之前停下，未声称执行整个含日志入口。500组对照核对全部姿态/速度/偏置/标定/原点/比例/辅助字段、时间戳及标志，最大误差1.11e-16；覆盖首选、阈值等于100和无效首选使用备用，以及不同历史索引。原矩阵算法未替换，数学库使用宿主。未覆盖输入solution为空时的清理分支。

此次上层验证确认了第二处转置约定：批次标定保存转置结果，而初始化组合时读取其转置。不能将两处独立地简化后混用未经转换的数据。还需追踪solution方向来源、初始化触发条件、GPS恢复融合及真实TMC输入；完整导航目标仍未完成。

## 初始化方向来源和定位校正入口（静态证据）

初始化传入的solution是0x138字节历史记录，不是额外假定的解算对象。+77ba80 从历史环形队列尾部向前检查 +130 标志和 +8 非负方向，调用 +7b45e0 检查时间是否可用；扫描会继续向前更新候选，遇到未置 +130 的记录即停止。因此不能简单取最新GPS。+77b58c 已证明历史+8来自扩展预积分+288。

实际方向写入点 +779f04/+779f08 将扩展记录 +390 复制至 +288；+390 即内嵌GPS(+338)的+58。之前分支检查定位虚函数有效性、标志字节、速度(+388)、质量字段(+398)，低速情况下还比较前后坐标距离、方向差和时间跨度（+7643c4/+764474/+762730）。原生方向数值来源现已定位，但GPS+58最上游相对指南针的转换仍需确认，不能据此直接接H5 heading。

主状态4的初始化 +77bb2c 要求扩展记录+278非零、至少一个标定矩阵首项小于100、可用历史记录；+77b86c完成初始状态后通过 +7b483c 接入管理器。首选矩阵有效进入状态16，只有备用有效进入状态8。+278的完整物理语义尚未确认，不称为GPS可用标志。

定位观测入口 +77b78c → +7b48e8：默认配置走管理器+4f8的 +7d735c，成功后复制校正姿态及辅助状态，再对尚未消费的预积分调用 +78b9b8。+7d735c 先 +7d6df4 对齐时间、检查姿态有效性，观测类型8分派 +7d59dc，其余分派 +7d6ad8；类型具体来源还需追踪。另一个配置位走 +78faf4，不能默认两分支等价。连续IMU路径 +7b4c04 → +7d64a0 也使用同一管理器状态。下一步应沿这些真实校正入口继续，而非添加自行设计的GPS插值融合。以上尚为静态证据，未新增运行时或融合差分验证。

### Error exponential (+763b88), native differential verification

Ported `tools/amap-app/vdr_error_exponential.py` and added
`verify_vdr_error_exponential_native.py`. The full original function executed
for 500 nine-dimensional error vectors, including zero and tiny rotations.
Rotation and both translated columns matched Python, maximum absolute error
8.88e-16. Only allocation/copy and host trigonometric runtime functions were
substituted; the original transformation and matrix multiplication executed.

The first three entries form Exp(phi); each remaining 3-vector is multiplied
by the SO(3) left Jacobian (transpose of the already verified right Jacobian).
This confirms the increment primitive used by +78c0e4. It does not yet validate
that full injection function, the measurement construction, Kalman correction,
or the full navigation chain. No TMC runtime integration is claimed.

### Full state injection (+78c0e4), native differential verification

Added `vdr_error_injection.py` and `verify_vdr_error_injection_native.py`.
512 original function executions covered every mask 0..127 four times,
including zero rotation and nonzero position, velocity and biases. Maximum
absolute difference was 2.84e-14. Checked all seven state blocks and unchanged
48-byte tail containing state flags/local frame. Six diagnostic stream calls
were skipped explicitly; all state mathematics and its callees executed.
Runtime allocation/copy and trigonometric substitutions match the earlier
verifier, so this is not a claim of Android runtime execution.

Confirmed: the low three mask bits must ALL be set to update pose. The
rotation increment left-multiplies R and rotates existing V/P before adding
the left-Jacobian-transformed velocity/position increments. Bits 3 and 4 add
gyro/acceleration bias increments; bit 5 left-multiplies the calibration
rotation; bit 6 adds the auxiliary vector increment. Unselected blocks stay
unchanged. The Python API returns a copied state, whereas native mutates it.

Still outstanding: measurement construction and covariance/gain at +7d5810,
GPS observation type/provenance, complete fusion lifecycle, and TMC runtime
integration. This verified injection alone does not implement navigation.

### Measurement correction (+7d5810), complete-call comparison

Added `vdr_filter_update.py` (NumPy research dependency) and
`verify_vdr_filter_update_native.py`. Ran 60 full original +7d5810 calls with
observation dimensions 1, 2, 3, 6, 9, 12; dense positive-definite state and
measurement covariances; both calibration flag states. Compared the returned
21-vector, all seven pose blocks, entire updated covariance and incremented
counter. All matched with rtol=1e-9, atol=1e-11. Each case started counter zero;
periodic normalization cases are deliberately excluded and remain pending.

Confirmed formulas on this domain:
S = H P H^T + R; K = P H^T S^-1; e = K residual;
A = I - K H; Pnew = A P A^T + K R K^T;
Pnew = (Pnew + Pnew^T)/2.
Native +4e0 selects state injection mask 7 or 0x7f. +1d0 counter increases;
+78c920 calls +78c764 on attitude every 100 updates and on calibration every
1000 updates. Those normalization internals are not yet ported.

Original matrix/decomposition/state math executed, including +76fd48 and
+7aba3c. Harness supplies allocation, copy, memset, trig, single-threaded C++
static guard acquire/release; skips the same six diagnostic stream calls in
state injection. This does not validate singular/indefinite covariance cases,
upstream GPS observation building or covariance prediction. NumPy solve is
an equivalent formula on the verified SPD domain, not a byte-for-byte port of
the native factorization's singular-matrix behavior. No TMC runtime imports
added. Next integration blockers are actual GPS H/residual/noise construction,
prediction covariance, periodic normalization, and native lifecycle wiring.

### Periodic rotation projection and correction lifecycle

Added `vdr_rotation_normalization.py` and native verifier. +78c764 projects a
nonzero 3x3 matrix through SVD: U diag(1,1,det(U)det(V^T)) V^T. Its early skip
is NOT an orthogonality test: +78a8cc compares abs(max)<1e-30 and
abs(max-min)<1e-30. The Python nonfinite input rejection is an explicit guard,
not a proven native behavior. 100 native executions, including zero, tiny
constant matrix, near-identity perturbations and dense full-rank matrices,
matched NumPy's equivalent projection (max abs error 1.25e-14). Native SVD
executed; it was not hooked. Degenerate nonzero rank-deficient cases remain
outside the validated domain because SVD bases may differ.

Added CorrectionFilter state/covariance/counter wrapper. It performs the
already verified measurement correction, then attitude projection at each
100th update and calibration projection at each 1000th. Native signed counter
wrap is represented. Updated whole +7d5810 verifier with input counters
0/98/99/998/999/1999; 60 complete calls passed, including periodic projection
branches, covariance, error vector, all pose blocks, and counter. This
supersedes the earlier exclusion of periodic normalization. Counter overflow
is implemented but not included in that test set.

Still no runtime TMC integration. GPS observation H/residual/noise construction,
covariance prediction and source/lifecycle linkage remain required.

### Native GPS position observation +7d46fc

Ported `vdr_position_observation.py`; full-function verifier passed 100 native
calls with randomized local positions, geographic observations and sigma.
Compared complete 3x21 H, 3-vector residual and variance vector. Native vector
append/allocation, local projection and observation matrix construction all
executed (only runtime support substituted).

Confirmed H[:,0:3]=-skew(predicted_position), H[:,6:9]=I, remaining columns zero;
residual=local_frame.project(lon,lat,alt)-predicted_position; all three noise
variance entries=sigma^2. The function appends a matrix and two vectors to
three native containers. Python returns those three values; converting the
variance vector into the aggregate observation noise matrix is upstream of
+7d5810 and not yet verified here.

Caller +7d64a0 checks native GPS virtual validity and GPS flag +18==0 before
calling. It reads lon/lat/alt from extended preintegration +370/+378/+380 and
quality from +398. If config bit 5 is clear, quality must be <=20; if set,
quality is multiplied by the double at +7bcf8 (not yet decoded). Do not equate
this sigma automatically with browser accuracy, and do not infer datum or
missing-altitude behavior. The existing local-frame transform is reused.

Next: inspect +7d5560 and the remainder of +7d64a0 for prediction covariance,
observation stacking and invocation of the verified correction filter.

### Observation stacking +7d6748..+7d68a8

Added `vdr_observation_stack.py`, used by CorrectionFilter.update_observations.
100 original assembly paths executed from +7d6748 to immediately before
+7d68ac's call to +7d5810. Inputs included 1..6 blocks with 1..3 rows each.
Stacked H, residual and diagonal covariance matched exactly, including the
native variance-vector-to-matrix helper +7b1664. No observation math hooks.
The verifier enters with the three native containers initialized on the stack;
it does not claim execution of the preceding GPS eligibility gates.

Empty container skips correction in the caller; the Python wrapper likewise
returns None and does not increment the correction counter. Position
observations can now feed the verified research correction via this actual
stacking convention. No TMC runtime integration has been enabled.

Important call-chain correction: +7d5560 is local-frame reanchoring via
+78b39c, followed by covariance coordinate transformation, NOT ordinary time
prediction. That transformation and covariance propagation still need
implementation; replacing them with an assumed generic propagation formula
would not establish fidelity to the native navigation pipeline.

### Local reanchor and covariance transform +7d5560

Implemented `vdr_reanchor.py` and CorrectionFilter.reanchor. Full native
+7d5560 calls (including +78b39c) matched 100 cases. Included displacement
norm 0, 99.999, 100, 100.001 and randomized 3D shifts. At norm >=100,
new origin=old_frame.unproject(position), position=0, and Pnew=T P T^T,
where T=I except T[6:9,0:3]=-skew(old_position). Recomputed east scale from
new latitude also matched. Maximum absolute covariance difference 3.73e-9
for large transformed covariance entries; rtol1e-10/atol1e-8 checks passed.
Native updates selected covariance blocks in place; Python expresses the
same verified transformation as a full matrix product.

Corrected unused cos/acos runtime hooks inherited by five verifier scripts:
a previous source-string register import edit also inserted register names
into reg_write calls. The new reanchor test exercises cos and exposed it.
Reran all five affected verifiers: reanchor 100, filter 60, position 100,
stack 100, normalization 100 passed. Earlier tested paths did not execute
those malformed hooks; reported comparisons remain unchanged.

Call ordering remains explicit: native +7d64a0 reanchors before building
position observations, so observation construction must follow reanchor.
The research CorrectionFilter exposes reanchor separately for that reason.
No TMC runtime integration or covariance time prediction is claimed yet.

### Corrected and located covariance prediction entry

Static trace confirmed ordinary manager +7b4a78 (config bit 4 clear) calls
+7d5c20 at its +4f8 filter member, then copies covariance/pose outward.
+7d5c20 validates pose (+778068), derives dt through +7cf360 -> +764628,
obtains pose terms via +7db924, and calls +78baec. +78baec allocates a 9x15
matrix at x4 and 9x6 matrix at x5; these drive the covariance block updates
beginning +7d5d20. Base noise matrix is at filter+1b8 and is used with dt
and an embedded 25.0 constant in the expression passed to +7da3a8. Exact
noise expression and derivative formulas remain pending, not inferred here.
Saved complete disassembly in ignored prediction-complete.txt for next work.

Correction to earlier research description: +7d6df4 does not align time.
It checks the observation at filter+4d8, and for type 2 copies byte +288 to
filter+4e2. Timestamp eligibility is separately checked by +7d6e14 against
the global preintegration history. This distinction matters for wiring a
future native-equivalent lifecycle. Current evidence identifies prediction
but does not verify/port its mathematics or enable it in TMC.

### Process-noise time scaling confirmed

Implemented `vdr_process_noise.scale_process_noise` and original-function
verifier. +7d5f1c's +7da3a8 expression evaluates (base_noise * dt_seconds)/25,
not dt*25 or dt-squared. Confirmed vectorized fmul/fdiv at +7da620 and scalar
remainder +7da65c. 100 whole helper executions matched exactly, including
zero dt, 1ms, 40ms, 200ms, 1s, 6x6/12x12 and odd 5x5 matrices (scalar tail).
The 25 constant is established by caller assembly; its physical rationale
is not established. Base noise values and subsequent projection remain
separate unfinished work. This helper is not yet wired to runtime TMC.

Derivative assembly inspection additionally shows explicit gravity*dt and
0.5*gravity*dt*dt skew terms inside +78baec, as well as rotation/bias
preintegration Jacobians. Those terms must be retained when porting the
9x15 and 9x6 matrices; no generic constant-velocity replacement was added.

### Full prediction Jacobians +78baec verified

Implemented `vdr_prediction_matrices.py`; 200 complete native +78baec calls
matched both 9x15 state and 9x6 noise matrices. Varied nontrivial rotations,
all five preintegration derivatives, biases, velocity/position, gravity and
positive dt 1/20/40/100/1000ms. Included zero gyro-bias difference. Maximum
absolute difference 1.56e-9 (noise includes division by 1ms); checks used
rtol1e-9/atol1e-8. Native math executed without matrix hooks. Velocity and
position arguments were supplied by previously verified advance_pose.

For A=R*deltaR*Exp(phi)*Jr(phi)*Jrotation_bg,
phi=Jrotation_bg*(bg-bg_reference):
B=skew(predictedV)*A+R*Jvelocity_bg;
C=skew(predictedP)*A+R*Jposition_bg.
F has identity first9 diagonal, skew(g*dt) in velocity/attitude,
skew(.5*g*dt^2) in position/attitude, dtI in position/velocity;
bias blocks A/B/C and R*Jvelocity_ba, R*Jposition_ba.
G=-F[:,9:15]/dt. The Exp(phi) term in A is essential; first prototype without
it failed, and comparison drove the correction before accepting the port.

Python explicitly rejects nonpositive dt rather than reproducing native
floating division by zero. Caller eligibility needs confirmation before
runtime integration. This completes derivative formulas, not the remaining
21x21 covariance block update, base-noise initialization, or full lifecycle.

### Full ordinary covariance prediction, non-adaptive branch

Added `vdr_covariance_prediction.py`. 100 native +7d5c20 executions with
filter+4e0=0 matched the complete 21x21 covariance and propagated R/V/P/bias
state, rtol1e-9/atol1e-9. Varied dense covariances, rotations, derivatives,
nonzero biases, velocity/position and intervals 1/20/40/100/1000ms. Only global
history insertion call +7d5c90 was skipped; all prediction math and original
pose advancement ran. Calibration-enabled adaptation after +7d60e8 remains
unported and is explicitly outside this helper's scope.

T is 21x21 identity with T[:9,:15]=verified F. Start Pnew=T P T^T.
Qscaled=Q*dt/25 for 18x18 Q. Native adds G Qscaled[:6,:6] G^T only to the top
9x9 block and Qscaled[6:,6:] only to the bottom12x12 block. No cross-block
noise is added. A dense Q test exposed the difference from a generic single
N Q N^T expression; port was corrected to native behavior and dense Q cases
now pass. This is verified behavior, not an assumption of block-diagonal Q.

Result's pose is propagated; the metadata timestamp/history lifecycle remains
caller-managed, matching this primitive's scope. Native branch selection,
base-noise and initial covariance values, calibration adaptation and live
TMC sensor wiring still need completion before enabling runtime navigation.

### Adaptive calibration trigger +7bdc40

Implemented `vdr_calibration_gate.py`. 500 complete native updates, native
constructor +7bdbe8 and resets +7bdc1c matched Python, with 33 triggered
updates. Compared returned decisions and both histories' decayed/total
weights. Histories use decay 0.8 for motion and 0.9 for absolute normalized
errors. First five prior samples suppress triggering. Thereafter compare
current motion >2*prior motion mean, both prior error means <1.4, and either
current ORIGINAL signed error >=2 plus its absolute value >2*prior mean.
Current sample is added whether triggered or not, and comparison uses prior
means. Negative synthetic error spikes were included to check that the >=2
comparison is signed, even though the actual caller supplies nonnegative
normalized residuals. All math/history executed; only runtime substitutions.

The caller +7d6244 uses this result to inflate calibration covariance at
indices15..17 using sqrt(1 + (0.5*rotation_change)^2/Pii). Full upstream
normalization of residuals and ensuing row/column scaling still need native
comparison. Gate alone does not complete the adaptive prediction branch.
Initialization parameters and TMC runtime wiring remain pending.

### Triggered calibration covariance inflation verified

Implemented `vdr_calibration_covariance.py`. 100 original block executions
from +7d6258 to +7d6440 matched all 441 covariance entries exactly. Input
was dense positive-definite 21x21 P and supplied rotation-change magnitude,
including zero. No math substitutions in this block. This is a block-level
test, not the entire adaptive prediction function or trigger calculation.

Let v=(0.5*rotation_change)^2 and D=identity, with
Dii=sqrt(1+v/Pii) for i=15,16,17. Native update is D P D, scaling both rows
and columns including all correlations. The resulting three calibration
variances grow by v. Python checks positive calibration variances explicitly;
nonpositive/native floating exceptional behavior is outside verified scope.

Pending adaptive branch input construction: body-frame velocity residual,
its 2D covariance normalization, and rotation-change magnitude. The gate and
triggered covariance adjustment are individually verified but not yet joined
into the complete +7d5c20 calibration-enabled branch. TMC wiring pending.

### Complete calibration-enabled prediction verified

Added `vdr_adaptive_prediction.py` and two native verifiers. 100 native input
construction paths stopped just before +7d6244 matched both normalized error
inputs and the motion input. World-to-vehicle matrix is C^T Rpredicted^T;
use lateral/vertical velocity divided by sqrt(diag(H Ppred H^T)), where H is
2x21 with only velocity columns3..5 populated by rows1..2 of that transform.
Motion is norm(cross(Rprevious[2,:],Rpredicted[2,:])). Correction to earlier
wording: this is not generic heading-angle change; it measures the change
of the third rotation row, without conversion to an angle.

100 complete calibration-enabled +7d5c20 executions then matched all 441
covariance entries and propagated pose. Used native gate constructor and
five baseline updates before each case, with matching Python history.
Varied speed to exercise both outcomes: 9 cases triggered covariance
inflation. Only global history insertion +7d5c90 and diagnostic logging
+7d6254 were skipped; input normalization, gate/history, covariance inflation
and pose/matrix math all executed. Existing ordinary prediction and adaptive
subcomponents are now joined in a verified research function.

Remaining integration work includes initial P/Q constants, observation
selection (including vehicle constraints/speed/heading), timestamp/history
and reset lifecycle, input coordinate/sensor conventions and live TMC wiring.
This does not establish end-to-end navigation or H5 sensor availability.

### Native default variances and covariance initialization

Added `vdr_filter_initialization.py`; executed full constructor +7d5080 and
reset +7d51f8. Constructor's 13 doubles match exactly: process-noise groups
(1e-4,1e-2,1e-8,1e-7,1e-8,1e-8), initial-state groups
(1,2.5,20,1e-7,1e-4,1e-3,1e-3). Each group repeats for three axes.
These are direct diagonal variance values, not standard deviations to square.
100 complete resets with default/randomized values matched both full matrices
exactly; injected pre-existing cross terms were cleared as expected.

Default ordinary filter installation +7b483c routes to +7d7060 when alternate
config bit4 is clear. For full flags0x7f, +7d7060 invokes callback+28, resets
filter, copies pose, initializes covariance through +7d51f8, then replays
history records with timestamp >= requested initialization time. Records
strictly later than that time go through prediction first, while equal-time
records go directly to observations. Callback/history ownership and partial
installation remain pending before a faithful runtime lifecycle is complete.

No TMC runtime import or end-to-end navigation claim. Remaining major work:
vehicle/speed/heading observation construction and selection, history/reset
lifecycle, input conventions and runtime integration.

### Horizontal GPS velocity observation +7d4084

Added `vdr_velocity_observation.py` and full-function native verifier.
200 calls matched all 2x21 H entries, residual and variance vector, including
three representable values around the speed compensation threshold.
H[:,:3]=-skew(current_velocity)[:2,:], H[:,3:5]=I2, remaining entries zero.
Measured velocity=(corrected_speed*cos(direction*pi/180),
corrected_speed*sin(direction*pi/180)). For speed strictly greater than
8.88888888888889, subtract 0.8333333333333333; otherwise leave it unchanged.
Residual=measured-current horizontal velocity. Both variance values are 1.
These exact constants and behavior are preserved; no rationale is inferred.

The input native GPS record supplies speed at +50 and direction at +58.
This direction's coordinate convention is local-east angle; browser compass
heading needs an explicit upstream conversion, still to be traced. Caller
+7d64a0 requires config bit4, native GPS validity, flag+18 clear, direction>=0
and 0<=speed<100. This construction test does not validate those caller gates
or establish the provenance of the native angle. Alloc/copy and sin/cos
runtime hooks only; original observation math and container insertion ran.
No production TMC imports yet; vehicle constraints, heading observation and
history/reset lifecycle remain outstanding.

### Stationary zero-velocity observation +7d4274

Added `vdr_stationary_observation.py` and whole-function verifier. 200 native
calls matched 3x21 H, residual and three variance entries. H[:,3:6]=I3,
all other columns zero (no attitude skew block); residual=-current_velocity;
variance=(0.0004,0.0004,0.0004). Native caller +7d64a0 selects this when
extended preintegration+27c is zero. Provenance of that motion classification
is still to be traced, so H5 speed==0 is NOT silently substituted for it.

Moving-vehicle observation is +7d3c78. Initial static inspection confirms
inputs include gyro minus pose gyro bias, calibration rotation at pose+a8,
velocity, and pose+f0 auxiliary vector in cross products. Therefore a naive
zero lateral/vertical velocity constraint would omit native lever-arm-related
terms. This function and its flag-controlled rows/noise remain unported.
No production TMC integration enabled by this research step.

### Moving-vehicle observation +7d3c78 verified

Added `vdr_vehicle_observation.py` and whole-function verifier. 200 complete
native calls matched H (2x21), residual and variance pair, across all four
w4/w5 noise combinations, including zero auxiliary offset and zero corrected
gyro. Runtime allocation/copy/trig hooks only; original observation math ran.

With C=calibration rotation, R=pose rotation, v=world velocity, l=auxiliary,
w=gyro-bg, modeled vehicle velocity is C^T R^T v + skew(l) C^T w.
Take lateral/vertical components (indices1,2), residual their negatives.
H has velocity block C^T R^T, gyro-bias block -skew(l)C^T,
calibration block C^T skew(R^T v)+skew(l)C^T skew(w),
auxiliary block -skew(C^T w), and remaining blocks zero; keep rows1,2.
Noise variance: w4 false ->0.1; w4 true,w5 false ->0.001;
w4 true,w5 true ->0.02. Argument names remain flag4/flag5 until caller
semantics are established, avoiding invented UI meanings.

This preserves native offset compensation rather than a generic zero lateral
velocity rule. Gyro and offset coordinate conventions remain upstream input
requirements. Heading observation/selection, history/reset lifecycle and
TMC runtime integration remain incomplete.

### 航向/姿态观测 +7d4a0c（Python 已对照原函数）

新增 `vdr_heading_observation.py`，输入采用原生东向为零的角度，尚不可直接传 H5 罗盘 heading。负角度进入无航向分支，使用 R*C 第一列的水平投影；投影长度小于 0.01 时拒绝。目标 yaw 与 R*C 的旋转差 trace 小于 2.24 时拒绝，残差使用两倍四元数向量部分，并非旋转对数。H 的姿态块是 I，安装角块是 R。

负角度按 flag 选择第 0 行或第 0、1 行；有效角度按 flag 选择第 0、2 行或全部三行。仅有效角度且 flag 关闭的三行分支接受正的外部航向方差。其余使用原二进制常量。

验证：`verify_vdr_heading_observation_native.py` 执行完整原函数 440 次，298 次接受、142 次拒绝，逐项比较 H、残差和方差通过；包含四种分支、外部方差及 trace/水平投影阈值附近样本。仅替代分配、内存、三角函数等运行库调用，观测数学逻辑由原 ARM64 指令执行。

本项仍是研究模块，未接入 TMC 运行时。后续需完成观测调度条件、输入坐标/传感器来源及连续轨迹验证，不能将组件对照结果表述为完整隧道导航已接通。

### 观测调度与停车约束（2026-09-28 续）

新增 Python 观测：
- `horizontal_position_observation`：+7d4874，type-8 平面位置约束，保留三维位置观测的前两行。100 次完整原函数对照通过。
- `stationary_attitude_observation`：+7d43dc，停车历史参考姿态约束，H 姿态块为 I；残差为参考姿态与当前姿态旋转差的两倍四元数向量部分。200 次完整原函数对照通过。
- `stationary_bias_observation`：+7d4564，使用预积分旋转的转置对数、旋转对 gyro bias 的雅可比及参考 bias 校正当前 bias；噪声是持续秒数 × 0.0001 / 25 + 1.5e-6。300 次完整原函数对照通过，涵盖零、微小与普通旋转。奇异雅可比/接近 pi 的原生边缘行为尚未专门验证。

`vdr_observation_dispatch.py` 还原 +7d657c 至 +7d6748 的观测选择，按原顺序组装航向、速度、停车/移动车辆约束、普通位置与 type-8 位置。原生 config 第 4/5/6 位分别控制速度观测、位置 sigma 缩放 0.3 与外部航向方差；GPS 标志及速度/质量边界保留。600 组原指令块对照产生 1651 个观测，所有选择顺序、H、残差、方差以及普通 GPS 位置使用标志一致。测试在组装前停止；停车姿态测试预置历史，尚未验证历史构建及停车 IMU 窗口更新。

另还原 +7d6ca4：仅允许退出校准，不负责重新开启。退出时清零协方差第 15..20 行列，恢复第 15..17 对角为配置的安装角方差。200 次完整原函数调用逐项精确一致。`CorrectionFilter` 已加入该转换和 `correct_prepared_frame`（重设局部原点→选择观测→滤波校正）；输入帧资格、时间顺序和历史准备仍由上游负责。

新确认：+7cfaa0 调用 +7cfbdc 组合前后预积分，并非先前推测的差分；构造停车窗口需要还原组合与偏差对齐。当前仍未接入 TMC 运行时。

组合验证已扩展：`verify_vdr_observation_correction_native.py` 600 组执行原生重设局部原点 + 观测选择 + 堆叠 + 完整滤波更新，对照 `CorrectionFilter.correct_prepared_frame`。累计 1631 个观测，最终旋转、位置、速度、各偏差、安装角、辅助偏移、21×21 协方差与计数器一致；覆盖 100/1000 次更新的旋转归一化和超过 100m 的局部原点重设。测试替代运行库与 GPS valid 虚方法，并跳过 6 处诊断日志调用；未替代观测/滤波数学函数。测试输入是构造的原生状态，不是车机实测连续轨迹，上游时间资格与停车历史生命周期仍不包含在此结论内。

### 预积分组合与连续预测/观测引擎（2026-09-28 续）

`vdr_preintegration_composition.py` 还原 +7cfaa0 / +7cfbdc，并包含 +7cf4a0 的参考偏差重设。两个窗口参考偏差差异达到机器 epsilon 时，先将旧窗口旋转、速度、位移及旋转偏差雅可比修正到新参考，再拼接窗口；样本均值按计数加权。600 次完整 +7cfaa0 原函数对照通过，包括空窗口、相同/不同偏差、epsilon 以下差异，比较所有已建模矩阵、向量、计数与时间。原对象 +240..25f 的最新传感器元数据尚未纳入 Python Preintegration，仅数值滤波部分使用的字段已覆盖。

`vdr_observation_lifecycle.py` 还原已初始化滤波器的 +7d64a0 生命周期：校准退出在时间检查前执行；拒绝时间戳不大于最后观测的记录；重设局部原点；停车按原 flags 维护四个历史姿态或组合 IMU 窗口；窗口时长达到 1900ms 才产生静止 gyro bias 观测；开始移动清空停车窗口与历史。`verify_vdr_observation_lifecycle_native.py` 连续执行 6×60 次完整原函数调用，逐帧比较状态、协方差、计数、局部原点、校准状态、全部停车窗口数值和历史姿态通过。运行库与 GPS valid 虚方法由测试宿主提供；仅跳过诊断日志和进程全局备份发布，不覆盖无效状态的全局备份恢复。

`vdr_filter.py` 将普通/自适应预测 +7d5c20 与上述观测生命周期组合成 `VdrFilter`。`verify_vdr_filter_native.py` 对 360 个连续预测→观测周期执行原函数，与 Python 引擎逐帧一致（状态、协方差、校准退出、停车窗口、历史、重复/倒序观测拒绝）；原生全局历史插入与备份发布未包含，输入窗口资格由上游负责。重复时间戳测试保留原函数行为：预测调用本身并不因观测时间重复而自动跳过，不能用观测去重替代上游窗口去重。

当前这是可连续运行并经原函数对照的已初始化 VDR 核心，不是完整 TMC 导航接入。仍需原生输入窗口生产/运动分类与初始标定状态机、真实传感器来源及坐标方向适配、输出/隧道匹配连线；车机 H5 geolocation 的持续经纬度不能直接替代该普通 VDR 分支的三轴 IMU。现有 TMC 导航运行路径尚未改为此核心。

### 原生运动分类与窗口标签（2026-09-28 续）

`vdr_motion_classifier.py` 新增 `MotionClassifier`，对应构造 +7bb434、输入 +7bb58c 和计算 +7bb84c。三轴陀螺仪与加速度模长组成 4 列，经过原生二阶滤波后维护 25×4 窗口。首次和第二次输入保留原函数特殊初始化公式，不套用通用滤波库。满窗口后，使用加速度模长标准差 <0.02、范围 <0.05、最大 gyro 标准差 <0.003490658503988659 判为 motion=0，否则 motion=1；进一步 gyro 范围阈值决定 stable 标志。未满窗口为 -1，重复查询未更新数据时不重新计算。

`verify_vdr_motion_classifier_native.py` 原函数执行 1200 次输入/查询，逐项比较原始三行缓冲、25 行滤波缓冲、全部统计量、状态与 reset；通过。状态覆盖未就绪 73、静止 432、运动 695 次。这不证明浏览器有实际可用 IMU。

外围 `MotionDetector` 对应 +779f3c/+77a100：motion=-1 时 detail=-1，motion=1 时 detail=0，静止时按发布次数累加至 100。原 config 字节 +8 的 bit7 启用静止 gyro 均值估计；stable=1 且窗口计数至少5才参与，前后均值最大轴差大于0.001则清空累计，超过1200000ms同样清空，累计至少25才写入扩展记录 +320。reset +77a0a0 只清分类缓冲和 detail，保留 bias 累计字段，Python 按原行为实现。

`verify_vdr_motion_detector_native.py` 执行 900 次完整 float32 采样适配 +77a0cc 与 180 次完整发布 +77a100，对照 motion/detail/stable、gyro bias、累计计数、诊断向量、超时与 reset 通过。诊断输入集合仍以 sample_vectors 称呼，未据字段位置擅自赋予物理语义。

已进一步定位输入窗口器：+77c358 → +7dbebc，其 +530 为当前扩展预积分、+148 为保留窗口；+773adc 输入预积分并保存样本/最大间隔。+7dbebc 在采样中断、新有效定位和时间到期走不同分支，再通过 +7dbbac 向注册监听器发布。默认配置解码为 +0=500、+4=240、+8=500、+c=200、+10=30000，+14 初始-1；具体字段语义仍按原分支核对，尚未移植此完整窗口器，不能直接用分类器的25样本窗口代替它。TMC 运行时接入仍未完成。

### 输入窗口筛选与调度移植（2026-09-28 续）

`vdr_window_gps.py` 还原 +7dbd14。原生有效性 +768734 使用事件类型/时间与 (181,91,0) 无效坐标哨兵，不是经纬度范围校验；生产入口仍应独立校验外部数据。连续有效 GPS 间隔不足500ms拒绝；距离小于0.01m且报告速度大于1时拒绝。距离使用 +7643c4 的球面公式与直径12756274。`verify_vdr_window_gps_native.py` 完整执行500次原函数（含失效哨兵、无效类型、倒序、同坐标不同速度），178接受、322拒绝，决定与保存定位一致。

`vdr_window_producer.py` 还原 +7dbebc 的窗口调度：当前预积分与保留预积分两个缓存，普通周期500ms，延迟窗口240ms。新有效 GPS 到达时可组合两个缓存并立即发布；到期分段后等待延迟窗口，发布主窗口与随后窗口一对；采样间隔严格大于200ms触发中断，特定位启用时阈值1000ms，重置当前积分并通知中断。原函数未初始化 GPS 前的一些不发布行为照实保留，未自行补发或编造数据。

`verify_vdr_window_producer_native.py` 构造真实原生窗口器，完整执行1200次 +7dbebc，观测60对发布窗口；逐项比较所有已建模预积分矩阵/向量、时间/计数、当前与保留缓存、调度时间及 gap 回调。包含0/20/40/200/201/1000/1001ms步长、新 GPS 与断续 GPS、普通/放宽间隔两模式，通过。数学与窗口函数未替代；监听器列表为空，仅在发布入口读取数据，尚不覆盖监听器对扩展字段的写入。

当前 Python 窗口器的参考 bias 由字段提供，尚未连 +7dbe34 的加权 bias 历史及30000ms刷新；扩展记录中的完整采样列表、运动分类/标定/GPS扩展字段仍要与监听器链路组合。下阶段应追 +7dbbac 的注册观察者调用次序，而非把这次空观察者窗口验证当作完整 TMC 输入链完成。

## Window observer dispatch (2026-09-28)

Static disassembly of `libamaploc.so` at `77b308` confirms that the window
publication listener first checks the processed byte at extended-window `+3e0`.
For an unprocessed window, it calls `779a34` for every observer in root `+9cf8`,
then invokes slot `+18` on every enabled observer, then invokes root `+d30`
slot `+18` with GPS and the sample vector. `77384c` marks the window processed
and clears the sample vector length. Registration order is root `+18c0`,
`+19e0`, `+97c8` (MotionDetector), `+9928`.

`779a34` requires both observer bytes `+10` and `+11`. It iterates 64-byte
sample pairs, passes timestamp from sample `+0c`, and uses an empty GPS object
for all but the last pair; the last receives the window GPS. All observer
replays finish before any publication callback. The producer's immediate
per-sample root callback `77b300` instead forwards to filter manager `7b49bc`;
it must not be mistaken for this deferred classifier replay.

`tools/amap-app/vdr_window_dispatch.py` ports this isolated ordering contract.
Its regression test checks ordering, observer enable/replay flags, final-sample
GPS, sample clearing and duplicate suppression. This is a static-derived port
with a passing Python regression test, not whole-function native equivalence.
The trailing root `+d30` callback and subsequent `77b628` state machine remain
to be connected; no production navigation integration is claimed.

### Native dispatch verification and manager call order

`verify_vdr_window_dispatch_native.py` now executes original ARM64 block
`77b360..77b3e0` and the original replay loop `779a34`: **2048 cases match**
Python event ordering, callback arguments, processed byte and sample-vector
length. Cases cover 0/1/2/17 samples, all 256 enabled/replay flag combinations
for four observers, and both processed states. Observer bodies and empty GPS
construction are boundary stubs; this is not a whole-manager or whole-engine
equivalence result.

The ordinary filter branch (global configuration byte +9 bit4 clear) is now
traced through the manager: `77b628 -> 7b4a78 -> 7d5c20` predicts first;
`77b628` then dispatches the navigation state handler; subsequently
`7b4c04 -> 7d64a0` performs observation correction. State handling must occur
between prediction and observation, not after a combined process_window call.
The immediate sample callback `7b49bc -> 7d6df4` only updates a flag from an
optional type-2 object in this filter, while its additional pose branch can
advance another pose. It does not itself call `7d5c20`.

The configuration bit4-set alternative instead queues prediction objects
(`7b36ec -> 7b4388`) and invokes a different manager (`78fa54/78fb94`); this
branch has not been replaced with ordinary filtering. At `77bf00`, state2
requests state4 once extended +278 reaches20 (configuration byte8 bit0 clear)
or exceeds5 (bit0 set). At `77bf70`, state16 requests state32 with reason16
only when +278 equals0. These predicates do not establish +278 as GPS validity,
and `77ae18` transition side effects still require faithful integration.

### Manager transitions and observer activation

`vdr_state_transition.py` translates full `77ae18` bookkeeping and `7799dc`
activation gating. Native comparison passes 1000 sequential manager calls and
1000 observer calls, including same-state reason changes, state64 notify-only,
nonpositive timestamps, signed32 elapsed wrap, and signed state-mask tests.
Logging and callback bodies are stubbed; manager observer vectors are empty in
this verifier, while the activation routine is independently executed in full.

Manager notifications occur before state mutation. Same state/same reason is a
no-op. Same state/new reason emits notification with state age zero, then only
updates reason and reason timestamp. New state64 emits notification but retains
all fields. Other new states update state/reason/timestamps, activate the first
observer list then the second, and finally invoke root+d30 slot+20 with
(timestamp, previous state, new state). `7799dc` enables a previously disabled
observer only if signed(mask & state)>0, stores its start timestamp and calls
slot0. Leaving that mask clears enabled/start=-1 and invokes slot8.

Enable/disable callback bodies, the trailing manager callback and the alternate
filter-manager branch still need integration. This does not establish a working
TMC inertial-navigation session.

### Motion observer connected to dispatch and activation

Constructor constants decoded as packed int32 pairs: address79790=(62,-1),
7c698=(63,-1), 79c50=(12,-1). Thus observers at root+18c0/+97c8 use mask62,
+19e0 uses63, +9928 uses12. Their replay flags are respectively true/false/
true/true in registration order. Vtable a18658 slot0 is no-op77c3fc;
slot8 is MotionDetector reset77a0a0, preserving bias accumulation.

`vdr_motion_observer.py` now connects ManagerState activation, deferred window
sample replay and MotionDetector publication. Input vectors narrow to float32
then widen, matching77a0cc. The adapter changes output gyro bias only when
native bias eligibility is met. Integration regression checks repeated windows
reach stationary classification, transitions between active states retain the
classifier, and leaving the mask resets classification while preserving bias.
Two integration/dispatch regression tests pass. These are Python integration
checks on previously verified components, not full native end-to-end evidence.
No sensor units or browser IMU availability are inferred by this adapter.

### Fallback attitude integrated into calibration ingestion

CalibrationWindow now includes the independent acceleration history (decay .99)
and one-shot fallback attitude at 7bd38c..7bd3f4. It records the first sample
as the start time, triggers only for signed elapsed >5000ms, and preserves the
result thereafter. The native-comparison harness now compares its readiness,
start timestamp and inline column-major 3x3 matrix on every ingestion call.
All1200 native ingestion calls pass, including queues/interpolation and two
calibration batches. GPS-quality admission remains outside this comparison.
The initial verifier incorrectly treated the inline matrix as a dynamic header;
this was corrected to read the inline72bytes, matching the existing native
attitude verifier and the actual store layout.

Integration priority: complete the calibration observer and connect manager
prediction/state-transition/observation/output as one continuous session before
claiming TMC availability. Isolated native matches do not establish that session.

### Producer -> motion -> calibration continuous integration

InputWindow now retains float32 paired sample records and composes them when
retained/current windows merge. The full native producer verifier additionally
compares every sample timestamp and both vectors for each publication and both
live buffers; all1200calls/60publicationpairs still match.

CalibrationObserver connects mask12 activation, float32 deferred ingestion,
GPS validity/accuracy<=20/speed admission, preferred/fallback output matrices,
and stationary gyro-bias accumulation. This implements byte8 bit3-clear behavior;
optional attitude adjustment is not implemented. Byte8 bit7 selects whether
MotionDetector or this observer supplies bias. GPS.position_sigma and
zero_speed_valid are native-contract inputs; no H5 equivalence is claimed.

A continuous integration test now feeds400 paired samples through WindowProducer,
window dispatch, MotionObserver and CalibrationObserver in native registration
order. It obtains stationary labels, fallback attitude and gyro-bias output,
and checks retained/reset behavior across activation changes. Three pipeline
regressions pass. This is prepared input through calibration, not yet automatic
manager initialization, complete GPS admission observers or TMC navigation output.

### Initialization history handoff

Traced77ba80: scans newest to oldest in root+9d28 ring, stops at the first
record with +130false, skips negative/NaN direction, and replaces its selection
whenever7b45e0(timestamp) permits replay. Thus the result is the oldest eligible
record in that contiguous suffix, not simply the latestGPS. For the ordinary
filter,7b45e0 delegates to7d6e14 history timestamp coverage.

vdr_initialization_history.py now selects that record and hands its timestamp,
direction, speed, origin, calibration matrices and gyro bias to initialize_pose.
The current window's matrix readiness determines requested state16 vs8. It does
not install the historical pose as a current fix: manager restoration/replay
must still advance it. Tests cover quality breaks, unavailable history, unknown
headings, fallback state8 and the pose handoff. Two related integration tests pass.

Additional source evidence: +278 is written by779c60 from observer+110, incremented
to100, and reset to0 by779ba4 when its sub-detector+20 is zero. It is not a GPS
validity bit. Its underlying76cb90/7bf738 algorithms remain required; callers of
prepare_initialization supply this native quality field explicitly.

### Full-initialization replay ordering connected to the filter

7b483c routes ordinary mask0x7f restoration to7d7060. This resets the filter,
copies the initialized pose, rebuilds covariance via7d51f8, and visits native
history oldest-to-newest. Windows older than the initialization timestamp are
skipped. Equal timestamps only observe; newer timestamps invoke the manager
slot+38, predict7d5c20, then observe through7db910 (x2=null,w3=1).

vdr_initialization_replay.py connects this ordering to VdrFilter using prepared
ReplayWindow observations. before_predict is a required callback rather than an
implicitly omitted manager operation. The regression advances a historical pose
through four500ms windows, checks20m eastward travel at10m/s, finite covariance,
current timestamp and coordinate output, and catches double prediction of the
initialization window. It passes. This is a synthetic integration check, not
whole7d7060 native equivalence: lifecycle reset hooks, real before-predict callback,
upstream quality/heading observers and manager live output are still pending.
Partial-mask restoration and the alternate manager branch are not implemented.

### Replay callback identified: quality estimator, not an empty hook

The manager allocated by776c60 uses vtablea18558; slot+38 is777ba0.
The callback validates the pose, predicts a temporary pose and retained historical
poses, accumulates12 statistic windows, and calls777a9c. It exports scores via
77823c (+590),778244 (+598), and readiness77824c (+5a0). It is not yet safe to
replace this callback with a no-op in a complete manager.

777a9c calls77770c for the first score. Constructor776c60 creates a model handle
through4ff2f0(type6) at+788. 77770c converts the feature vector to float32, sets
named model input via virtual+10, invokes virtual+60, reads named output via
virtual+70, and converts the first float result to double. The actual resource
and model format must be identified before this inference path can be ported.
The second score uses55 normalized linear features: constructor copies means
fromb0320, scales fromb04d8, coefficients fromb0690 (each440bytes), and bias
bits406cf2b18548a9bd. The linear result is clamped to0 when negative and updated
only when GPS passes the native virtual validity check. This finding supersedes
any assumption that the before-predict callback is merely optional logging.

Next concrete dependencies: resolve4ff2f0 model resource/type6 and trace feature
assembly7772b8, then reconnect this callback in initialization replay. No model
outputs or quality flags are synthesized to bypass this missing behavior.

### Quality model resource contract resolved to registry type6

Factory4ff2f0 stores type6 in a4feb3c wrapper. Default registration47bc30..47bc4c
maps type6 to `amap_bundle_loc_vdr_confidence`, resource mode1, flagfalse;
4fe254 stores the entry and4fe35c resolves it by type. Input string9612a is
`features`; output93f82 is `mlp/layer_confidence/confidence`. The
`vdr_confidence_model` string is a separate config-key registration7f06b4,
not the model filename. No same-name ZIP entry was found; bundled containers
or runtime resource delivery are not yet ruled out.

inspect_vdr_model.py reproducibly extracts this contract plus55means/scales/
coefficients and the linear bias from the SHA-pinned ELF. It succeeded and
saved ignored local vdr-model-contract.json. resource_resolution_verified stays
false. The next unresolved layer is4ff384 resource mode1 dispatch to4ff5c4 or
the resource service, not the neural input/output names.

### Native unavailable-model behavior verified

77770c initializes d8=-1 through779974. Missing manager handle, readiness=false,
or null model return that sentinel. verify_vdr_quality_unavailable_native.py
executes all three complete function paths, stubbing only the external readiness/
model virtual calls: native returns-1 in each case and matches Python.
vdr_quality_inference.py preserves this contract and float32 feature/output
conversion. It does not replace the unavailable model with a guessed score.

Important correction: model-file availability is not by itself a reason to stop
porting the pipeline. Native explicitly supports absence. Downstream treatment
of the-1score remains to be verified before claiming navigation equivalence.
Actual input tensor shape/runtime adapter and successful model inference remain
unverified. 4ff5c4 constructs callback500c30 then invokes resource-service slot0
via5054c0; model resource resolution is delegated outside this wrapper.

### Output status consumer77b114

The direct output-status update checks manager slot+20 (77824c, byte+5a0),
not its score accessors+10/+18. For state8/16/32 with that readiness flag,
root+58 becomes1; root+65 is1 except state32; root+66 is1 in state16 or
state8 after a strictly exceeded positive root+14 delay since root+20.
Other states or absent readiness clear these flags. It does not inspect-1
neural confidence here. This evidence is local to77b114, not all consumers.

vdr_output_status.py ports flag assignments and ordered events: quality3/2,
motion8/9,missing10/11,flag654/5,flag666/7. Missing window retains previous
quality/motion/missing fields. Tests cover running->retaining->unstable,
strict timer boundary, readiness loss and retained fields; the output test
and initialization replay test pass. Native full-function parity and the
remaining score consumers are still pending. Native unnamed flags deliberately
have not been relabeled as accuracy or permission to navigate.

### Initialization quality sensor gate

Tracing779ba4->7bf738 shows initialization quality is driven by an IMU posture
stability detector, not a GPS-validity counter. Its gyro gate7bf980 is now ported
in vdr_gyro_quality_gate.py and matched against1006 complete native calls.
All three absolute float32 gyro components must exceed1.5 to trigger; one large
axis alone is insufficient. Recovery requires strictly more than3000ms since
trigger and all components strictly below.25. Native threshold equality and NaN
behavior are covered. Status is cleared on trigger; this routine only returns
recovery eligibility, it does not set status back to1 itself.

The surrounding7bf738 combines this with7bfa44 posture statistics once per1000ms;
25 posture vectors are retained and thresholds are2/3/15 for its three angular
statistics. Upstream orientation76cb90 and that angular-statistic gate remain to
be connected before deriving +278 automatically. Current flags are not synthesized
from GPS speed or treated as vehicle movement without the native sensor path.

### Posture quality detector connected

vdr_posture_quality.py translates7bf738/7bfa44 and composes the verified gyro
gate. It keeps25posture vectors and consecutive-vector angular differences,
evaluates every>=1000ms, and requires change-angle std<2, angle-to-mean std<3,
maximum angle-to-mean<15. Angle762780 uses acos(dot/(normA*normB+1e-8))*180/pi.
Population variance was traced via76210c/76216c; column means via764954.
The status/recovery combination retains the native unknown/not-ready behavior.

verify_vdr_posture_quality_native.py executes800complete7bf738 calls after the
real constructor, covering stable posture, varying tilt, all-axis gyro triggers
and recovery. Status, last-trigger and evaluation timestamps match Python.
The native dependencies including angle/statistics run unmodified; allocator,
memcpy and platform math calls use the standard harness runtime. The preceding
orientation update76cb90 remains required before feeding actual gyro/accel to
this detector; no H5-only posture was fabricated.

### 2026-09-29: continuous orientation → initialization-quality observer

Added `vdr_orientation_quality.py`: native 25 Hz attitude feedback (P=.5,
I=.01), acceleration initialization, posture stability input, reset and window
quality counter publication. Counter output can now be placed on MotionWindow.
`verify_vdr_orientation_quality_native.py` executed 2,000 full 76cb90 calls:
rotation and integral feedback agree at 1e-12 tolerance. Quaternion comparison
explicitly permits equivalent opposite signs; this is not bitwise parity.
A further 800 full 779ba4 calls, with 779c60 publication every 13 samples,
match native counter state and published quality through repeated disturbances.
This joins raw native-coordinate sensor samples to the existing stability
module. Production TMC wiring, GPS-direction observer and complete manager
initialization/output remain incomplete; this does not establish working
vehicle inertial navigation.

### GPS direction and shared initialization observer pipeline

Ported default 779d40 publication into vdr_direction_observer.py. Native
constructor limits are 1,500 ms, position sigma 20, speed 3/5, movement 5 m,
angle difference 10 degrees, and missing-fix timeout 5,000 ms. Direct/zero-speed
flags are retained as explicit native inputs. Optional configuration-bit-1
estimator 782ae0 is an explicit callback, not silently approximated.
800 complete default native publications agree for heading and missing-fix
fields, including invalid fixes and low-speed admission. Added a continuous
500-sample pipeline test through producer, orientation quality, GPS direction,
motion, and calibration in native registration order. Both pipeline tests pass.
This exposes quality, direction and fallback attitude together; manager
initialization/replay/output and production TMC integration still remain.

### Initialization handoff assembled

Re-read 77b58c: history eligibility is exactly window quality != 0; snapshot
copies window timestamp, direction, GPS, both calibration matrices and bias.
Added record_from_window and vdr_initialization_handoff.initialize_from_windows,
joining selection/pose construction with required manager reset and prediction
callbacks, covariance initialization and chronological replay. A synthetic
history test selects the oldest replayable qualified record, verifies reset
before all prediction callbacks, advances position 20 m over 2 s, and verifies
quality rejection has no manager side effects. Three history/replay tests pass.
This is an integration test with explicit test callbacks, not native whole-root
parity. Production manager callbacks, state transitions and output publication
are still required before connecting this engine to TMC.

### Running-state decision wiring

Added vdr_running_states.py for 77bf00 (state2 quality threshold), 77bf70
(state16 quality loss -> state32/reason16), and 77bd0c decision ordering.
36 complete native state2/state16 calls match emitted state/reason/forced
requests with transition and logging boundaries intercepted. State8 keeps
matrix comparison, history selection, reset/replay and notification callbacks
explicit. Two Python tests cover upgrade callback ordering, calibration
observer deactivation, equal threshold, missing history and quality-loss
configuration choices. State8 full native parity and state32 recovery are
not yet established; matrix difference and replay side effects remain caller
obligations. No production TMC route has been changed by this work.

### Recovery state32 control flow

Added vdr_recovery_state.py from 77bfc4. Reason16 can restore to16 before
checking missing-fix/deadline; reason8 optionally restores to8 at quality>=6
and nonnegative (non-NaN) direction. Timeouts preserve strict boundaries and
signed32 deadline addition. Caller transitions must mutate manager state so
post-restoration deadline checks see the new timestamp. 216 full native
77bfc4 invocations match timeout/missing-fix requests with quality0 (no estimator
or restoration exercised). Two Python tests cover successful callback ordering,
updated deadlines and NaN rejection. Native partial restore7d7060 masks60/61,
7bde68 recovery estimator and their covariance updates remain unimplemented;
explicit callbacks are not a production replacement for them. TMC not wired.

### Native partial restoration masks60/61 implemented

vdr_partial_restore.py now implements complete ordinary7d7060 partial branch
for recovery masks60/61. It retains P[:9,:9], clears all covariance rows/columns
from9 onward, restores configured gyro/accel bias diagonal variances and only
incoming mounting diagonal15..17. It copies mounting rotation, optionally pose
rotation(bit0), sets calibration enabled, and preserves all other pose bytes.
No auxiliary/bias/position/velocity copying or historical replay occurs here.
200 full native7d7060 calls compare every covariance entry and all changed and
retained pose bytes exactly. VdrFilter.restore_recovery exposes this operation;
a lifecycle test checks position/bias/timestamp/correction count/stationary
history are retained. Actual recovery candidate estimator7bde68 and preparation
of incoming covariance, manager quality callbacks and TMC wiring remain open.

### Fallback recovery candidate installed

Implemented reason8 recovery preparation77c194..77c280 in
vdr_recovery_candidate.py: acceleration basis, yaw multiplied by transposed
basis, installation matrix, and mask61 covariance input. Default covariance
is cleared entirely then installation diagonals set to.001; config byte9 bit4
retains caller covariance. 100 complete77bfc4 reason8 calls compare captured
7b483c arguments (rotation, installation matrix, all covariance values and
mask). Restoration/transition boundaries are intercepted in this verifier;
partial restoration itself has separate200-call native parity. A combined
Python test uses real candidate generation and real filter restoration before
state32->8, retaining position and enabling calibration. Three recovery tests
pass. Reason16 estimator7bde68, quality manager and production TMC integration
remain incomplete; this is not complete navigation validation.

### Aligned recovery estimator and restoration

AlignedRecovery now ports7bde00/7bde68: last accepted nonnegative direction,
R-transpose times yaw installation matrix, last-direction/current timestamps,
strict 2,000ms readiness lifetime and original variance constant. 400 complete
native updates match matrix, timing, variance and readiness, including NaN and
missing direction. Its restore method builds mask60 input covariance with
(sum of attitude/installation standard deviations)^2 and calls real partial
restoration. A Python test verifies variance installation, retained pose rotation
and expiry without writes; four recovery tests pass. Whole reason16 caller
covariance preparation has not yet had native argument capture parity. Quality
manager callback and production TMC input/output integration remain incomplete.

### Quality score evaluation and lifecycle

vdr_quality_scores.py implements777a9c readiness gates, signed evaluation
interval, optional-model primary result and55-feature linear secondary score.
Parameters are supplied from the pinned APK extractor, not guessed defaults.
Reset follows7778b4/779894: scores=-1,last evaluation=-1,ready=false; first valid
pose activation uses(.1,0) from777bf0. 500 native777a9c calls match cadence,
scores and timestamps; GPS validity and feature extraction are boundary stubs,
while unavailable-model inference and linear arithmetic execute natively.
Upstream pose/history feature extraction in777ba0/7772b8 is still required.
No complete quality-manager or production TMC integration is claimed.

### Quality feature histories and55-feature assembly

Added vdr_feature_history.py ring insertion/full readiness, zero/reset behavior,
means, population deviations, sentinel-limited minima/maxima and7772b8 feature
assembly. Native comparison:240 insertions and960 statistic outputs across
1/5/25 capacity and1/2/6 dimensions, including NaN, all match. A full native
7772b8 call matches all55 feature positions across12 populated histories.
Actual pose/window-derived values feeding these histories in777ba0 are still
unimplemented; this does not replace them with synthetic statistics. Complete
quality manager and TMC wiring remain open.

### Pose and covariance feature input projections

vdr_quality_inputs.py implements grouped norms776ff4, vehicle velocity7781cc
(C^T R^T V) and vehicle Euler angles6adeb4 (R C). 800 full native helper calls
match randomized vectors/rotations. Added collect_quality_inputs feed ordering
from777cd4..777fdc: biases, lateral/vertical velocities, roll/pitch, altitude,
attitude/direction differences, residual category norms and covariance norms.
Full feed function and temporal pose-history update still need native parity;
individual helper checks do not prove complete777ba0 equivalence. No production
TMC integration is claimed.

### Continuous quality-manager assembly

Added vdr_quality_manager.py using constructor-confirmed2 retained poses,
5,000ms strict shift cadence, first history20 samples and remaining histories10.
It propagates current/retained poses, shifts current unpredicted pose into the
retained list, feeds actual pose statistics and evaluates55 features using
readiness histories0/7/9 (native5cc/6e4/734). Reset clears histories, retained
poses and score state. A continuous29.5s synthetic IMU/pose test reaches score
evaluation with real feature collection; linear coefficients are test-only and
neural output remains-1. Full777ba0 differential verification is still required,
including residual/covariance feed and temporal history. TMC remains unwired.

### Whole continuous quality callback parity

verify_vdr_quality_manager_native.py now executes100 complete777ba0 callbacks
with actual native pose propagation,12 history updates,55-feature extraction
and score evaluation. All ring contents/index/full flags and both scores agree
with QualityManager across50 seconds of IMU windows and alternating residual
categories. Neural model is absent (original-1 path); only GPS validity and
standard allocator/math runtime boundaries are hosted. Added before_predict
adapter and explicit direction/residual fields to ReplayWindow; missing
residual raises rather than fabricating a category. Existing replay and manager
integration tests pass. Root manager still needs native residual publication,
window/history orchestration and production TMC input/output integration.

### Actual filter correction vector feeds quality callback

Traced7d68b8..7d68e8: category is ordinary GPS-position observation use(0/1),
followed by21-dimensional Kalman state correction, not raw measurement residual.
7d6ea8 resets category to-1. CorrectionFilter now publishes this22-vector only
when an observation updates state; empty observations preserve it. QualityManager
before_predict reads the previous vector directly from the engine. Extended
existing360-cycle native filter comparison verifies all22 entries alongside
state/covariance/history. Replay integration test now executes real observation
corrections and real quality callback until feature histories and evaluation
are ready (test scoring coefficients only). Three replay tests pass. Root
window lifecycle, external-input conversion and production TMC wiring remain.

### Root window lifecycle wiring

Added vdr_window_lifecycle.py from77b308/77b628 ordering: initial state1->2,
observer replay/publication, history snapshot, quality-before-prediction,
prediction, state handler, conditional gap inflation, observation/lookahead,
bias publication/feedback, output status and output callback. Reprocessed
windows skip observers but still enter manager/history, matching native flow.
Ordering test covers startup, reuse and state4->8 reinitialization exception.
Filter manager dependencies remain explicit; this is not a complete engine.
Bias feedback confirmed7dbe34 accumulates gyro/accel in weighted histories,
while7dba7c refreshes cached biases only after configured interval and gate.
Producer feedback routines are implemented below; the concrete root adapter
remains outstanding.

### Producer feedback and synchronous publication

WindowProducer now implements 7dbe34 accumulation with two decay-0.9 histories,
and 7dba7c cached-bias refresh. Native constants are 30000 ms and initial refresh
timestamp -1000. Refresh requires a positive timestamp, the GPS restart gate,
and strictly more than 30000 ms since the previous refresh. Neither gap resets
nor lookahead splits refresh the biases; histories survive refreshes.

The optional synchronous on_publish callback runs before GPS-triggered refresh,
so root filter feedback can affect the new integration window in the same call.
Returning publications alone cannot preserve this native listener ordering.
The native producer verifier now executes 1200 actual 7dbe34 calls alongside
1200 full 7dbebc calls, comparing cached biases, refresh timestamps and all
current/retained/publication integration fields. Passed. Two focused Python
tests cover synchronous feedback ordering and strict refresh gating. This
closes producer feedback but does not establish a complete production engine.

### Ordinary filter manager and lookahead output

Added vdr_filter_manager.py to implement the ordinary prediction/observation
branch of 7b4a78/7b4c04. It invokes the real quality manager and VdrFilter,
copies the corrected pose for output, and advances only that copy with a
nonempty lookahead integration (78b9b8). The core filter never consumes that
lookahead early. Output time is maintained separately from pose initialization
metadata. State handlers, gap handling, bias publication and observation-field
conversion remain explicit required dependencies; this is not yet a standalone
root engine or production TMC integration.

A real-filter regression test runs successive windows at 10 m/s: filter at
5 m, lookahead output at 7 m, following filter at 10 m rather than 12 m. It also
checks output mutations cannot alter the filter. Passed, along with the
existing root-window lifecycle test. Full native manager parity remains to
be established; this test verifies the integration invariant, not all branches.

### Root state controller integration

Added vdr_state_controller.py connecting states 2/4/8/16/32 to the existing
real initialization replay, ordinary filter, aligned/fallback partial recovery,
and full reinitialization. State 4 reports native availability reason bits and
returns to state 2 with forced reason 2 on quality loss. Configuration remains
explicit; root transition notifications and reset side effects are required.
The fallback-to-aligned comparison is now concrete: preferred * current.T,
Euler angles in degrees, then maximum absolute component. 200 randomized
comparisons execute actual 77dc80 and 762cdc and agree with the Python function.

Two continuous real-filter tests cover waiting/init/aligned/loss/recovery and
waiting/init/fallback/loss/recovery/full-replay upgrade. The latter verifies
that large attitude differences replace the engine and replay through the
current window. Test configuration is explicit and is not a claim that all
production configuration bits have been recovered. Root input conversion,
gap policy, notification/reset side effects and production wiring remain.

### Prepared-window observation adapter

Added FilterGps and WindowObservation to carry native GPS validity/flags,
uncertainties, quality-as-calibration-state, motion/detail and direction into
the ordinary filter. Configuration flags remain explicit. This converts
internal native-convention windows, not H5 coordinates or sensor units.

Found and fixed missing latest gyro samples: 7cf800 stores the final float32
gyro vector at +250 even on the first time-initializing sample; 7cfbdc copies
the newer window's vector when composing nonempty windows. Preintegration now
retains it and the observation adapter uses it, not the window mean.
Validation: 1000 native preintegration steps check the stored latest vector;
600 native compositions check retention including empty-window branches;
360 native prediction/observation cycles now run Python through this adapter;
all pass. Both state-controller integration scenarios now use the adapter,
and all 23 Python VDR tests pass. Root configuration/reset/gap policy and
production browser/session/output integration remain incomplete.

### Sample gaps and ordinary covariance policy

InputWindow now retains the maximum signed sample interval from 773adc. Full
native producer comparison exposed that extended-window composition resets
this auxiliary field to zero rather than combining maxima; the port follows
that observed behavior. All 1200 producer calls now compare this field too.

GapPolicy implements the 77b728 configuration gate and threshold >=301 ms.
For the ordinary filter, 7d6f00 adds 100000 to covariance diagonals 0..2,
250000 to 3..5 and 2000000 to 6..8, leaving all other entries unchanged.
200 native calls compare all 441 entries exactly. The existing root lifecycle
continues to skip this operation for the native reinitialization transitions.
Added the concrete gap handler to state-controller wiring tests and a threshold
test. All 24 Python VDR tests pass. Browser GPS-only store was rechecked: it
still has no motion-sensor stream, and production navigation remains unconnected.

### TMC browser motion capture entry

Added a real DeviceMotion capture module and a debug-page "惯性传感器" tab.
Capture begins on user interaction, handles browsers requiring explicit motion
permission, rejects partial/nonfinite acceleration or rotation fields, reports
missing complete samples after 5 seconds, and stops on tab unmount/page hiding.
Each complete event exposes a callback for future navigation-session ingestion.
The recorder bounds retained data to 3000 samples and exports local JSON.

Source contract: https://www.w3.org/TR/orientation-event/ . Acceleration includes
gravity in m/s²; rotation beta/gamma/alpha is mapped to device x/y/z in rad/s.
Time is explicitly monotonic receipt time mapped to an epoch, not claimed to
be the sensor's acquisition timestamp. Device axes have not yet been mapped
to the native engine's installation frame. No GPS values are synthesized into
motion samples and this capture entry does not yet drive navigation.

Four capture tests pass (units/null rejection, timeout/stop, cancelled pending
permission and bounded recording/hidden-page cleanup). Vite production build
passes. Full type-check currently fails at the unrelated existing
TencentVideoView.test.ts:137 DOMWrapper.exists typing. Vehicle sensor availability
and full native-to-browser integration remain unverified.

### Continuous sensor-to-filter integration and initialization correction

Added prepare_window with constructor defaults read by executing 77376c:
quality/motion/stable -1, detail 0, direction -1, preferred/fallback matrices
all 10000, bias zero. Root lifecycle now supports retaining each prepared
window after observers and before filter state handling for real replay.

The first continuous integration test feeds 1100 paired sensor events and GPS
updates through producer, all four observers, root lifecycle/state controller,
real initialization replay, prediction/observation, output status and synchronous
bias feedback. It reaches running state and produces more than 20 finite
coordinate outputs without manually supplying initialization quality or pose.
Root auxiliary notification/reset callbacks are explicit test stubs, scoring
coefficients are fixtures, and this is not a complete native-root parity test.

This test exposed a real wiring defect: 77b86c uses historical time/direction/GPS
from its selected record, but reads calibration and bias from the latest ring
slot (77b8bc/77b8c0). The previous Python handoff incorrectly took all fields
from the historical record, which may still have unavailable calibration.
Both initial and upgrade replay now use latest calibration/bias. Added a
regression fixture with unavailable historical calibration and valid latest
fallback. All 26 VDR tests pass; the existing 500-case native pose builder
comparison independently exercises the separate historical/latest pointers.

Exactly parallel synthetic acceleration still exposes the previously documented
native align_vectors singularity (NaN); the continuous success fixture uses a
nonparallel, constant-magnitude gravity vector. No artificial recovery was added
or claimed as original behavior. Production input validation and full-session
native verification must account for invalid orientation results before output.

### Reusable ordinary session

Added vdr_session.py with instance-owned producer, observers, bounded replay
history, manager state, quality, filter, recovery, status, coordinate publication
and synchronous feedback. Native-frame paired samples are accepted only with
finite vectors and positive signed-32 relative timestamps; epoch timestamps
are rejected. Output subscribers receive independent snapshots. Nonfinite or
out-of-range coordinates are not published. Retention and configuration remain
explicit integration inputs; nonzero unstable-delay mode is rejected because
its time reference has not yet been verified.

Resolved default callback semantics through ELF relocations and disassembly:
76dadc installs a18480; its slot18->77a6e4 and slot20->77a728 traverse the group
initialized empty by77a6c8. Base root slots30/38/40 point to77c42c/430/434, each
RET. Quality reset slot28 at a18558 points to7778b4, already represented by
QualityManager.reset. Thus the session's empty default-group/reset-tail hooks
are scoped to these base semantics rather than unresolved test stubs.
Also corrected the publication label:77b76c copies pose auxiliary at root2b0
to root40; actual gyro/accel feedback remains the separate producer path.

New reusable-session tests run1100 input pairs to automatic initialization and
coordinate output, verify independent session state and output snapshots, and
reject malformed vectors/epoch time before mutation. All28 VDR tests pass.
This does not verify the derived application manager, secondary observers,
all configuration branches, browser installation frame, or road matching.
No production navigation endpoint has been enabled by this change.

### Session transport and pending vehicle validation

The vehicle's browser motion-sensor test has not yet been run (user report).
H5 GPS availability does not establish availability of acceleration/rotation
samples. Browser installation-frame and sampling-rate adaptation remain open.

Added authenticated inertial session routes, disabled unless AMAP_VDR_FACTORY
is installed. Sessions have owner isolation, 120-second idle expiry, an eight
session limit, bounded batches and sequence/digest retry deduplication. Responses
are no-store. Failed replacement initialization preserves the previous session;
processing errors invalidate potentially partially integrated sessions.

NativeVdrBatch validates all native-frame samples before integration, rejects
nonfinite vectors and out-of-order relative timestamps, and copies output
snapshots. Three adapter tests pass, including 1100 samples through the real
translated session using explicitly synthetic test configuration. Four HTTP
transport tests pass, covering authentication, isolation, retry deduplication,
disabled configuration and initialization failure. These tests do not validate
browser coordinate conversion, actual vehicle sensors or complete native parity.
The production factory remains unconfigured; navigation has not been switched
to this engine.

### Browser paired recording

The motion debug export now uses tmc-browser-motion-v2 and records both device
motion and unconverted browser GPS with one monotonic receipt clock. Original
GPS timestamps, null altitude/speed/heading, and coordinate provenance remain
explicit; no installation transform or synthetic IMU is applied. Mock GPS is
excluded. Both arrays are bounded to 3000 records and only exported locally.
GPS recording stops with motion capture, and the debug component removes its
location subscriber on unmount. Five capture tests pass, including matching
receipt timestamps, null preservation, snapshot isolation and stop/restart.
This closes the missing GPS portion of future vehicle replay data, not the
browser-to-native conversion or production-engine activation.

### Explicit browser input adapter

Added vdr_browser_input.py for the post-calibration SI input boundary. It takes
an explicit proper installation rotation, acceleration sign and accuracy-to-sigma
factor; none is claimed as a validated vehicle default. Vectors are rotated without
applying the JNI accelerometer g scale a second time. Browser clockwise-from-north
heading becomes native east-zero counterclockwise direction via (90-heading)%360,
consistent with initialize_pose yaw and ENU velocity. Receipt elapsed times become
positive signed-32 relative milliseconds; duplicate rounded times are rejected.
GPS coordinates remain in the supplied datum. Missing altitude/speed/accuracy is
rejected rather than invented; missing heading retains the native -1 sentinel.

Three tests pass: cardinal headings/time/units, proper rotation and invalid-input
state preservation, and 1100 browser-shaped synthetic samples through the adapter,
batch validation and real translated session to running state 8 and output. This
uses explicit synthetic installation/model parameters, not real vehicle calibration.
Cadence adaptation (ordinary observers expect 25 Hz), verified installation and
accuracy conventions, native configuration, HTTP browser streaming and production
navigation output wiring remain unresolved. The factory remains disabled.

### Frontend session transport

Added web/src/functions/inertialSession.ts for already adapted native-frame
samples. It creates one authenticated session, sends ordered batches of at most
100 samples every 200 ms, retries ambiguous network/503 failures once with the
same serialized payload and sequence, and checks batch acknowledgements and
finite/ranged engine output before publication. The pending queue is bounded
at 250 samples; overflow stops the session rather than silently losing IMU.
Stop drops late results and deletes after an in-flight request completes; late
creation after cancellation is also deleted. Requests have five-second deadlines.
Unreachable cleanup relies on the existing server-side 120-second expiry.

Five frontend tests pass for identical retries, snapshots/order, cancellation,
late creation, overflow and invalid output. Fetch is mocked in these tests; this
is transport behavior evidence, not a live browser-to-Flask verification. The
module is not yet wired to navigation and does not imply the engine is enabled.

### HTTP + real engine loss/recovery integration

test_vdr_http_pipeline.py runs 1600 browser-shaped synthetic samples through
BrowserInput, Flask's real authenticated routes, NativeVdrBatch and VdrSession.
It repeats every HTTP batch and verifies the state/history clock is unchanged,
removes GPS for 12 seconds, restores GPS, and closes the session.

The first stronger displacement assertion exposed a misleading prior fixture:
perfectly constant gravity and zero gyro were classified stationary, so the
native stationary observation suppressed velocity despite moving GPS. Merely
checking non-null output had missed this. The moving integration fixture now
includes explicitly synthetic zero-mean 2 Hz, 0.12 m/s² vertical road vibration;
no production classifier or engine behavior was changed to force motion.
It passes a 60–110 m eastward displacement bound across the 12-second gap and
a <10 m longitudinal error bound after GPS recovery, plus missing-fix flag
transition assertions. Those tolerances apply only to this synthetic scenario,
not vehicle accuracy. Test configuration/model coefficients remain fixtures;
real browser streaming, verified production profile and vehicle IMU validation
are still outstanding.

### Actual APK linear parameters in HTTP integration

verify_vdr_http_apk.py now reruns the same loss/recovery/displacement and retry
checks with linear-score parameters freshly extracted by inspect_vdr_model from
the pinned APK, rechecking library SHA-256 rather than trusting cached JSON.
The test passed with libamaploc SHA-256
52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34.
Installation, state/observation configuration and trajectory remain synthetic;
the optional neural backend remains absent. This replaces only the synthetic
linear parameters in this verification, not the production configuration.

Reinspection of 77a824 confirms an external object in x1 is stored at root+18
(77a890) and forwarded to filter constructor7b3f80. Follow-up caller tracing
corrected the earlier interpretation of this object as configuration:76cf24
passes its own manager pointer to77f5dc, which forwards it to77a824. Configuration
flags used by the state machine are instead read from global a523b8.

### Global configuration source identified

inspect_vdr_config_refs.py verifies the library hash and scans direct ADRP
references to the global configuration page;19 candidate instruction contexts
were found. This is not a complete alias/GOT write analysis.
77bf20..77bf34 reads a523b8+8 bit0 for fast-start;77b728..77b734 reads+9 bit0
for gap policy. Static initialization761fa0..761fc8 clears this structure.
Runtime initialization761eb0 guards on byte0, sets it to1 and queries a registry:
7e2a30 obtains the provider;7e2b4c queries IDs12,24,78,52 to bytes1,2,3,5;
byte4 is set1. Crucially761f2c..761f54 queries integer ID141 (0x8d) through
7e2ab8 and stores the result at+8, supplying the state/filter bitfield.
Next required evidence is registry ID141's default and any runtime override,
not an assumed zero value from static initialization. Production remains disabled.

### Registry 141 construction default

7e2848 creates a223-entry table;7e2904 fills it by calling7e1154 for every ID.
The pinned halfword jump table at b9802, index141, resolves to7e1270. That
branch allocates0x38 bytes, sets ID0x8d, branches to7e192c (w2=0) and invokes
7e1f28. Helpers7f1728/7f1678 retain this default in+30 and pass it to7e0fd8,
which writes+20.7e2ab8 returns that+20 integer directly (or-1 for absent IDs).
Thus the constructor default for141 is0, independently of BSS zeroing.

Constructor callback slot40 resolves via RELA a19db8+40 to7e1ed4 (RET).
The following slot20 callback resolves to7f3a84, which walks registered
listeners; it is not itself a configuration loader. Runtime writes/listener
registration remain to be traced before claiming the actual App value is0.
inspect_vdr_config_refs.py now emits the actual table target and construction
instruction chain, with the pinned ELF hash enforced.

### Configuration update path and bitfield evidence

Direct branch scanning found configuration initialization calls at76a404 and
7dcfa4, and a generic registry update call7e33c0->7e2b68. The latter loads the
entry by ID from provider+58 and calls its virtual slot50; it is not proof that
ID141 takes that path. The surrounding7e2b90 dispatcher also contains an explicit
integer update path7e3094->7f1be0->7e0fd8. ID141's dispatcher branch still needs
resolution before excluding runtime overrides.

The current port's flag meanings can now be tied to the shared integer at
a523b8+8: bit0 fast-start (77bf2c), bit2 tolerate-missing (existing native
recovery verifier writes first byte4), bit8 gap covariance policy (77b730),
bit9 retain-on-quality-loss and allow-fallback-recovery (77be6c and existing
recovery verifier writes second byte2), bit12 preserve recovery covariance
(77c070). Other use of bit12 selects the unported alternate filter branch;
it must not be enabled merely to preserve covariance in an ordinary session.
These mappings do not establish every state threshold or all runtime flags.

### ID141 override and root defaults confirmed

The SIMD comparison constants loaded at7e2c00..7e2c6c contain ID141 (at9db20).
Thus an external item found by7e2cd8 takes7e2dac->7e3094->7f1be0, which reads
the item's integer at+28 and sends it to7e0fd8 to overwrite registry value+20.
ID141 can therefore be overridden, rather than always using its constructor0.
The startup snapshot761eb0 reads that registry value once (guard byte0); update
timing and configuration key naming have not yet been established.

Root constructor constant795e8 decodes as int32(60000,180000); the first is the
recovery timeout read at root+10. Root+8 explicitly receives double10, used by
the attitude threshold path. verify_vdr_http_apk.py now uses60,000 ms,10 degrees
and registry141 constructor-default flags0 alongside real APK linear parameters.
The HTTP GPS-loss/displacement/recovery test still passes. Installation,
trajectory and recovery variances remain synthetic; runtime overrides and the
optional neural backend are absent. This is a default-profile verification,
not a claim of matching a specific phone's downloaded configuration.

### Browser cadence and HTTP boundary

Added BrowserResampler as a TMC integration adapter (not APK code): bracketed
linear interpolation onto40 ms ticks, with an explicitly configured maximum
gap40..200 ms. It never extrapolates; a gap above the limit fails the stream
until a new instance is created. It is not an anti-aliasing filter or a substitute
for measuring actual sensor timing. Three tests cover irregular linear input,
snapshot independence and outage rejection.

BrowserVdrBatch composes explicit installation/unit conversion, resampling and
NativeVdrBatch. GPS waits until a grid tick at/after its receipt; adapter state
is staged so malformed later samples cannot partially advance the filter. Two
tests cover cross-batch GPS association and whole-batch rejection. The real
Flask HTTP loss/recovery test now also accepts raw browser-shaped batches via
this boundary. Both native-input and browser-input variants pass with actual
APK linear parameters and confirmed default flags/timeout/threshold.
No production factory or frontend stream is enabled yet; real installation,
sensor availability, input quality and remaining native configuration are open.

### Explicit frontend/backend input negotiation

Session creation now negotiates `native` versus `browser` format and returns
the accepted format. BrowserVdrBatch advertises browser input; the server rejects
an incompatible request before replacing the existing session. Frontend transport
can serialize browser elapsed/acceleration/angularVelocity/GPS fields, snapshots
them independently, and verifies acknowledgements against floor(elapsed)+1.
It rejects format mismatches instead of sending raw browser samples into the
native-frame adapter. Six frontend transport tests, five HTTP transport tests,
and both actual-APK-parameter loss/recovery pipelines pass. Realtime capture and
navigation consumption still need wiring; negotiation alone does not enable them.

### Realtime frontend capture linked to transport

browserInertialStream.ts now connects actual devicemotion capture and fresh GPS
subscriptions to the browser-format HTTP transport. Permission is invoked on the
button gesture before network awaits. GPS arrival uses the capture monotonic
clock; mock fixes and absent required altitude/speed are not sent as measurements.
Stop, page hiding, missing sensors, failed connection and permission cancellation
release capture, subscriptions, timers and the backend session. No previous GPS
fix is fabricated into IMU. Samples before session readiness are not queued.

The motion debug tab includes InertialStreamTest for explicitly starting this
stream, viewing engine results and stopping it; test output does not replace map
position. Server failure messages are shown. Three new stream tests exercise
real synthetic DOM motion events, GPS association, cancellation and sensor timeout;
14 related frontend tests pass. Vite production build and vue-tsc pass. The
production engine factory remains unconfigured, so the real UI reports unavailable
until configuration is supplied. Browser live-to-server and vehicle validation
remain outstanding; mocked transport tests do not establish either.

### Explicit server runtime profile loader

flask_app startup now calls configure_inertial_runtime. Server-admin environment
TMC_AMAP_VDR_PROFILE (or app.config AMAP_VDR_PROFILE) points to a JSON profile.
Absent configuration remains disabled; invalid configuration logs the exception
and leaves the rest of TMC available. Status reasons distinguish profile_missing
and profile_invalid, and readiness is explicitly experimental.

Profile schema is tmc-vdr-profile-v1 with:
- apk: path to the pinned APK, relative to the profile file or absolute;
- registry141: currently must be integer0 (verified constructor-default mode);
- installation: explicit rotation3x3, acceleration_sign(+1/-1),
  accuracy_to_sigma(positive), maximum_gap(40..200 ms);
- recovery_variance: positive gyro and acceleration values;
- observation_flags: explicit boolean flag1 and flag2.

vdr_runtime.load_factory validates the profile, extracts real linear parameters
after APK hash verification and creates independent BrowserVdrBatch/VdrSession
instances. It uses confirmed60-second recovery timeout,10-degree threshold,
600-entry retention and ordinary default flags. No installation/sign/uncertain
covariance values are silently supplied. NumPy and pyelftools were added to
the existing packaged amap tools requirements. No production profile is supplied
or auto-enabled by this change. In-memory sessions require the existing single
Flask process; multiple-worker deployment would need routing/shared state design.

Three runtime-loader tests pass. The actual-APK verifier now builds its synthetic
profile through this runtime loader (rather than test-only session construction)
and both HTTP pipelines still pass. Sensor installation, browser-to-live-server
verification and navigation publication remain outstanding.

### Navigation output wiring

AmapAppView now starts browserInertialStream when live navigation begins with
amap-vdr selected. New engine positions update marker, route progress, heading
and speed through the existing coordinate conversion. Browser GPS remains the
fallback during initialization or after1500 ms without fresh engine output.
Repeated, future and stale timestamps are rejected. Exit, simulation, unmount
and preference changes close the stream. Failures display their fallback reason.
Unconfigured deployments still fall back; no vehicle profile is auto-installed.

estimated_accuracy is TMC-derived, not a native APK field: separately predict
output covariance through lookahead, project with the position Jacobian, then
take sqrt(5.991*largest horizontal eigenvalue). This is a Gaussian-model95%
ellipse major radius, not calibrated vehicle accuracy. Invalid covariance
prevents publication. Output prediction does not mutate filter covariance.
Horizontal speed and heading come from output velocity.

41 Python VDR tests, frontend type checking and Vite build pass. Both actual-APK
HTTP pipelines pass after the output change. Live browser-to-backend/vehicle
verification and installation configuration remain open. This wiring does not
prove navigation accuracy or parity with the App's derived manager, optional
neural backend and alternate filter branches.

### Cross-process HTTP verification (2026-09-29)

`verify_vdr_live_http.py` now passes: Windows Node with synthetic jsdom motion
events sends actual HTTP to an ephemeral WSL Flask server using the deployed
runtime loader and pinned APK coefficients. The test sends 1600 samples,
withholds GPS for 12 seconds, checks 60–110 metres of eastward displacement,
then checks GPS recovery and a finite nonnegative uncertainty output.
It uses an explicitly synthetic installation profile, not vehicle calibration.

The initial startup failure was test infrastructure: jsdom AbortSignal was
incompatible with Node fetch. The test now retains Node's networking realm and
only supplies DOM surfaces from jsdom. Node also needs to retain Flask's updated
session cookie; the test adapter now does so. Neither issue required weakening
production authentication or removing cancellation. The actual live HTTP test
passes in about 14 seconds; frontend type checking also passes.

Navigation GPS callbacks now leave the displayed speed untouched while fresh
inertial output owns the position, avoiding mixed-source position/speed updates.
Actual browser page lifecycle, vehicle IMU availability/installation and tunnel
accuracy remain unverified. This test does not establish full native App parity.

### Navigation freshness and fallback correction

The navigation publication gate now deducts sensor-to-response delay from its
1500 ms freshness budget. Previously a 1400 ms old result could suppress GPS for
another 1500 ms after receipt. Results at or beyond the age limit, repeated or
future timestamps, invalid speed/heading, and uncertainty above the existing
60 m navigation threshold cannot take ownership of navigation position.
Reset clears both ownership and missing-fix recovery history between sessions.
Two gate regressions and nine transport/capture tests pass; frontend type
checking passes. This is TMC publication policy, not a new native-engine claim.

### Native recovery variance constructor evidence

Located filter constructor 7d5080, called at 7b4014 with manager+4f8.
7d511c loads the pair at 9d2e0; 7d512c writes its second double (9d2e8)
to filter+48. 7d5138 loads 9e870; 7d5150 writes its first double to filter+50.
These are the same offsets used by the already compared 7d7060 recovery reset.
The decoded values are gyro bias variance 1e-7 and acceleration bias variance
1e-4. They differ from the synthetic HTTP profile's .01 and .1.

inspect_vdr_model now exposes these as recovery_constructor_variance after the
existing library hash check. verify_vdr_recovery_defaults_native executes the
actual ARM64 constructor prefix 7d5080..7d5168 and verifies both memory values;
it passes against the pinned APK. It deliberately stops before child constructors.
Runtime profile defaults have not yet changed: later parameter overrides still
need inspection, followed by pipeline checks with these native values. This
finding does not resolve vehicle mounting or sensor availability.

### Explicit native-constructor recovery profile

Runtime profiles can now select recovery_variance="native-constructor". This
loads the verified values from the hash-checked APK; explicit numerical profiles
remain supported. The name deliberately describes constructor defaults, without
claiming that an arbitrary official App session has no later overrides.
Both APK HTTP pipeline verifiers now select this mode instead of synthetic .01/.1
variances. The native/browser Flask tests and cross-process Node-to-Flask test
pass with these values, including the 12-second GPS gap and recovery assertions.
The APK verifier additionally checks the loaded StateConfiguration values.
This does not enable an unconfigured production server or supply a vehicle
installation matrix. Later native overrides and observation flags remain open.

### Observation binding runtime check

Revisited the previously identified 7d6df4 type-2 refresh and traced binding:
root 77ad30 takes the selected object's +28 pointer, then 77ad44 tail-calls
7b45b4; 7b45cc calls 7d6dd8 on manager+4f8. This stores the linked pointer
at filter+4d8. A linked type field (+8)==2 latches filter+4e1 to true.
7d6df4 copies the linked +288 byte to filter+4e2 only for type 2.
Neither operation clears existing flags when the linked type changes away
from 2. Constructor 7d51cc/7d51d0 initially clears both flags.

verify_vdr_recovery_defaults_native now executes the actual bind and refresh
functions across types 1 -> 2 -> 2 -> 2 -> 1 and toggling +288. All five flag
pairs match (0,0), (1,1), (1,0), (1,1), (1,1). This extends the earlier static
finding with native execution, including the sticky flag behavior.
The root-selected object's producer and state remain to be connected; a fixed
profile flag pair is only an explicit experimental input, not full runtime
equivalence. No flags were silently enabled in the production adapter.

### Observation source ownership and filter-side port

Root construction 77a8cc -> 76dadc constructs the default object at root+a80;
76dadc sets wrapper kind1 and constructs its +30 linked object through 7b7668,
which also writes kind1. Root77aa70 binds that default via77accc.
External76da60 creates a type2 wrapper through7c0f5c at external+38 and a
type1 fallback at+438. 76dc70 switches the root to+38 once; 76de64 switches
it to+438. 76dc98 forwards its boolean argument to7c0c48, writing linked+288.
Callers6aaa34 and6ab230 activate type2 then6b3f34 supplies true. Their upstream
activation criteria and the type2 observation producer still need porting.

vdr_observation_binding ports the verified filter-side bind/refresh semantics.
WindowObservation now reads these live flags from its binding, while preserving
explicit experiment flags for unbound sessions. The native verifier compares
Python against ARM64 across five bindings plus three state changes without
rebinding. All pass, and all41 VDR unit tests pass. Production does not invent
an external type2 source: that upstream integration remains incomplete.

### Type-2 producer input contract, static evidence

inspect_vdr_observation_sources.py now reproduces hash-checked disassembly of
the selection, activation and producer ranges. Its report was generated against
the pinned APK. The type2 producer 7c0c50 consumes the same prepared-window
structure: timestamp+260, GPS+338, direction+288, motion+27c, detail+280 and
latest vector floats+250/+254/+258. GPS observation is conditional on valid(),
byte+350 clear, position sigma+398 <=20, and not (+351 && +352). It always
constructs a heading observation with linked-source+288 as its flag. Motion
branches construct additional observations; the nonmotion path accumulates
preintegration and emits after elapsed >=1900. Those observation classes and
their effects still require comparison; these are not browser data substitutes.

Type2 activation at6aaa34 is reached conditionally:6aa870 checks6b4408,
then6b4234 result; a second path6ad1e4 checks6b4408 then694304 result. Both
reach6aaa34 only on true. The meaning and upstream inputs of those predicates
are not established yet, so no activation rule was invented from GPS loss.

### Activation predicate identified as fingerprint parsing

6b4408 passes external+1a0 to6b49b4, which atomically reads a 32-bit state and
returns state==2. Both activation paths then use694304 (6b4234 tail-calls it).
694304 rejects a zero +f0 collection size or an empty +158 string through
340380. It parses resource collections through693a58 and builds a result before
returning true; a cached same-identifier branch can also return true.
At6946ec/6946f8 it uses string95edf and86445. Their exact decoded text is
"%s 指纹解析完成，floor_num_ = %d, tunnel_num_ = %d, %s" and "parseFinger".
This identifies an additional fingerprint-resource branch, not merely a GPS-loss
predicate. The hashed observation-source inspector now prints these strings and
the gate/parser admission/result ranges for reproducibility.

Ordinary constructor-bound type1 remains distinct from this externally
activated type2 branch. Existing ordinary HTTP success does not prove the
fingerprint resources, parser, activation state machine or type2 correction
pipeline are implemented. Resource provenance/format is the next trace target;
do not substitute TMC GPS-loss heuristics for parseFinger success.

### Fingerprint container loader and correction to admission field

695874 loads the encoded buffer via695a88 (96f164/96fed4 descriptor decoder),
then checks decoded version==0x1b59 (7001). It populates three maps at+e0,
+f8 and+110 from 32-byte decoded entries. The first and third maps use integer
keys; the middle map uses a pair packed into64bits. Payloads are copied using
their leading signed32 length. It stores the decoded identifier at+158.
Direct branch scanning locates a loader caller at69647c.

Native labels identify this container as MgcGridFinger:99fb6 is
"MgcGridFinger::fromBuffer error",99fa1 is"algVersion not equal", and8fc76
is"指纹信息：%d个平面,%d个甬道,%d个凸包". The pinned inspector prints them.
Correction:694334's +f0 is the size field of the map beginning at+e0, not a
resource pointer as initially described. The documented admission condition
above has been corrected. No buffer format was guessed or deployed from this
partial trace. Descriptor schema, resource acquisition and payload decoding
remain unfinished; this is distinct from already working ordinary IMU filtering.

### Download response admission and decoder descriptor

6963b8..696444 compares a response-derived identifier with stored request+170
and discards a mismatch. Native84299 says"指纹回包与当前请求不一致，丢弃: resp=%s, req=%s".
696448 obtains a buffer through resource-provider+38; successful return and
nonzero +d0 then call695874. Failure logs874e4"指纹下载失败: %s"; successful
decode sets state2 via69a628 and logs9bf52"指纹解析成功". These identify a
download-response path, but the provider implementation/endpoint is unresolved.

695a88 obtains descriptor a130c8 via69a8bc, constructs a bounded input stream
through96f164, then invokes96fed4. The inspector now preserves its first160
descriptor bytes and exact admission instructions. A wire schema has not yet
been asserted: field types, offsets and nested descriptors need native decode
comparison before a Python reader can be treated as equivalent.

### Native fingerprint wire probe

verify_tunnel_fingerprint_wire_native.py now executes695a88 with actual pinned
ARM64 code and ELF relative relocations. The synthetic protobuf wire payload
08d9361201611a016222002a0163320164 succeeds. It verifies version7001 at output+0,
strings for tags2/3/5/6 at output+8/+16/+88/+96 respectively, and an empty
nested tag4 structure occupying64bytes at+24. Tag3 is the identifier consumed
by695a08. Descriptora130c8 uses32-byte entries; tag4's relocation at a13140
points to nested descriptora13028. Allocation/memcpy/free are environment
shims; existing-allocation realloc explicitly errors rather than faking growth.

This establishes the outer wire contract through real decoder execution, not
just descriptor interpretation. Nonempty nested records, malformed inputs,
downloaded payloads and geometry interpretation remain unverified. The harness
does not call a live resource endpoint or change production configuration.

### Nonempty fingerprint container port

The native wire verifier now sends two records in each nested tag2/3/4 group.
Actual decoder output confirms counts/pointers at outer+40/+48, +56/+64 and
+72/+80. Each record is32bytes: signed32 fields1/2 at+0/+4, string3 pointer+8,
bytes4 pointer+16 (length-prefixed native allocation), signed32 field5 at+24,
and tunnel-only field6 at+28. Repeated-array realloc now preserves previous
allocation contents with tracked sizes. Six records pass native comparison.

tunnel_fingerprint_container.py implements this outer container and repeated
records; the native verifier compares its decoded records against ARM64 output.
Geometry bytes remain opaque, nested tag1 metadata is retained as raw messages,
and numeric field semantics beyond wire layout are not invented. Python imposes
a16MiB input cap and rejects truncated/unsupported wire data. Malformed-input,
duplicate-message and real-download equivalence are not yet established; this
reader is not yet connected to production resource retrieval/navigation.

### Packed tunnel geometry reader

tunnel_fingerprint_geometry.py now reads694814's payload: uint32 record count,
count doubles, then each53-byte header (four doubles, uint16 sample count,
one attribute byte, two retained bytes, four float baselines) followed by28-byte
samples (<Hdd5h). Samples expose their raw integers plus original /100 scalar
and /50 three-vector baseline reconstruction, rounded to float32 as native.
The second signed scalar is divided by100. Field physical meanings are not
guessed; coordinate projection and polygon construction are still absent.

The native wire verifier executes actual69496c..694b50 header instructions and
694b5c..694c9c sample instructions against a synthetic nonzero/signed fixture.
Header coordinates/count/attribute/baselines, sample coordinates/id, reconstructed
vector/scalar and signed packed field agree with Python. This is a scoped
block comparison, not full694814 equivalence or downloaded-resource validation.

### Tunnel projection and native convex hull

The geometry reader now provides project(records, explicit frame), reusing the
previously compared local_coordinates primitive. Actual694cec..694d04 output
matches the projected sample within1e-7. Frame axes, origins and scales remain
explicit inputs; no browser datum assumption is introduced.

tunnel_polygon_matching.convex_hull ports691690, including <=3 point passthrough,
axis1/axis0 sorting, duplicate handling and integer-cross-product turn tests.
The native wire verifier executes complete691690 for55 empty/small/duplicate/
collinear/random cases, all matching ordered Python hull vertices. project now
builds the hull from projected sample points for downstream matching. Actual
resource acquisition and local-frame initialization are still not connected;
this is not production navigation or full694814 parity.

### Fingerprint frame initializer located (2026-09-29)

Static pinned-library evidence now identifies `6aa8f4 -> 6ada54` as the
external manager's `+100` frame initialization path. `6b4074` converts two
signed packed int32 coordinates by dividing by 10,000,000; `6aa930` swaps
the two lanes before passing the origin triple (third component from a
float32 at input+8). `6ada54` writes origin radians at frame+8/+10 and
altitude at +18, then curvature-dependent scales at +20/+28. Constants:
degrees-to-radians=0.017453292519943295, eccentricity coefficient=
-0.006694380004260925, meridian numerator=6335439.327202763,
equatorial radius=6378137.0. These differ from ordinary VDR's constant
metres-per-degree local frame: do not reuse that class for fingerprint data.
`6aa940` marks the frame initialized only after the call returns.

Reproducible instruction ranges are added to
`inspect_vdr_observation_sources.py`. Remaining verification: resolve the
math PLT targets and compare the complete initializer against native code;
trace the origin input provider and coordinate datum rather than infer them
from the curvature formula. This is static evidence, not a completed runtime
connection or a real-car test.

The complete `6ada54` initializer is now ported as
`tunnel_local_coordinates.initialize_frame`. ELF PLT/relocation resolution
confirms `9f2fc0 -> sin`, `9f31b0 -> pow`, `9f2e20 -> sincos`.
The native verifier executes the entire ARM64 initializer (libm calls hooked
to host libm), checking 104 origins/altitudes including both hemispheres and
near-polar inputs. Origin radians, preserved altitude and both curvature
scales agree within 2e-15 relative / 1e-8 absolute tolerance. The distinct
initializer/projector radian rounding constants are deliberately retained.
Existing wire/header/sample/projection and 55 convex-hull cases still pass.
Origin provider/datum and real resource delivery remain unresolved; this
verification does not claim that fingerprint matching is active in TMC.

Packed origin wrapper +6aa8f4 is now executed end-to-end in the same native
verifier: 104 cases confirm signed int32 / 1e7 conversion, lane swap,
float32 altitude widening, TLS/return path and initialized byte=1. Python
`initialize_packed_frame` reproduces this 12-byte input contract.
Static callers: +6aa878/+6aac8c invoke +6b4814 (current x20 directly);
+6ad1ec/+6ad6ec invoke +6b46b0 (current x20+0x40). All four initialize
before fingerprint parse, after resource state==2. This pins the record
layout boundary but not the ultimate record provider or datum. Do not wire
browser WGS84 directly on the assumption these inputs share that datum.

### Origin record dispatch traced (2026-09-29)

The frame origin is supplied by incoming records, not decoded fingerprint
geometry. Pinned jump table +a8b11 resolves dispatcher +6a9f8c kind 0 to
+6aa1a0 and kind 2 to +6aa29c; both pass record+54 into +6aa7d8 when the
external manager state (+950) equals 2. That handler retains the input in
x20, and +6b4814 forwards it to the verified packed frame adapter.
A separate dispatcher +6af870 routes kind 8 to +6ad06c, whose origin input
is record+40 via +6b46b0. Handler calls still require resource-ready state
before initialization/parse. Numeric record kinds are established; their
semantic names and producer datum are not yet established. These ranges
and decoded jump-table targets are included in the hash-checked inspector.
This narrows the next trace to record constructors/producers of kinds 0/2/8,
not fingerprint geometry decoding.

### Outer record receiver boundary (2026-09-29)

Origin path A now traces to +7dc4d0 (virtual entry relocation +a19230;
this-adjusting thunk +7dccf8). It forwards the unchanged record x1 through
+7dc590 -> +76dbf4 -> +6a9f8c. Manager base adjustment is +a680 and external
module pointer is wrapper+28. Its admission checks manager+ae80 and a
record timestamp at +18 against manager+ae88, with a process-static latch
at +a52550. Do not mistake this wrapper for the final sensor producer.

Path B traces to +76a530 (function prologue immediately preceding this
range), forwarding x1 via +76a5e0 -> +76d2f8 -> +76dc40 -> +6af870.
Before forwarding, manager+c878 must be set; kind8 has additional +d0
subtype checks: 0x12 is rejected, 0x0d depends on a global enable flag.
These wrappers do not transform coordinate fields. Their virtual callers
and original record constructors still need tracing to determine datum.
Pinned inspector now includes all five forwarding/admission ranges.

Receiver functions are virtual callback entries: legacy +7dc4d0 is stored
at relocation +a19230 and has this-adjusting thunk +7dccf8; extended entry
starts at +76a524 (not +76a530, which is inside its prologue), stored at
+a180f8 with direct thunk call +76a684. The pinned inspector now supports
`--callers` for direct B/BL and relative function-pointer relocations, making
these upstream searches reproducible without the ignored scratch script.
Verified with `--callers 0x7dc4d0 0x76a524` in separate runs. A nearby kind8
constructor at +7df418 is not established as this input record: its layout
is smaller than the fields used by the receiver. Numeric type equality is
not enough to connect separate record hierarchies.

### Concrete virtual callback caller resolved (2026-09-29)

Legacy factory +7dc3f0 allocates 0xaf50 bytes, runs +7dc1f0 and returns
object+20. Constructor writes main table +a19208 at object+0 and secondary
interface table +a192a0 at object+20. Host constructor +75f508 calls this
factory through +761dc4, then +761da8 stores the returned interface at
host+a0. The queued-record loop +75f8fc loads that interface, loads each
record pointer unchanged from its local pointer range, and calls virtual
slot +20 at +75f918. Relocation +a192c0 resolves that exact slot to
+7dccf8, which subtracts 0x20 and branches to +7dc4d0. Thus this virtual
edge is now concretely connected, not inferred from a slot number alone.
The remaining upstream question is how the host's queued pointer range
is populated and whether coordinate transformation happens before enqueue.
The inspector includes the allocation, constructor, host and delivery ranges.

### Additional selectable route-fusion engine (2026-09-29)

User explicitly requested a separate engine for degraded GPS precision using
browser fixes only. `route-fusion` is now persisted alongside browser/amap-vdr
in navigation settings. It does not impersonate native Amap inertial output.
`amapRouteFusion.ts` accepts converted map coordinates, checks precision,
route distance, heading and temporal continuity; it begins short route
prediction while fixes continue but quality degrades. Three reliable fixes
restore observation corrections with a maximum correction rate of 5 m/s.
Prediction horizon: 30 seconds/500 metres since last reliable position;
speed older than 5 seconds pauses movement. Missing route geometry is a hard
boundary. Repeated reliable off-route observations escape the constraint and
reach existing replanning. Predicted positions cannot trigger arrival.
Engine/route/navigation lifecycle resets state and clears its interval.
Seven scenario tests plus two pre-existing inertial output gate tests pass;
Vue application type-check passes. Real-vehicle behavior is not yet verified.
Native Amap integration remains separate and incomplete.

### Long degraded-position support (2026-09-29)

Route fusion now permits prediction beyond 30 seconds/500 metres while a
qualified speed stream remains live (three accepted samples spaced <=2.5s).
Speed validity is independent of position accuracy, which permits drifting
positions in long tunnels. Checks include finite 0..60 m/s, bounded speed
change against time since previous accepted speed, heading agreement with
the predicted route tangent, strictly increasing source timestamps and a
full-sample freeze detector (>8 seconds unchanged coordinates/speed/heading
while moving). A fresh timestamp alone cannot defeat freeze detection.
A missing speed stream pauses after five seconds; unqualified streams retain
the short horizon. Zero speed holds position. Display includes estimated
seconds; these are not a calibrated error bound. Ten tests pass, including
five-minute low-precision replay, braking, stop, recovery, frozen samples,
route gaps and off-route release. Vue application type-check passes.
Remaining limits: browser speed provenance/accuracy is not independently
observable; noisy stale speed can escape heuristics. Road branch connectivity
is not in AppRoute; prediction follows the chosen route and cannot determine
an actual tunnel branch from speed alone. No real-car accuracy claim.

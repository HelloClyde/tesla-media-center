# 端侧导航语音

当前 debug 和导航统一使用从固定高德 APK 提取的默认音色、MNN 3.1.1 WASM
以及网页端文本前端和声码器。首次加载的主要资源约 6.52 MB，合成在浏览器
Worker 内执行，24 kHz PCM 经 Web Audio 播放。下面的 Matcha 体积、性能和
构建记录是此前版本的历史对照。

本地准备：`python web/scripts/amap-tts/extract_assets.py --apk
.local-data/amap-app/amap-release.apk`，再在 `web/` 执行 `npm ci` 和
`npm run build`。CI 用 `tools/amap-app/release_assets.py` 下载并校验固定 APK，
然后提取模型。MNN WASM 和模型的授权情况见
`web/public/tts/amap-1.0/NOTICE.md`。

## 旧版 Matcha 记录

车机的系统 SpeechSynthesis 无可用声音且曾报告 synthesis-failed。默认导航改为
sherpa-onnx 1.13.8 / Matcha 中文模型，在浏览器 Worker 内使用 CPU WASM SIMD 合成，
通过 Web Audio 播放，不调用系统 TTS，也不向服务端上传播报文本。

入口：debug → 声音测试 → 端侧中文；可输入文本、加载模型、播放、停止、释放内存。
显示资源加载状态、合成耗时、音频长度、RTF、短句缓存命中。浏览器系统 TTS 保留为对照选项。
导航开始及模拟导航点击会解锁音频、预加载模型；转向、重算、到达使用相同服务。
静音、停止、退出页面会停止播放并使待播结果失效。过时超过 15 秒的导航播报丢弃，
避免迟到指令。每次最多 300 字；短句内存缓存最多 24 条/8 MiB，合成串行、最新请求优先。

## 构建和缓存

本地开发先执行 `python -m pip install -r tools/tts/requirements.txt`，再执行
`python tools/tts/prepare_assets.py`，最后启动 Vite。量化构建已在 Linux/WSL 验证；
本机 Miniconda 派生的 Windows venv 曾遇 ONNX DLL 初始化/检查器崩溃，改用 WSL 构建成功。
固定 upstream
release 包 SHA256 为 `bf17d3373493ae69695c3671b1c637e41c6937f755dd2c7ac9be07ca35f03cc4`。
精简版大文件放在被 git 忽略的 `web/public/tts/matcha-1.13.8-q8-v1/`，CI 在 Docker 构建前下载并校验，
前端构建复制到 dist。Docker 在缺少模型时明确失败，不能发布只有 UI 的空壳。

发布压缩包 126,139,751 字节；浏览器实际读取 data+wasm 144,838,164 字节（约 138 MiB），
另有约 115 KiB JS。首次使用需要网络，后续优先使用 Cache Storage；禁用缓存或配额不足时
仍尝试合成，不能保证浏览器始终保留缓存。运行时内存需求高于文件体积。
Worker 及 JS 仍需由本站提供；当前不承诺完整离线应用。释放语音内存保留磁盘资源缓存。

## 高德原生能力

本地固定 APK 包含 `lib/arm64-v8a/libamaptts.so`、`libGNaviVoice.so` 和
`gaolaoshi_amap/{am_encoder,am_decoder,ddspganV2_ctrl,ddspganV2_f0}.mnn`。
这证明存在原生语音实现，不证明能在浏览器执行；JNI/ARM64 原生库不能直接作为 WASM 使用。
首次静态检查未执行原生库；后续执行检查见下文。这句原记录写于移植之前。

### 固定 APK 进一步检查（2026-09-30）

检查版本 17.00.0.2005（SHA-256 `022c844511dce2958fd37c8d0941feb72587a434701debc9b2fda3e69ec07152`）
的 ZIP 目录及配置文件。除上述四个 MNN 模型外，还有 `libOSL_MNN.so`、
`libnui.so`、`assets/tts/languagedata_embedded.bin`、
`assets/tts/voices/voicefont.bin` 和 `assets/amaptts/front_asset/` 下的拼音、
分词等数据。前一次统计漏掉了 `libnui.so`，而 `libamaptts.so` 的 ELF 依赖表明确引用它。
重新汇总 21 个候选相关文件（含 `libGNaviVoice.so` 和配置文件）为
23,501,416 字节原始大小、12,508,411 字节 APK 内压缩大小（11.93 MiB）。
这仍**不是**经过实际播报验证的完整 TTS 下载量、内存占用或运行体积；
`libamaptts.so` 还有其他共享库和 Android 系统库依赖。

`assets/tts/parameter.cfg` 写有 `mode_type:0`（注释为 local）、PCM、16 kHz 和
`font_name:linzhilingyuyin`；这份 NUI 配置不能代表 App 的默认导航音色。
进一步反编译 App DEX 后，`kb7.c()` 对普通中文配置返回默认语音 ID 123，
`VoiceHelper.f()` 将其映射到 `gaolaoshi`。`VoiceHelper.b()` 对 ID 123
明确从 `assets/voicesqure/default_voice_ip/gaolaoshi_amap/` 复制六个模型与配置文件
到 App 私有目录；这些文件确实存在于 APK。因此**默认语音模型内置在 APK 中**。
六个文件共 4,210,592 字节原始大小、3,495,977 字节 APK 压缩大小；逐一计算
MD5，均与 App 在 `bd0.a()` 中用于修复/校验默认音色的六个预期值一致。
`gaolaoshi.json` 另列约 95.5 MB 的下载包元数据，但不是上述内置默认模型的
必要证据，不能把它当作首次播报必需下载量。

体积方面，这组候选原生文件小于当前网页端 49,409,456 字节（47.12 MiB）的
data + WASM。然而两者运行平台和打包方式不同，无法把 APK 压缩大小当作可替换的
浏览器资源大小。当前没有在同一文本、同一设备上生成的高德/Matcha 对照音频，
因此不能判定高德音质更好；也没有可用于网页的高德 WASM 发行物和再分发授权。
当时不替换浏览器端引擎。若要重新评估，需先取得合法可部署的网页端实现，再做
同句试听、首次加载、合成延迟、内存与车机兼容性测试。

### 原生执行检查（2026-09-30）

按固定 APK 提取 `libamaptts.so`、`libnui.so`、`libOSL_MNN.so` 等到忽略目录，
用 `readelf` 检查 ARM64 ELF：`libamaptts.so` 通过 JNI 入口加载，依赖
`libnui.so`、`libOSL_MNN.so`、Android `libc.so`/`liblog.so` 等；
`libnui.so` 导出 `nui_tts_initialize`、`nui_tts_play` 等函数，其符号表还有
约 500 个未定义的动态导入，覆盖 TTS 以外的能力。`parameter.cfg` 的本地模式
与 `libnui.so` 内的 `voicefont.bin`/`languagedata_embedded.bin` 路径相符。
为直接执行而未启动安卓模拟器：在 ARM64 用户态容器中提供 Bionic 与 APK
原生依赖，从本地 APK 提取资源，编写仅存在于忽略目录的最小调用程序。
库内日志标出版本 `V2.5.13-000-20260825`。`nui_tts_initialize` 和
`nui_tts_play` 均返回 0，但详细日志显示 `set voice error`（140903），
随后合成器初始化失败（140900）；等待 15 秒也没有音频回调或 PCM/WAV。
进程退出时还出现 Bionic 互斥量清理错误。返回 0 只说明异步调用被接受，
**不代表合成成功**。配置的 `font_name` 为 `linzhilingyuyin`，库打印
`remove voice linzhilingyuyin`。这说明本轮错误地把 NUI 旧路径作为默认导航
语音路径进行测试；其失败**不表示 APK 缺少默认语音包**。App 的默认路径使用
`gaolaoshi_amap` MNN 模型，并经 `VoiceIpEngine` 与原生音频服务初始化。
进一步定位到 `libamapbadge.so` 中 `VoiceIpEngine.nativeCreateModule`，在 ARM64
用户态环境里成功加载 `libamapbadge.so`/`libamaptts.so` 并调用该工厂取得非空指针。
在忽略目录构造最小 JNI 调用环境后，`VoiceIpEngine.nativeInit` 读到了默认语音配置，
`VoiceIpEngine.nativeGetVoiceIpServicePtr` 和 `AudioManagerAdapter.nativeGetAudioServicePtr`
均返回非空指针。连接两个服务并调用 `AudioManagerAdapter.nativePlay` 后，函数返回任务号 1，
但五秒后 `nativeIsPlaying` 返回 0；`VoiceIpEngine.nativeGetVoiceIPData({"id":123})`
仍返回 `{}`，没有 `JNIPlayer.playPCMData` 回调，也没有 PCM 文件。原生音频初始化中还须为
高德进程注入的配置服务提供最小替身，这些返回值无法证明完整的默认语音初始化成功。
四个默认 MNN 模型可由 MNN 解释器读取；声学编码器需要 `txt_tokens`、`tone`、
`prosody`、`ph2char` 等输入。这些检查还没有驱动 App 的文本前端、VoiceIP 服务和
音频回调组成完整合成链，不能将成功加载模型当作成功播报。
本轮尚未从这条正确路径得到 WAV，不能对音质或合成延迟作实测结论。

进一步连接原生服务和音频回调后，默认音色的合成任务进入 `playPCMStart`，
并尝试读取四个内置 MNN 模型和 `assets/amaptts/front_asset/` 的数据；
但没有调用 `playPCMData`，以 `113|offline` 结束，PCM 长度为 0。
文件访问记录还显示它尝试读取 `front_model/prosody_model_fp16.mnn`、
`front_model/g2p_encoder_fp16.mnn` 和 `dict_char_pgc.json`，而这三个文件在
固定 APK 的完整 ZIP 目录中不存在。前两个路径位于 TTS 公共资源工作目录；
DEX 中的 `l30.i()` 优先返回 `CloudResourceService.fetch("amap_tts_common_res")`
的下载目录，否则回退到 APK 内 `assets/amaptts/front_asset/` 的拷贝目录。
该回退资源不含 `front_model`。词典则位于音色目录，由 `getVoice()` 提供的
`model_path` 决定；默认音色的 APK 内置精简目录不含它。音色元数据另列完整
音色包下载地址及约 95.5 MB 大小，但该地址在本次检查返回 HTTP 404。
APK 的 `cloudres_master` 仅列出 `h5_template`，未提供
`amap_tts_common_res` 的直接下载 URL。未取得这些下载资源，不能将其接入
合成测试。`getTTSParams(5)` 还传入 `amap_tts_config_res` 的下载目录；
本地最小调用未提供该配置资源。因此也尚不能仅凭文件访问失败断定 `113`
的唯一原因。默认音色的四个声学/声码器模型内置，
不等于完成中文文本到 PCM 的全部资源也内置。
这里的文件访问只是“尝试读取”的证据，不能证明两个 `front_model`
或词典是默认离线播报的必需文件。`l30.i()` 明确有 APK 内置
`front_asset` 回退，原生初始化日志也曾返回 `offline_result:1`；
最小 JNI 替身合成失败不能推断真实 Android App 在首次离线启动时无法播报。

继续扫描 APK 内原生库时，在 `libamapbadge.so` 找到一条更早的 ID 123
音色记录：版本 `1706755513983`，
[下载地址](https://mapdownload.autonavi.com/voiceip/voiceip/publish/amap/V2.1.0/123/20240201104626/123_1706755513983.zip)，
文件为 29,940,925 字节，下载 MD5 `13c6dfb5460867a1db3a29851932888a`
与元数据一致。该 ZIP 有 216 项，主要是旧音色数据、录制音频和界面素材；
没有上述前端模型或词典。它的模型类型与本次默认 MNN 版本不同，
不能混用或据其音频判断当前模型的 TTS 音质。
最小 JNI 测试程序原先把 `generateTask()` 返回为 null；修正为非空任务对象后
正常播放队列仍返回 `113|offline`。后来确认这是测试夹具的任务状态问题，
不能据此判定模型合成失败。
将配置资源工作目录设为非空后，原生库进一步尝试读取
`amap_tts_config_20241104/drc.json`；APK 同样没有它。DEX 中云资源清单来自
AOCS 的 `cloud_resouce` 模块，具体接口为
`https://m5.amap.com/ws/shield/frogserver/aocs/updatable/1`；
直接提交未经 App 签名的请求只返回 `code:3, Params error`，未取得清单。
音色最新元数据接口 `/ws/user/theme/voice/resource/info` 也需要 App 请求参数；
直接请求同样返回 `code:3`。这些失败不提供资源下载地址。

MNN [官方 Web 构建说明](https://github.com/alibaba/MNN/wiki/engine#web)
提供将推理引擎编译为 WebAssembly 的方法，网页端原则上可以直接
运行这些 `.mnn` 网络，不需要把高德的 Android 原生库装进网页。
但 MNN 只执行模型计算：还需确定文本规范化、分词、拼音/音素、声调、韵律和
说话人向量如何形成模型输入，以及 `ddspganV2` 输出如何还原为 PCM。
缺失的前端模型及词典、合成控制逻辑、实际浏览器 WASM 体积和性能均未验证。
原生库在本轮用于观察 App 行为和生成同源试听样本的参考路径。
这一阶段只生成了高德默认音色 WAV；浏览器移植结果见文末。

### 原生库反汇编进展（2026-09-30）

用 Ghidra 反编译 APK 内的 ARM64 `libamaptts.so` 后，已追到实际调用顺序：
`AudioGenerator::synthesizeImpl`（`0x228858`）先调用文本切分 `0x228f20`，
再调用前端 `0x2d147c` 生成音素及韵律输入，随后以 `0x2cbd8c` 执行
`am_encoder`、时长展开及 `am_decoder`，最后由 `runVocoder`（`0x229018`）
逐段生成 PCM。这里的地址是 Ghidra 映像地址，用于继续定位实现。

默认音色 `config.json` 指定 `ttsModelType: 1`、`ttsLinkType: 2`，
声码器因此走 `0x2f6c84` 分支。该分支依次调用 `ddspganV2_f0.mnn` 和
`ddspganV2_ctrl.mnn`：前者产生 `f0` 和 `f0_frames`，中间代码对基频积分并
每 240 个采样点提取相位形成 `phase_frames`，后者接收
`spec / f0_frames / phase_frames` 并输出四组谐波及噪声频谱参数。
`0x2f5d88` 将幅度和相位组合成复数频谱，执行逆变换与重叠合成，
最后进行幅度归一化并写入 16 位 PCM。相邻合成段还有 2880 采样点的交叠处理。
这些步骤需要独立移植到 WebAssembly 或 JavaScript，MNN Web 只能承担网络推理。

词典/前端资源路径也已从初始化函数 `0x2d0a8c` 确认：它会尝试加载
`dict_char_pgc.json`、Jieba 数据、拼音和英语数据，
另有可选的韵律及 G2P 模型。现有 APK 提取物缺少 `dict_char_pgc.json`；
不过原生初始化仍报告 `offline_result: 1`，因此仅凭文件缺失不能判定它就是
合成失败原因。当前无完整 Android 环境的 JNI 测试返回 `113|offline`、PCM 为 0。
在文本前端、声学模型和声码器调用后设置一次性断点，均未命中；
所以 `113` 发生在实际合成链之前的任务调度/接口适配阶段，不能用它推断
模型或词典无法工作。随后在生成器完成异步初始化后直接调用合成入口，
并仅在这个测试夹具里跳过已结束任务的取消检查，三个阶段与声码器均返回成功。
在 `0x229408` 的 PCM 输出调用点及交叠缓冲的尾调用点截取 16 位采样，
按实际 24 kHz 写成 WAV。最初只截普通调用点会漏掉每段 2880 个采样；
完整捕获后重新生成以下试听文件。

同句试听文件在忽略目录 `.local-data/amap-app/tts-native/amap-default-compare.wav`，
文本为“前方二百米右转，进入长安街。导航语音测试。”，
103,920 个采样、4.33 秒、单声道、24 kHz，峰值 0.990、RMS 0.212，
无削波采样。另有“前方右转，进入人民路”的 2.37 秒样本
`.local-data/amap-app/tts-native/amap-default-short.wav`。
用户已试听并确认该默认音色优于现有端侧语音，决定采用此音色替换。
这证明默认 MNN 音色能在 APK 的原生合成链里离线发声；样本生成借用了 ARM64
原生库来校验输入输出，网页端仍需独立复现文本前端及声码器 DSP。
当前提取的默认音色六个文件合计 4,210,592 字节，APK 内置八个
`front_asset` 文件合计 1,228,014 字节。这约 5.19 MiB 只是模型与基础前端数据，
尚未计入网页 MNN WASM、DSP、分词/拼音代码及可能的额外资源；
实际浏览器包体必须在移植完成后测量，不能直接与当前 47.12 MiB 比大小。

在声学模型入口截获了同一句被拆成的三组真实前端输入（数组长度包含边界符）：

| 段 | `txt_tokens` | `tone` | `prosody` | `ph2char` |
|---|---|---|---|---|
| 1 | 174 61 30 25 7 24 13 4 52 28 46 94 70 174 | 3 5 5 4 4 7 5 5 6 6 7 6 6 3 | 3 3 3 3 3 3 3 3 3 3 3 7 7 7 | 100001 1 1 2 2 3 4 4 5 5 6 7 7 100001 |
| 2 | 174 49 39 62 66 15 7 6 49 37 174 | 3 7 7 7 7 5 5 4 4 4 3 | 3 3 3 3 3 3 3 3 7 7 7 | 100001 1 1 2 2 3 3 4 5 5 100001 |
| 3 | 174 16 10 27 7 84 39 14 17 64 162 174 | 3 6 6 5 5 6 4 7 7 7 7 3 | 3 3 3 3 3 3 3 3 3 7 7 7 | 100001 1 1 2 2 3 4 5 5 6 6 100001 |

这些是声学模型包装器收到的前端数组；`x_char_phlevel_self`、`z_p`、
说话人向量在包装器内部由数组及音色词典构造。独立 MNN 3.6.1
Python 运行库可加载声学编码、解码与控制模型并列出张量形状，
但加载 `ddspganV2_f0.mnn` 时进程异常退出；原生 APK 运行库能加载并完成合成。
这需要进一步定位该模型的兼容性及包装器的数据变换，不能将四个模型文件
直接交给通用 Web MNN 推理器就宣称可用。

后续逆向已复原声学时长展开、位置编码、相位生成、频谱窗函数及主要声码器
DSP，并完成四个模型的 WebAssembly 推理验证；具体数值结果见下文。

### APK 可确认的合成链

| 阶段 | APK/反编译可确认的接口 | 尚未取得的细节 |
|---|---|---|
| 资源准备 | `VoiceHelper.b()` 复制默认音色的四个 MNN、`am_dict.json`、`config.json`；`l30.a()` 复制 `front_asset`；`l30.i()` 优先采用云公共资源、失败回退内置数据。 | 云资源中的可选模型、词典及配置的实际内容。 |
| 文本前端 | `libamaptts.so` 引用 `cppjieba`、`tn_map.json`、`pinyin.bin`、`english.bin`、`tone_fix.txt`、韵律与 G2P 模型路径；有 `enable_prosody`、`enable_g2p` 字符串。 | 文本规范化规则、词到音素的编码表、可选模型的启用条件。 |
| 音色与声学编码 | `am_dict.json` 有各 96 维的 `spk_emb`、`spk_vae_emb` 及速度/音量参数。`am_encoder.mnn` 输入 `txt_tokens`、`tone`、`prosody`、`ph2char`、说话人向量等，输出 `rounded_dur`、`x_lat`、`x_ling`。 | 额外输入 `x_char_phlevel_self`、`z_p` 的构造和时长扩展算法。 |
| 声学解码 | `am_decoder.mnn` 输入 `x_durembed`、`x_env`、`x_lat`、`x_ling`、`x_spk`，输出 `mel_output`。 | 从编码器输出构造所有解码器输入的运算。 |
| 声码器 | 内置 `ddspganV2_f0.mnn`、`ddspganV2_ctrl.mnn`。MNN 转换器读出前者输入 `spec`，输出 `f0`、`f0_frames`；后者输入 `spec`、`f0_frames`、`phase_frames`，输出 `h_mag`、`h_phase`、`n_mag`、`n_phase`。原生库含 `AudioGenerator::runVocoder` 及 FFTW 符号。 | `phase_frames` 的生成、相位/噪声重建及 PCM 生成公式。 |
| 播放 | `JNIPlayer.playPCMData` 回调传递 `byte[]`；`z55.playPCMData()` 将字节写入 Android `AudioTrack`。测试夹具在更早的 `0x229408` 截取了 24 kHz PCM。 | 车机实际播放与音质对照。 |

这是静态接口和部分原生调用记录能确认的边界；不能由模型名或张量名推断
整个算法已经复现。网页端可用 MNN WASM 替代模型推理部分，但前后处理仍须
实现并用实际音频校验。

浏览器端可对应为 Worker 中的文本前端、四个 MNN WASM 推理会话、
WASM/JavaScript 的时长扩展与频谱重建，最后通过 Web Audio 播放 PCM。
模型、字典和 WASM 可由本站首次加载后缓存；合成过程本身无需服务端。
这只是实现架构，不等于现有 APK 原生库能直接编译为 WASM：
该库只有 ARM64 机器码，没有 C++ 源码；关键前后处理需要独立实现。
尚未验证四个模型在 MNN Web 后端的算子兼容性、车机浏览器延迟与内存。

## 验证与限制

禁用浏览器 speechSynthesis 的 Edge 实测：标准测试句输出 101084 个 22050 Hz 单声道
采样，4.58 秒音频；一次本机合成耗时 1351 ms，RTF 0.29，RMS 0.088。
重复短句缓存命中，离开声音测试 Tab 后停止。该结果不能代替车机实际播放和性能测试。
在禁止 data/wasm 网络请求后，释放 Worker 并重新加载仍成功，验证资源 Cache Storage 命中。
模拟路线调用真实 TTS 生成 60368 个采样，耗时约 822 ms，退出导航停止播放。
取消合成/加载期间停止、重复短句缓存、加载错误后重试的 3 项测试及类型检查、构建通过。
WASM SIMD 不支持、内存不足、加载或合成超时均显示错误，不伪装成系统播报成功。

**模型授权限制**：上游 model card 标明 DataBaker 数据集仅非商业使用；当前声音未获商业授权确认。
见 `web/public/tts/NOTICE.md`。运行库 Apache-2.0 不等于模型也取得相同授权。

## 8 位权重版（2026-09-28）

最初为原版/精简版对照实验；现已按用户要求仅保留精简版，导航与 debug 固定使用同一模型。

| 资源 | 原版字节 | 精简版字节 |
|---|---:|---:|
| 声学模型 | 75,624,611 | 20,352,050 |
| 声码器 | 53,884,024 | 13,727,877 |
| 完整 data 包 | 131,106,945 | 35,678,237 |
| data + 共享 WASM | 144,838,164 | 49,409,456 |

不计少量 JS，总下载由 138.13 MiB 降到 47.12 MiB，减少 65.9%。不是分片下载，
也不是换了另一个发音人。`quantize_assets.py` 对较大的二维及以上浮点权重按首维通道
进行对称 INT8 存储，插入 DequantizeLinear 恢复 FP32 权重。保留偏置、小常量及原运算图；
ONNX 检查器通过。该方案着重减少网络包体，不保证降低内存或提高速度。
采用 [ONNX Q/DQ 表示](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)，
未宣称端到端 INT8 算子执行，也没有将权重误差等同于语音质量评分。

独立浏览器上下文、现有 WASM 引擎的三句真实生成对照（ms）：

| 文本 | 原版 | 精简版 |
|---|---:|---:|
| 前方二百米右转，进入长安街。导航语音测试。 | 1337 | 1415 |
| 前方一公里靠左行驶，进入中山北路。 | 990 | 1033 |
| 已为您重新规划路线，请在安全地点掉头。 | 1078 | 1121 |

此轮精简版慢约 4–6%。三句时长分别约 4.56、3.62、4.10 秒；无空音频、NaN 或削波，
RMS 约 0.088–0.096，峰值 < 0.72。上述检查不证明主观音质无损，需在车机对照试听。
试听 WAV 与 JSON 指标位于 `.local-data/tts/{original,int8}-{0,1,2}.wav`、
`.local-data/tts/{original,int8}-metrics.json`，未加入 Git。
正式精简资源经 Linux 构建，debug 页真实生成、短句缓存、资源缓存及退出停止验证通过。

精简版目录完整包含 data、loader JS、WASM 和 API JS。
CI 自动安装固定量化依赖、校验上游包并生成精简版；原版只在构建中间目录保存，
不会进入网页或 Docker 部署包，不提交大型二进制模型。
量化不改变原模型来源和授权限制。

## 高德默认音色 Web 移植进度（2026-09-30）

从 APK 录制的 24 kHz 基准样本已被用户试听认可。通过原生库夹具抓取第一段
前端及模型张量，验证了独立网页实现的每个数值阶段：

| 阶段 | 对原生张量或 PCM 的比较 |
|---|---|
| MNN 3.1.1 编译到 WASM | 四个模型都能推理；控制模型四组输出 RMSE 约 3.6e-6 到 2.9e-5 |
| 音素时长展开 | `ceil(rounded_dur * speed_alpha)` 产生相同的 173 帧；编码器特征展开 RMSE < 7e-7 |
| 96 维时长位置编码 | 每音素位置 `1/duration` 至 1，48 个正弦与 48 个余弦，指数分母 47；对原生 RMSE 1.3e-8 |
| 频谱重建 | 1200 点 FFT、240 采样跳步、周期 Hann 窗；单独 ISTFT 前 10,560 采样 SNR 79.93 dB |
| WASM 控制模型 + JavaScript DSP | 同一随机噪声输入下前 10,560 采样对原生 PCM SNR 78.21 dB |

模型桥接代码在 `web/scripts/amap-tts/mnn_bridge.cpp`，固定 MNN 3.1.1 源码
（Git commit `e552986eceb10905a6e015b8cfe847fb0d82a46b`）的构建脚本为
`web/scripts/amap-tts/build-mnn-web.sh`。音频 DSP、相位、声学展开以及四模型
封装位于 `web/src/functions/amap*.ts`。`AmapTtsCore` 以**已解析的音素
数组**为输入；使用录制的三段音素，能独立输出 101,040 个采样、4.21 秒的
整句音频，文件保存在忽略目录
`.local-data/amap-app/tts-native/wasm-core-complete.wav`。原生样本是 103,920
个采样、4.33 秒。这一轮使用整段 mel 推理并直接连接三个句段；原生库按含
2880 采样交叠的子段推理，故整段音频未做逐采样一致性声明。

随后使用跳过声学推理的 ARM64 夹具批量探测 405 个拼音音节，得到
`web/src/functions/amapPhonemeMap.json`。网页前端用固定版本的 `pinyin-pro`
处理常见多音字，再按 APK 规则生成音素、声调、韵律及字索引；数字先转中文。
已经与 APK 对比了整句“前方 200 米右转，进入长安街。导航语音测试。”，
以及 500 米、人民路、中山北路、重新规划、地点掉头等导航文本的全部四组
前端张量。`amapTextFrontend` 对这些句子逐项一致。

`web/public/tts/amap-1.0/worker.js` 已替换网页播报入口。
`web/scripts/amap-tts/extract_assets.py` 从固定 SHA256 的 APK 提取四个 MNN
和 `am_dict.json`；`build-core.mjs` 打包文本前端和 DSP。网页构建和类型检查通过。
在 Edge 的真实 Worker 中合成“前方 200 米右转，进入长安街。”得到 68,640
个 24 kHz 采样；修正音量后，复测合成耗时约 0.78 秒、RMS 0.211、
峰值 0.990。这是本机 Edge 的一次缓存已命中的运行，不代表车机性能。
新增 8 项单元测试和现有播放控制 5 项测试通过。

当前合成与 APK 相同音色、模型及主要 DSP，但声码器使用整段 mel 推理，
没有完全复现 APK 的 2880 采样交叠；与原生录音的时长/波形不逐样本一致。
还需要在实际车机浏览器检验延迟、内存和音质。对少见拼音、英文路名和
APK 专有的文本规范化规则，目前可能提示无法解析；Worker 不会假装播报成功。
项目负责人已于 2026-09-30 确认默认音色模型可以随本应用公开发行；
发行说明记录在 `web/public/tts/amap-1.0/NOTICE.md`。

# 端侧导航语音

当前仅保留约 47 MiB 的精简版，debug 和导航不再提供原版切换。下文原版数据仅供历史对照。
构建源文件保存在 `.local-data/tts/source`，部署仅包含 `web/public/tts/matcha-1.13.8-q8-v1/`。
旧版浏览器选择不再读取；启动引擎时清理 TMC 语音缓存中的原版资源。

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
此次未移植、执行或再分发高德语音库、模型。

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

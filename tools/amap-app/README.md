# 当前接入：App 5.1

`route_v51.py` 是当前在线导航解码器。旧版 inspect_* 仍仅用于研究，不接导航。实际接入与限制见 [集成说明](../../docs/amap-tmc-integration.md)。

# 高德 App 离线响应研究工具

针对官方 Android App 17.00.0.2005 内保留的旧驾车回调 `h60.parser` 和 `RouteCarResultData.parseTaxiCost` 编写，已有两份固定坐标的真实响应通过外层检查；路线主体尚未完整解码，不能用于证明新版导航接口已经打通。

```powershell
python tools/amap-app/inspect_envelope.py .local-data/amap-app/response.bin
python -m unittest discover -s tools/amap-app -p 'test_*.py' -v
```

输入为保存的原始响应 body，不含 HTTP 头。工具只输出包头、长度、摘要与可识别的打车费用整数，不联网，不输出路线原始字节。费用单位尚未核实。

格式依据：两字节小端 body 标记 200，八字节小端扩展偏移，随后为 payload。偏移相对 payload 起点；标记 100 的扩展为八字节文本字节数和 UTF-16LE 逗号分隔整数。App 将**整个 payload** 交给原生解析器，工具不会把偏移之前的内容宣称为已解码的路线。

工具比 App 的反编译逻辑严格：检查十字节完整包头、拒绝偏移/长度溢出、非法 UTF-16 和整数。未知扩展保留 unknown 状态；缺失扩展标为 absent-unverified，不代表 App 接受此响应。测试全部使用明确标记 FAKE 的合成路线内容。

APK 和反编译产物保存在忽略的 `.local-data/amap-app/`，不随工具发布。具体证据与限制见 `docs/amap-app-analysis.md`。

## 实验性前缀与节点表

`inspect_route_prefix.py` 和 `inspect_route_nodes.py` 只覆盖两份样本观察到的候选结构，不是完整协议解析器。坐标比例、坐标系、长度单位、路线引用头部及耗时均未充分验证。不要将这些结果接入导航。

```powershell
python tools/amap-app/inspect_route_prefix.py .local-data/amap-app/signed-baseline.bin
python tools/amap-app/inspect_route_nodes.py .local-data/amap-app/signed-baseline.bin --reference-run 452:10
python tools/amap-app/inspect_route_nodes.py .local-data/amap-app/signed-east-control.bin --reference-run 1027:13 --reference-run 1139:16
```

引用表位置和条数是人工研究输入。工具只校验指定范围和节点索引，不证明这些范围就是完整路线记录。两份对照显示不能按摘要条目数量直接切分节点表。

新增 `inspect_route_records.py`，可按三份样本共同观察到的头部、标签和尾部规则自动定位引用记录，不需要 `--reference-run`：

```powershell
python tools/amap-app/inspect_route_records.py .local-data/amap-app/signed-far-east-control.bin
```

这仍是严格限制于观察格式的实验解析器；不认识的结构会报错，不能代表完整协议兼容。输出含中文标签、候选节点引用及剩余未解析字节数。长度单位、耗时、坐标系和完整道路折线均未验证。

`python tools/amap-app/inspect_route_blocks.py .local-data/amap-app/signed-baseline.bin` 可继续校验详情块边界，并尝试有限的相对坐标解码。未知布局标为 unsupported，不输出部分解码的块。注意 `framing_consumed_all=true` 只表示分块边界覆盖主体，**不表示块内容全部解码**；请同时检查 `uninterpreted_geometry_block_count` 和 `complete_polyline`。此工具不提供可用导航路线。

# OAJX 外层检查

HTTP 基线（会实际发出两个 HTTPS 请求）：`python tools/amap-app/http_baseline.py`；补齐旧构造器默认值的对照：加 `--defaults`。没有签名/会话，不代表 App 完整请求。原始结果只写入 `.local-data/amap-app/http-baseline-20260927*`，重复运行覆盖同名文件。

单文件正文解码：`python tools/amap-app/extract_spx_file.py APK INDEX_JSON EXACT_RESOURCE OUTPUT_FILE`。资源名必须与索引完全一致；输出路径由调用者显式指定。支持本次验证的 SPX/003 内容及跨子包共享引用，不执行提取的代码。第三方原始正文请保存在忽略目录 `.local-data/amap-app/`。

SPX 文件名目录：`python tools/amap-app/inspect_spx.py .local-data/amap-app/amap-release.apk .local-data/amap-app/spx-file-index.json`

该命令离线解码当前样本的文件名表并校验边界，不解码文件正文。所有工具测试：`python -m unittest discover -s tools/amap-app`。

`python tools/amap-app/inspect_oajx.py .local-data/amap-app/amap-release.apk`

读取本地 APK（或直接传 OAJX 文件），检查当前样本的 ion/002 索引与 spx/003 子包边界，输出 JSON。不会解码名称或脚本，也不会发送网络请求。该布局仅在 17.00.0.2005 样本验证。

测试：`python -m unittest discover -s tools/amap-app -p test_inspect_oajx.py`

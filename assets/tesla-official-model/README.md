# Tesla App 车辆模型

TMC 按车辆 `vehicle_config.car_type` 及 VIN 的车型、年款选择车模。车辆状态页和高德 3D 导航共用同一套选择规则。已从本地 Tesla Android 4.61.0-4607 XAPK 恢复并导出以下自包含 GLB，WebP 贴图和 Meshopt 几何压缩后放在 `web/public/models/`：

| 车型 | 本地资源文件 |
| --- | --- |
| Model 3 2017–2023 / 2024+ Highland | `tesla-model-3-2017-2023.glb` / `tesla-model-3-2024-plus.glb` |
| Model Y 2020–2024 / 2025+ | `tesla-model-y-2020-2024.glb` / `tesla-model-y-2025-plus.glb` |
| Model Y 2025+ Standard | `tesla-model-y-2025-standard.glb`（需 `car_type=e41Bayberry`） |
| Model Y L | `tesla-model-y-long.glb`（需 `car_type=e80Bayberry`） |
| Model S 2012–2020 / 2021+ Palladium | `tesla-model-s-2012-2020.glb` / `tesla-model-s-2021-plus.glb` |
| Model X 2015–2020 / 2021+ Palladium | `tesla-model-x-2015-2020.glb` / `tesla-model-x-2021-plus.glb` |
| Cybertruck | `tesla-cybertruck.glb` |
| Semi | `tesla-semi.glb` |

这些 `tesla-*.glb` 随仓库和 CI 镜像提供。VIN 年款只能近似识别改款交界车辆，因此优先使用 Tesla API 返回的 `car_type`；无法识别时由用户手动选择。导出素材和中间文件留在 `.local-data/tesla-app/`，不进入仓库。

原始 XAPK 与 `assets_pack.apk` 曾通过 Android `apksigner` 验证，证书 SHA-256 为 `f27a58479622c8d7bfcd87cb30e9800915761191f6ef7b268e30476e9d7a0e71`。导出使用 [tesla-model-extractor](https://github.com/koenhendriks/tesla-model-extractor) 的 `unreal` 子命令；先转换 WebP 贴图，**再**进行 Meshopt 压缩，后者会重新量化几何并压缩动画。原 Model Y 的 13 段动画在压缩后仍保留，其余车型也已检查 GLB 结构与动画数量。

这些模型、贴图和动画来自 Tesla App，并作为应用资源随仓库分发。

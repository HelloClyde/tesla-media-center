# Tesla Media Center（TMC）

面向车机横屏浏览器的多媒体与导航应用。前端使用 Vue 3，后端使用 Flask；播放页尽量使用浏览器端软解码，以适配车机浏览器的媒体能力。应用从首页启动器或左侧栏进入。

## 应用

| 应用 | 当前能力 |
| --- | --- |
| 高德导航（实验） | 地点搜索、路线规划、2D/3D 地图、实时与模拟导航、路线拥堵显示、转向和车道提示、导航语音。浏览器实时定位需要 HTTPS 和定位权限。 |
| 特斯拉 | 车辆状态与 3D 场景、轨迹、行程、原始数据；使用 Tesla Owner API token，并将历史记录保存到 SQLite。 |
| QQ 音乐 | QQ/微信扫码登录、搜索、推荐、歌单、播放队列、歌词和音质选择；可播放内容由账号权益及上游接口决定。 |
| 哔哩哔哩 | 首页、热门、排行榜、搜索、分 P/番剧播放、弹幕与续播。视频由浏览器软解；默认通过服务端转接原始分段。 |
| 腾讯视频 | 推荐、搜索、选集、链接或 VID 打开；目前主要支持公开、未加密的 MP4 内容，会员/DRM 内容不保证可播。 |
| 抖音（实验） | 公开短视频浏览、搜索、分享链接、扫码登录、上滑/下滑切换、下一条预加载和播完自动切换选项。登录、搜索与播放可能受到上游验证或 CDN 限制。 |
| 玩球直播 | 按频道浏览直播间并播放直播流，使用浏览器端 FFmpeg 软解码。可用性取决于上游直播源。 |
| 本地播放器 | 浏览服务器上的本地视频目录，播放 MP4/FLV 等媒体。 |
| GBA / GAM4980 | 浏览、上传并运行游戏，使用触控/按键操作；游戏和存档位于数据目录。 |
| 设置与调试 | 配置地图 Key、本地媒体目录及部分播放设置，检查设备能力。 |

QQ 音乐、地图和游戏的细节分别见 [QQ 音乐说明](docs/qqmusic.md)、[高德导航说明](docs/amap-tmc-integration.md) 和 [GAM4980 说明](docs/gam4980-player.md)。

## Docker 部署

当前 CI 构建 **linux/amd64** 镜像，主分支发布 `latest`、`master` 和 `sha-<commit>` 标签。示例：

```bash
mkdir -p /opt/tmc/data
docker run -d --name tmc --restart unless-stopped \
  -p 8080:8080 \
  -e TMC_PASSWORD='请改成自己的登录密码' \
  -v /opt/tmc/data:/data \
  ghcr.io/helloclyde/tesla-media-center:latest
```

打开 `http://<服务器地址>:8080` 登录。`TMC_PASSWORD` **只在首次生成配置文件时生效**；已有 `/data/config.json` 时不会覆盖旧密码。不设置时会生成随机密码，并写入首次启动日志。公开访问时应通过 HTTPS 提供服务；车机浏览器的 GPS 定位尤其依赖安全上下文。

`/data` 保存配置、账号凭据、游戏与存档、Tesla 历史记录、车辆皮肤和地图缓存，应持续挂载并备份。旧版本升级先阅读[持久化与数据迁移](docs/persistence.md)。本地视频可以放在 `/data/video` 并在设置中将 `video_path` 指向该目录，或自行挂载其他媒体目录。

本地开发环境已有从 Tesla App 提取并压缩的 Model 3/Y/S/X、Cybertruck 和 Semi 多款车模。车辆状态页按 Tesla 返回的 `car_type` 或 VIN 车型、年款选择模型，高德 3D 导航使用同一规则。本机运行或从当前目录构建 Docker 镜像会带上这些资源；它们被 Git 忽略，因此从公开仓库检出的 CI 构建不会包含，公开镜像会回退到仓库自带的展示模型。各车型文件名、匹配范围和来源见[模型资源说明](assets/tesla-official-model/README.md)。

车辆状态的「车辆外观」支持给当前官方车模上传对应 UV 排布的正方形 PNG/JPEG/WebP 皮肤；20–24 款 Model Y 也可试用仓库附带的示例图。贴图按车型上传至服务器的持久化数据目录 `tesla/skins/`，车辆状态和高德 3D 导航共用。之前存在浏览器 IndexedDB 中的皮肤会在服务器没有对应车型皮肤时自动迁移。切换车型不会误用其他车的贴图，清除皮肤后恢复车漆颜色设置。公开构建缺少官方模型时，此项不可用。

## 本地运行

建议使用 Python 3.11 和 Node.js 20。先准备后端依赖和前端产物：

```bash
git clone https://github.com/HelloClyde/tesla-media-center.git
cd tesla-media-center
python -m pip install -r requirement.txt -r tools/amap-app/requirements.txt
python tools/amap-app/release_assets.py
python web/scripts/amap-tts/extract_assets.py
cd web
npm ci
npm run build
cd ..
python flask_app.py
```

服务地址为 `http://127.0.0.1:8080`。高德运行资源和离线导航语音资源由上述脚本校验、提取；首次下载需要外网连接。开发时可另开终端在 `web/` 运行 `npm run dev`，访问 `http://localhost:3000`，Vite 默认将 `/api` 转发到本地 8080 端口。也可用 `TMC_API_PROXY` 指定后端地址。

本地默认数据目录是仓库下的 `data/`；通过 `TMC_DATA_DIR` 可改到其他路径。不要将 `data/config.json`、账号凭据、游戏 ROM 或本地提取的第三方资源提交到仓库。

## 配置

首次运行会创建 `data/config.json`，Docker 中为 `/data/config.json`。常用配置可在“设置与调试”页面修改：

| 配置项 | 用途 |
| --- | --- |
| `password` | TMC 网页登录密码；初次部署可由 `TMC_PASSWORD` 初始化。 |
| `video_path` | 服务器上的本地视频目录。 |
| `amap_key`、`amap_security_js_code` | 高德 JS/Web 地点搜索所需的 Key 和安全密钥；导航底图与路线规划不以此作为唯一数据源。 |
| `bilibili_cache_size_mb` | 旧版 B 站合流缓存的容量上限；新版原始分段转接不保存媒体文件。 |
| `tesla_api_base_url`、`tesla_auth_base_url`、`tesla_token_path` | Tesla API 地址；一般无需手动修改。 |

地图的地点搜索需要自行配置相应高德凭据；路线、实时路况、位置与语音等功能还依赖上游服务、车机定位与本地资源。请勿把 Key、token、密码、域名或服务器私有配置写入 README 或提交到 Git。

## 构建与发布

本地构建镜像前，先运行上面的高德资源提取脚本，再执行：

```bash
docker build -f docker_build/Dockerfile -t tmc:local .
```

Dockerfile 将地图资源、TTS、模型、贴图和应用代码分层，以复用较大的资源层缓存。GitHub Actions 在推送 `master`、`v*` 标签或手动触发时构建 AMD64 镜像并发布到 GHCR；配置阿里云 ACR 的四个仓库 Secret 后也会同步发布。构建流程见 [.github/workflows/docker-image.yml](.github/workflows/docker-image.yml)。

## 使用边界

本项目依赖第三方平台接口、账号权限和浏览器能力，接口变动或官方验证可能导致部分内容不可用。浏览器端软解码也会受设备性能和网络条件影响。Tesla 接入以 Owner API token 为主，并非 Fleet Telemetry 全量实现。

请仅在不会影响驾驶安全的情况下操作或观看内容；驾驶时遵守当地交通法规。

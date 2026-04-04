# Tesla Media Center

面向车机浏览器的开源多媒体中心，提供本地视频播放、B 站在线播放、Tesla 状态与轨迹查看、GBA 模拟器游玩，以及高德地图路线规划等能力。

## 目录

- [项目概览](#项目概览)
- [截图](#截图)
- [功能清单](#功能清单)
- [快速开始](#快速开始)
- [Docker 部署](#docker-部署)
- [配置说明](#配置说明)
- [开发环境](#开发环境)
- [GitHub Actions 镜像构建](#github-actions-镜像构建)
- [已知限制](#已知限制)
- [免责声明](#免责声明)

## 项目概览

当前版本已经支持：

1. B 站首页、热门、排行榜、搜索
2. B 站视频在线播放、分 P / 番剧 EP 切换、弹幕加载
3. 热门和搜索结果滚动到底自动加载更多
4. 播放结束按 EP 列表自动续播下一集
5. B 站缓存目录管理、容量限制、自动回收、一键清理
6. Tesla Owner API 接入、车辆状态、轨迹、行程和设置分 Tab 展示
7. 本地 h264 / h265 的 mp4 / flv 点播播放
8. GBA 游戏库浏览与模拟器游玩
9. 高德地图目的地搜索与路线规划
10. 跟随系统的白天 / 夜间两套主题
11. GitHub Actions 自动构建并推送 Docker 镜像到 GHCR

## 截图

### 首页 3D 车模

![home](shot/img_001.png)

主页可通过 `config.json` 中的 `home_page_iframe` 配置自定义内容，推荐使用 Sketchfab 的可交互 3D 模型：
https://sketchfab.com/search?features=animated&type=models

### B 站播放

![bl](shot/img_005.png)
![bl](shot/img_006.png)

### 本地视频播放

![video](shot/img_002.png)

### GBA 模拟器

![gba](shot/gba.png)

### 高德地图

![map](shot/img_003.png)
![map](shot/img_004.png)

## 功能清单

### B 站在线播放

使用服务端转码，前端使用 ffmpeg wasm player 播放。

已支持：

1. 首页、热门、排行榜、搜索
2. 热门和搜索结果自动翻页加载
3. 分 P / EP 列表切换与当前播放项高亮
4. 播放结束自动续播下一集
5. 弹幕分段加载和去重
6. seek 跳转与切换 EP
7. 服务端缓存大小限制和一键清理

### 本地视频播放

已支持：

1. h264 / h265 的 mp4 / flv 播放
2. Web 端文件列表浏览
3. 基于 wasm 的软解播放

如果视频是流式点播，建议将 `moov box` 前置。可用如下 ffmpeg 命令转码：

```bash
ffmpeg -i test.mp4 -codec:v hevc -codec:a aac -b:v 512k -b:a 128k -s 1100x624 -r 25 -movflags faststart output.mp4
```

原始播放器项目：
https://github.com/sonysuqin/WasmVideoPlayer

### GBA 模拟器

GBA 模拟器内核基于 `gbajs2`，界面按车机横屏场景重新设计。

已支持：

1. 本地 GBA ROM 游戏库浏览
2. 点击 ROM 后切换到专注游玩界面
3. 触控方向键、A / B、L / R、Start / Select
4. 键盘映射控制
5. 暂停、继续、重启、返回游戏库

默认 ROM 目录为 `./roms/gba`，支持通过 `config.json` 中的 `gba_path` 覆盖。

原始模拟器项目：
https://github.com/andychase/gbajs2.git

### Tesla 状态与轨迹

当前实现兼容 `TeslaMate` 个人用户常见的 `Owner API` token 使用方式。

已支持：

1. `Access Token / Refresh Token` 保存与回填
2. 授权状态检查
3. 车辆状态、轨迹、行程、设置 4 个 Tab
4. 车辆列表读取与最近状态展示
5. 轨迹地图展示
6. 手动同步与自动轮询同步

说明：

1. 当前仍以个人自用的 `Owner API` 链路为主，不是 Tesla 官方 Fleet Telemetry 全栈接入
2. 中国区 token 需要按对应区域生成
3. 如果能读到账户但读不到车辆，通常是 token 类型或权限范围不匹配

### 高德地图

高德地图 API Key 需要自行申请：
https://console.amap.com/dev/key/app

如需在 Tesla 浏览器中获取 GPS，需要使用 HTTPS 访问站点。

已支持：

1. 目的地搜索和路线规划
2. 实时路况
3. GPS 信号低提醒
4. 地图移动、拖拽、视角调整、车头朝上

## 快速开始

### 方式一：直接运行

1. 克隆仓库

```bash
git clone https://github.com/HelloClyde/tesla-media-center.git
cd tesla-media-center
```

2. 安装 Python 依赖

```bash
pip install -r requirement.txt
```

3. 安装前端依赖并构建

```bash
cd web
npm install
npm run build
cd ..
```

4. 创建 `config.json`

```json
{
  "home_page_iframe": "https://sketchfab.com/models/de2fc0824eb140ccb63c5b215797b996/embed?autostart=1&internal=1&tracking=0&ui_infos=0&ui_snapshots=1&ui_stop=0&ui_watermark=0",
  "video_path": "./video",
  "gba_path": "./roms/gba",
  "amap_key": "xxx",
  "password": "abc",
  "bilibili_cache_dir": "/tmp/tesla-media-center/bilibili-cache",
  "bilibili_cache_size_mb": 2048,
  "tesla_api_base_url": "https://owner-api.vn.cloud.tesla.cn",
  "tesla_auth_base_url": "https://auth.tesla.com",
  "tesla_token_path": "/oauth2/v3"
}
```

5. 启动服务

```bash
python flask_app.py
```

默认访问地址：

```text
http://127.0.0.1:8080
```

### 方式二：使用 Docker

```bash
docker run -it \
  -p 8080:8080 \
  -v ./config.json:/root/tesla-media-center/config.json \
  -v ./video:/root/tesla-media-center/video \
  -v ./roms:/root/tesla-media-center/roms \
  -v ./db:/root/tesla-media-center/db \
  -v ./tmc-cache:/tmp/tesla-media-center \
  ghcr.io/helloclyde/tesla-media-center:latest
```

建议将 `./db` 和 `./tmc-cache` 都单独挂载出来：

1. `./roms` 用于挂载 GBA ROM 库，默认从 `./roms/gba` 读取游戏
2. `./db` 用于持久化 Tesla SQLite 数据库，避免容器重建后轨迹和行程记录丢失
3. `./tmc-cache` 用于 B 站转码缓存，避免容器层磁盘被缓存文件占满

## Docker 部署

镜像地址：

```text
ghcr.io/helloclyde/tesla-media-center:latest
ghcr.io/helloclyde/tesla-media-center:master
ghcr.io/helloclyde/tesla-media-center:sha-<commit>
registry.cn-hangzhou.aliyuncs.com/<namespace>/tesla-media-center:latest
registry.cn-hangzhou.aliyuncs.com/<namespace>/tesla-media-center:master
registry.cn-hangzhou.aliyuncs.com/<namespace>/tesla-media-center:sha-<commit>
```

拉取示例：

```bash
docker pull ghcr.io/helloclyde/tesla-media-center:latest
docker pull registry.cn-hangzhou.aliyuncs.com/<namespace>/tesla-media-center:latest
```

## 配置说明

`config.json` 示例：

```json
{
  "home_page_iframe": "https://sketchfab.com/models/de2fc0824eb140ccb63c5b215797b996/embed?autostart=1&internal=1&tracking=0&ui_infos=0&ui_snapshots=1&ui_stop=0&ui_watermark=0",
  "video_path": "./video",
  "gba_path": "./roms/gba",
  "amap_key": "xxx",
  "password": "abc",
  "bilibili_cache_dir": "/tmp/tesla-media-center/bilibili-cache",
  "bilibili_cache_size_mb": 2048,
  "tesla_api_base_url": "https://owner-api.vn.cloud.tesla.cn",
  "tesla_auth_base_url": "https://auth.tesla.com",
  "tesla_token_path": "/oauth2/v3"
}
```

字段说明：

1. `home_page_iframe`：主页展示内容，不知道填什么时可直接使用默认值
2. `video_path`：本地视频目录
3. `gba_path`：GBA ROM 目录，默认 `./roms/gba`
4. `amap_key`：高德地图 Key，没有时地图功能不可用
5. `password`：Web 登录密码
6. `bilibili_cache_dir`：B 站转码缓存目录，默认可直接使用
7. `bilibili_cache_size_mb`：B 站缓存上限，单位 MB
8. `tesla_api_base_url`：Tesla Owner API 地址，中国区默认 `https://owner-api.vn.cloud.tesla.cn`
9. `tesla_auth_base_url`：Tesla 认证地址，默认 `https://auth.tesla.com`
10. `tesla_token_path`：Tesla token 路径，默认 `/oauth2/v3`
11. `tesla_db_path`：Tesla SQLite 数据库路径，默认 `./db/tesla_history.sqlite3`

缓存说明：

1. 服务端会在生成新缓存后自动回收旧缓存
2. 前端 B 站“我的”页可以直接查看缓存占用
3. 前端 B 站“我的”页可以修改缓存上限并一键清理缓存

## 开发环境

下面以 CentOS 为例，其他系统请自行安装对应依赖。

1. 下载代码

```bash
yum install git -y
git clone https://github.com/HelloClyde/tesla-media-center.git
cd tesla-media-center
```

2. 创建 Python 环境，可选

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
sh Miniconda3-latest-Linux-x86_64.sh
conda create -n tmc python=3.10
conda activate tmc
```

3. 安装 Python 依赖

```bash
pip install -r requirement.txt
```

4. 安装 Node.js 并构建前端

```bash
yum install nodejs npm -y
npm config set registry https://registry.npmmirror.com

cd web
npm install
npm run build
cd ..
```

5. 创建配置文件并启动

```bash
python flask_app.py
```

## GitHub Actions 镜像构建

仓库已配置 GitHub Actions，会在以下场景自动构建并推送 Docker 镜像到 GitHub Container Registry：

1. push 到 `master`
2. 推送 `v*` tag
3. 手动触发 `workflow_dispatch`

同时支持在配置好阿里云 ACR 凭据后，同步推送到阿里云镜像仓库。

需要在 GitHub 仓库 Secrets 中配置：

1. `ALIYUN_REGISTRY`
2. `ALIYUN_REGISTRY_NAMESPACE`
3. `ALIYUN_REGISTRY_USERNAME`
4. `ALIYUN_REGISTRY_PASSWORD`

示例：

```text
ALIYUN_REGISTRY=registry.cn-hangzhou.aliyuncs.com
ALIYUN_REGISTRY_NAMESPACE=helloclyde
```

如果以上 4 个 secrets 未配置，workflow 仍会继续推送到 GHCR，只是不会推送到阿里云 ACR。

## 已知限制

1. 当前仍然不是完整复刻 bilibili 客户端，功能会优先覆盖核心场景
2. 服务端实时转码依然较吃 CPU，弱机器上的并发能力有限
3. 车载弱网场景下仍可能出现短时缓冲或音画不同步
4. B 站首页推荐接口当前仍是单页，不支持像热门一样持续翻页
5. 本地视频播放器目前只支持 h264 / h265 的 flv / mp4，并且更适合时长较短的视频

## 免责声明

本解决方案及相关代码和文档仅用于帮助用户搭建和管理面向乘客的多媒体服务，不应在任何会影响驾驶安全的场景中使用。

用户在驾驶或操作车辆时，应始终遵守交通法规并保持注意力集中。任何因使用或误用本解决方案而导致的直接或间接后果、损害、事故或责任，均由用户自行承担，项目开发者和分发者不承担责任。

使用本解决方案即表示你已经理解并同意：

1. 不会在任何可能干扰驾驶或车辆操作安全的场景中使用本方案
2. 已理解并接受使用本方案带来的全部风险
3. 对自身和他人的安全承担最终责任

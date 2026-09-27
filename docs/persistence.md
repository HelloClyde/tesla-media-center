# 统一持久化目录

Docker 设置 `TMC_DATA_DIR=/data`，本地默认项目根目录下 `data/`。只需挂载一次：

```bash
-v /opt/tmc/data:/data
```

| 数据 | 根目录内位置 |
| --- | --- |
| 登录密码、加密密钥、应用配置及 Tesla/B 站凭证 | `config.json` |
| QQ 音乐登录凭证及设备信息 | `qqmusic/` |
| GBA 游戏、普通存档、即时存档 | `gba/`、`gba/saves/`、`gba/states/` |
| GAM4980 游戏、存档 | `gam4980/`、`gam4980/saves/` |
| Tesla 历史数据库 | `tesla/tesla_history.sqlite3` |
| 地图磁盘缓存及缓存设置 | `amap-cache/map.sqlite3` |
| B 站视频缓存 | `bilibili-cache/` |

`TMC_PASSWORD` 仅用于首次没有配置时初始化密码；不覆盖已有配置。未指定时生成随机密码并在首次启动日志显示。配置文件和 QQ 凭证应一起备份，保留原 `secret_key`；浏览器原登录会话也仍需保留。

## 从旧容器升级

先停止旧容器，保留容器及原挂载数据备份。不要在旧服务继续写数据库时直接复制 SQLite 文件。

最方便的首次升级方式：**保留原来的挂载参数**，额外添加 `-v /opt/tmc/data:/data`，启动新版镜像。程序首次初始化会复制旧配置、QQ 凭证、游戏与存档、Tesla 数据库、地图缓存、B 站缓存；不会删除源数据，也不覆盖目标已有文件。SQLite 通过备份 API 迁移。旧配置里的自定义路径仅用于这次迁移，之后统一从新根目录读取。

只有旧数据对新容器可见，才能自动复制。原来只存在旧容器可写层里的文件，应在替换容器前 `docker cp` 导出到宿主机，再通过旧路径挂载给新容器。例如（`旧容器名` 替换为实际名称）：

```bash
mkdir -p /opt/tmc/legacy/qqmusic
docker cp 旧容器名:/root/tesla-media-center/config.json /opt/tmc/legacy/config.json
docker cp 旧容器名:/root/tesla-media-center/.qqmusic/. /opt/tmc/legacy/qqmusic/
```

首次新版启动时提供：

```bash
-v /opt/tmc/legacy/config.json:/root/tesla-media-center/config.json:ro \
-v /opt/tmc/legacy/qqmusic:/root/tesla-media-center/.qqmusic:ro \
-v /opt/tmc/data:/data
```

其余旧目录同理，保留原挂载路径：`roms/`、`db/`、`/var/cache/tmc/amap`、`/tmp/tesla-media-center`。确认新目录的数据完整后，下次重建即可去掉旧挂载，只保留 `/data`。第一次成功初始化会生成 `.migration-v1`，后续启动不会从旧文件回灌覆盖新数据；应在首次启动前备齐旧数据。

本地视频仍支持自选 `video_path`；如希望也只挂载一个目录，可将视频放入 `/data/video` 并在配置中设置该路径。侧栏固定顺序等设备偏好仍在浏览器，不属于服务器持久化数据。

## GAM4980 存档

- 需要登录 TMC，存档以游戏内容标识命名，不受文件重命名影响；同一 TMC 实例共享游戏存档。
- 自动保存、暂停、返回列表和切换应用时提交到服务器，写入使用临时文件与原子替换。
- 服务端已有存档时优先加载它；没有服务端存档时，自动上传当前浏览器的旧存档。换设备前先在原浏览器打开对应游戏完成迁移。
- 上传失败时保留浏览器备份并显示错误；下次打开会先重试。也可暂停重试或导出 `.sav` 手动备份。
- 关闭整个浏览器或断网时最后一次请求不能保证送达，请等待同步完成；不要在多台设备同时运行同一个游戏，以免较晚写入的存档覆盖另一台进度。

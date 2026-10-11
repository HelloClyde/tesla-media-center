# 车内监控与对讲

在车机的应用列表打开“监控”，选择“车机端”，点击“启用监控”并允许摄像头与麦克风。在另一台设备通过 HTTPS 打开同一个 TMC，登录后打开“监控 → 远程查看”，选择在线车辆。查看时收听车内声音，点击“开始说话”后授权麦克风即可对讲，再点击“结束说话”释放麦克风。

默认 360p，约 10 帧/秒，可在启用前选择 720p；实际尺寸受摄像头输出限制。可仅启用摄像头或麦克风。多人可同时观看，同一车辆同时只允许一个查看端对讲，避免声音混在一起。当前上限为 8 台在线设备、每台 4 个查看端。

监控由车机主动启用，不能从远程网页打开未授权的车机摄像头。切换 TMC 应用时继续运行，导航页等界面显示开启状态与停止按钮。离开远程查看页面会断开查看与对讲；退出 TMC 登录会关闭该浏览器的监控连接并释放采集设备。关闭网页、车机休眠或浏览器暂停后台网页时，无法保证持续采集。

摄像头和麦克风需要 HTTPS（localhost 调试例外）；浏览器必须实际开放 `getUserMedia`、摄像头/麦克风及 AudioWorklet。网页无法绕过车机对这些硬件的限制。不支持时会显示具体原因，不自动改成录像或虚构画面。

## 中转与运行

媒体路径为车机浏览器 → TMC Python 后端 → 查看浏览器，对讲沿相反方向回传；没有浏览器之间的直连。使用同源 `/api/monitor/stream` WebSocket，复用现有 HTTPS 端口，不需要 TURN、UDP 端口或 Android 设备。

视频为 JPEG 二进制帧，音频为 16 kHz 单声道 PCM16，每包 40 ms。浏览器音频采集、重采样和播放放在 AudioWorklet。没有查看端时不上传媒体；慢连接只保留最新视频帧和最多 4 包音频，浏览器也检查发送积压并丢弃旧帧；音频播放缓存最多约 240 ms。网络中断会自动重连，用户停止或授权失效后不再自动开启。

WebSocket 须携带 TMC 登录 Cookie 和 45 秒有效、一次性且绑定浏览器会话的连接授权。授权通过 WebSocket 子协议头传递，不写进 URL。限制消息尺寸、发送速率、设备数和观看人数；不同设备的音视频不混传。数据只在内存中用于实时转发，不保存录像、声音或截图，不写持久化数据目录。

增加 `flask-sock==0.7.0` 依赖；现有 Docker 的单进程、多线程 Flask 服务支持该连接。中转状态在内存，不支持多个独立 Python worker 分摊同一组连接；改为多进程部署前须增加共享中转服务。Docker 同时包含 `/monitor/audio-worklet.js`。

## Nginx

生产反向代理必须允许 WebSocket Upgrade。合并以下 location 到现有 HTTPS server，保留原有 TMC 登录、静态文件及其他 API 配置：

```nginx
location = /api/monitor/stream {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 90s;
    proxy_send_timeout 15s;
    proxy_buffering off;
}
```

后端每 20 秒发送 WebSocket ping，浏览器还每 10 秒发送应用心跳。Vite 本地代理已设置 `ws: true`。

验证：`python -m pytest tests/test_monitor.py -q` 覆盖真实 WebSocket 握手、视频/音频下发、对讲回传、登录与一次性授权、设备隔离、互斥对讲、断线恢复和缓冲上限。前端测试覆盖 44.1/48 kHz 重采样、静音、播放缓存及停止/重连。

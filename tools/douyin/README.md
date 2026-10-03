# 抖音访客会话诊断

安装轻量依赖后运行：

```powershell
python -m pip install -r tools/douyin/requirements.txt
python -m tools.douyin.visitor_probe --attempts 3 --check-qr
```

脚本用 Python HTTP 会话取得首次页面、执行页面内的访客校验脚本，再请求首页，检查服务端是否下发 `UIFID_TEMP` 和 `ttwid`。访客 Cookie 只留在内存，命令行仅输出是否取得身份。

`--check-qr` 还会生成二维码并轮询一次，命令行只显示状态，不输出二维码或 token。轮询所需的 `a_bogus` 由附带的 Python 实现生成。扫码登录、视频列表和播放地址均使用 HTTP 会话；登录 Cookie 仅保存在服务端内存中。

应用默认使用该 HTTP 流程，不需要 Playwright 或 Chromium。搜索接口可能要求扫码登录，官方验证状态会直接提示给用户。

`signing/abogus.py` 与 `signing/sm3.py` 改自 [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 的提交 `d8f874cd5b647b0ca087a57b15a458c3864439fa`，遵循 Apache-2.0；完整授权文本和声明见 `signing/LICENSE`、`signing/NOTICE`。本地修改仅调整了模块导入路径。

抖音的校验脚本和接口可能变化，诊断失败时不能据此判断账号或网络故障。

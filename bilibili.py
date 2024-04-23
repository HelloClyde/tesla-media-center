from bilibili_api import login, user, sync
print("请登录：")
credential = login.login_with_qrcode_term() # 在终端扫描二维码登录
# credential = login.login_with_qrcode() # 使用窗口显示二维码登录
try:
    credential.raise_for_no_bili_jct() # 判断是否成功
    credential.raise_for_no_sessdata() # 判断是否成功
except:
    print("登陆失败。。。")
    exit()
print("欢迎，", sync(user.get_self_info(credential))['name'], "!")
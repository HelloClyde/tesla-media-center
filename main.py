from aiohttp import web
from loguru import logger
import os
import json
import base64
import time
from cryptography import fernet
from aiohttp_session import setup, get_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from bilibili_api import hot, homepage, rank, search
from config import put_config_by_key, get_config_by_key, get_all_config_safe
from functools import wraps
import asyncio  
import ffvideo


routes = web.RouteTableDef()


def json_ok(data):
    return web.json_response({
        'status': 'ok',
        'data': data,
    })

def json_fail(status='fail'):
    return web.json_response({
        'status': status,
        'data': None
    })
 
def login_check(req_handler):
    @wraps(req_handler)
    async def wrapTheFunction(request):
        session = await get_session(request)
        if 'last_visit' not in session:
            logger.error('need login')
            return json_fail('need_login')
        data = await req_handler(request)
        return data
    return wrapTheFunction

@routes.post('/api/login')
async def login(request):
    data = await request.json()
    logger.info(f'post data:{data}')
    password = data['password']
    if get_config_by_key('password') == password:
        session = await get_session(request)
        session['last_visit'] = int(time.time())
        return json_ok({})
    return json_fail()


@routes.get('/api/logout')
async def logout(request):
    session = await get_session(request)
    if 'last_visit' in session:
        del session['last_visit']
    return json_ok({})


@login_check
@routes.get('/api/ws/ctl')
async def video_control_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            logger.info(f'ws receive msg:{msg.data}')
            payload = json.loads(msg.data)
            type = payload['type']
            args = payload['args']
            if type == 'init':
                ffvideo.set_video_config(args)
                await ws.send_str('init_ok')
            elif type == 'pause':
                ffvideo.set_play_state('pause')
            elif type == 'play':
                ffvideo.set_play_state('playing')
            else:
                raise Exception('not support')
        if msg.type == web.WSMsgType.ERROR:
            logger.error('ws connection closed with exception %s' % ws.exception())  
    logger.info('websocket connection closed')
    return ws

@login_check
@routes.get('/api/ws')
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    # 启动，后台线程处理
    task = asyncio.create_task(ffvideo.sync_to_ws(ws))
    logger.info(f'start sync_to_ws task')
    
    async for msg in ws:
        if msg.type == web.WSMsgType.ERROR:
            logger.error('ws connection closed with exception %s' % ws.exception())  
    logger.info('websocket connection closed')
    task.cancel()
    logger.info(f'sync_to_ws task cancel')
  
    return ws


@routes.get('/api/config')
@login_check
async def get_config(request):
    return json_ok(get_all_config_safe())

@routes.get('/api/video/list')
@login_check
async def video_list(request):
    prefix = get_config_by_key('video_path')
    path = request.query["path"]
    abs_path = f'{prefix}/{path}'
    files = os.listdir(abs_path)
    ret = []
    files.sort()
    for f in files:
        abs_f = f'{abs_path}/{f}'
        if os.path.isdir(abs_f):
            ret.append({
                'fileType': 'DIR',
                'fileName': f,
            })
        else:
            if f.endswith('.mp4'):
                ret.append({
                    'fileType': 'FILE',
                    'fileName': f,
                    'url': os.path.normpath(f'/api/video/files/{path}/{f}')
                })
        
        
    return json_ok(ret)

@routes.get('/api/video/files/{path:[^{}]+}')
@login_check
async def video_files(request):
    prefix = get_config_by_key('video_path')
    path = request.match_info['path']
    abs_path = os.path.normpath(f'{prefix}/{path}')
    logger.info(f'play path: {abs_path}')
    return web.FileResponse(path = abs_path)

@routes.get(r'/')
async def home(request):
    return web.HTTPFound("/index.html")

@routes.get(r'/{name:(?!api).+}')
async def static_web(request):
    name = request.match_info['name']
    logger.info(f'static file request:{name}')
    fpath = f'./web/dist/{name}'
    if os.path.exists(fpath):
        return web.FileResponse(path=fpath)
    else:
        # return web.HTTPFound("/index.html")
        return web.HTTPNotFound()



@routes.get('/api/bilibili/hot')
@login_check
async def bl_hot(request):
    resp = await hot.get_hot_videos()
    return json_ok(resp)

@routes.get('/api/bilibili/search')
@login_check
async def bl_search(request):
    keyword = request.query["keyword"]
    page_no = request.query["pageNo"]
    resp = await search.search(keyword, page_no)
    return json_ok(resp)

@routes.get('/api/bilibili/rank')
@login_check
async def bl_rank(request):
    type = request.query["type"]
    logger.info(f'rank type:{type}')
    resp = await rank.get_rank(rank.RankType[type])
    return json_ok(resp)

@routes.get('/api/bilibili/home')
@login_check
async def bl_home(request):
    resp = await homepage.get_videos()
    return json_ok(resp)


@login_check
@routes.get('/api/bilibili/bv/{bvid}')
async def bl_bv_video(request):
    bvid = request.match_info['bvid']
    vod = ffvideo.BiliDlVideo(bvid)
    await vod.start()
    res = web.StreamResponse(headers={'Content-Type': 'application/octet-stream'})
    await res.prepare(request)
    ffvideo.read_output_pipe_to_resp(res)
    return res

if __name__ == '__main__':
    app = web.Application()
    
    # cookie session加密
    secret_key = get_config_by_key('secret_key', default_value=fernet.Fernet.generate_key().decode('utf-8'))
    put_config_by_key('secret_key', secret_key)
    
    setup(app, EncryptedCookieStorage(base64.urlsafe_b64decode(secret_key.encode('utf-8'))))
    
    app.add_routes(routes)
    web.run_app(app)
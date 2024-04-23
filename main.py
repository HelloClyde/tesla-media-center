from aiohttp import web
from loguru import logger
import os
import json
import base64
from cryptography import fernet
from aiohttp_session import setup, get_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from bilibili_api import homepage, sync
from config import put_config_by_key, get_config_by_key, get_all_config_safe
from functools import wraps
 
def login_check(req_handler):
    @wraps(req_handler)
    async def wrapTheFunction(request):
        session = await get_session(request)
        if 'last_visit' not in session:
            logger.error('need login, redirect')
            return web.HTTPFound('/#/login')
        return req_handler(request)
    return wrapTheFunction

routes = web.RouteTableDef()

# bilibili 
@routes.get('/api/bilibili/home_videos')
@login_check
async def bilibili_home_video(request):
    resp = await homepage.get_videos()
    return web.json_response(resp)


@routes.get('/api/config')
async def get_config(request):
    return web.json_response(get_all_config_safe())

@routes.get('/api/video/list')
async def video_list(request):
    prefix = get_config_by_key('video_path')
    path = request.query["path"]
    abs_path = f'{prefix}/{path}'
    files = os.listdir(abs_path)
    ret = []
    for f in files:
        abs_f = f'{prefix}/{f}'
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
        
        
    return web.json_response(ret)

@routes.get('/api/video/files/{path}')
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



if __name__ == '__main__':
    app = web.Application()
    
    # cookie session加密
    secret_key = get_config_by_key('secret_key', default_value=fernet.Fernet.generate_key().decode('utf-8'))
    put_config_by_key('secret_key', secret_key)
    
    setup(app, EncryptedCookieStorage(base64.urlsafe_b64decode(secret_key.encode('utf-8'))))
    
    app.add_routes(routes)
    web.run_app(app)
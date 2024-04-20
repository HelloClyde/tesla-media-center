from aiohttp import web
from loguru import logger
import os
import json

with open('config.json') as f:
    config = json.loads(f.read())

routes = web.RouteTableDef()


@routes.get('/api/config')
async def get_config(request):
    return web.json_response(config)

@routes.get('/api/video/list')
async def video_list(request):
    prefix = config['video_path']
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
                    'url': f'/api/video/files/{path}/{f}'
                })
        
        
    return web.json_response(ret)

@routes.get('/api/video/files/{path}')
async def video_files(request):
    prefix = config['video_path']
    path = request.match_info['path']
    abs_path = f'{prefix}/{path}'
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
        return web.HTTPNotFound()


app = web.Application()
app.add_routes(routes)


if __name__ == '__main__':
    web.run_app(app)
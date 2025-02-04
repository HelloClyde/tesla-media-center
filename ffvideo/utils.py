from loguru import logger
import requests
from bilibili_api import HEADERS
from flask import jsonify

def download_stream( url, pipe_path, headers=HEADERS, chunk_size=10240):
    try:
        logger.info(f'url:{url}, pipe_path:{pipe_path}')
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()

        logger.info(f'start download..')
        with open(pipe_path, 'wb') as wf:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    wf.write(chunk)
        logger.info(f'download finished, url:{url}')
    except Exception as e:
        logger.exception("download fail.")
        raise e
    

def json_ok(data):
    return jsonify({
        'status': 'ok',
        'data': data,
    })

def json_fail(status='fail'):
    return jsonify({
        'status': status,
        'data': None
    })
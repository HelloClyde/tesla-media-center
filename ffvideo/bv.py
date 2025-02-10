from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file, make_response
import requests
from bilibili_api import video, Credential, HEADERS, bangumi, sync, homepage, hot, rank, search, ass
from loguru import logger
import imageio_ffmpeg
import subprocess
import time
import threading
from ffvideo import utils as futils
from ffvideo.utils import json_ok, json_fail
from config import put_config_by_key, get_config_by_key, get_all_config_safe
import os
from werkzeug.exceptions import ClientDisconnected
import re

ffplay_stop_event = threading.Event()

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

class FFMPEGJobs:
    def __init__(self, bv=None, tasks=None, stop_event=None, size_map={}):
        self.bv = bv
        self.tasks = tasks if tasks is not None else []
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.size_map = size_map
        
    def __repr__(self):
        return f"FFMPEGJobs(bv={self.bv}, tasks={self.tasks}, stop_event={self.stop_event.is_set()}, size_map={self.size_map})"

# 原始字典
ffmpeg_jobs_dict = {
    'bv': None,
    'tasks': [], 
    'stop_event': threading.Event(),
    'size_map': {},
}
ffmpeg_jobs = FFMPEGJobs(**ffmpeg_jobs_dict)

def add_bv_route(app):

    @app.route('/api/bilibili/rank', methods=['GET'])
    def bl_rank():
        type = request.args.get('type', 'All') 
        logger.info(f'rank type:{type}')
        resp = sync(rank.get_rank(rank.RankType[type]))
        return json_ok(resp)

    @app.route('/api/bilibili/hot', methods=['GET'])
    def bl_hot():
        resp = sync(hot.get_hot_videos())
        return json_ok(resp)

    @app.route('/api/bilibili/home', methods=['GET'])
    def bl_home():
        resp = sync(homepage.get_videos())
        return json_ok(resp)

    @app.route('/api/bilibili/search', methods=['GET'])
    def bl_search():
        keyword = request.args.get('keyword') 
        page_no = request.args.get('pageNo', '1') 
        resp = sync(search.search(keyword, page_no))
        return json_ok(resp)
    
    def get_video_bitrate(video_path):
        command = [FFMPEG_PATH, "-i", video_path]
        
        # 执行命令并捕获输出
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        # FFmpeg的输出会在stderr中，但这里我们合并到了stdout，所以只检查stdout
        output = result.stdout
        logger.info(f'output:{output}')
        
        # 使用正则表达式查找比特率信息
        # 匹配形如 "bitrate: 500 kb/s" 的字符串
        bitrate_pattern = re.compile(r'bitrate:\s*(\d+)\skb/s')
        match = bitrate_pattern.search(output)
        
        if match:
            bitrate = match.group(1)
            return bitrate
        else:
            return None
    
    def download_stream( url, pipe_path, headers=HEADERS, chunk_size=10240):
        global ffmpeg_jobs
        try:
            logger.info(f'url:{url}, pipe_path:{pipe_path}')
            response = requests.get(url, stream=True, headers=headers)
            response.raise_for_status()
            
            # 打印所有响应头
            headers = response.headers
            for key, value in headers.items():
                logger.info(f"header=>{key}: {value}")
            ffmpeg_jobs.size_map[url] = int(headers.get('Content-Length'))

            logger.info(f'start download..')
            with open(pipe_path, 'wb') as wf:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if ffmpeg_jobs.stop_event.is_set():
                        logger.warning(f'received stop signal, return')
                        return
                    if chunk:
                        wf.write(chunk)
            logger.info(f'download finished, url:{url}')
        except Exception as e:
            logger.exception("download fail.")
            ffmpeg_jobs.stop_event.set()
            logger.warning(f'download fail, send signal to stop all tasks')
            raise e

    def ffmpeg(input_video_pipe, input_audio_pipe, output_video_path):
        global ffmpeg_jobs
        
        DONE_FILE = f'{output_video_path}.done'
        if os.path.exists(DONE_FILE):
            os.remove(DONE_FILE)
            
        # ffmpeg_cmd = f'{FFMPEG_PATH} -re -i {input_video_pipe}  -i {input_audio_pipe} -c copy  -movflags faststart -f flv {output_video_path} -y'
        # ffmpeg_cmd = f'{FFMPEG_PATH} -re -i {input_video_pipe}  -i {input_audio_pipe} -c:v libx264 -x264-params keyint=30:scenecut=0 -c:a aac -movflags faststart -f flv {output_video_path} -y'
        ffmpeg_cmd = f'{FFMPEG_PATH} -i {input_video_pipe}  -i {input_audio_pipe} -c:v libx264 -x264-params keyint=30:scenecut=0 -c:a copy -f flv {output_video_path} -y' # http-flv重新编码，头部关键帧
        # ffmpeg_cmd = f'{FFMPEG_PATH} -i {input_video_pipe}  -i {input_audio_pipe} -c copy -f flv {output_video_path} -y' # http-flv
        
        logger.info(f'cmd:{ffmpeg_cmd}')
        process = subprocess.Popen(ffmpeg_cmd, shell=True)
        
        while True:
            if ffmpeg_jobs.stop_event.is_set():
                logger.info(f"terminate ffmpeg:{ffmpeg_cmd}")
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.info(f"terminate timeout,kill")
                    process.kill()
            
            if process.poll() is not None:  # 如果子进程已经结束
                break
            time.sleep(0.1)
        
        return_code = process.wait()
        logger.info(f'ret code:{return_code}')
        if return_code == 0:
            with open(f'{output_video_path}.done', 'w') as f:
                pass
            logger.info(f'ret code:{return_code}, write done file')
        else:
            logger.warning(f'ffmpeg error exit, code:{return_code}')
            
            
    @app.route('/api/bilibili/bv/<string:bvid>/dm/<int:seg>', methods=['GET'])
    def get_bilibili_video_dm(bvid, seg):        
        v = video.Video(bvid=bvid)
        dms = sync(v.get_danmakus(0, from_seg=seg, to_seg=seg+1))
        return json_ok({
            'dm': list(map(lambda x: x.__dict__, dms))
        })
    
    def return_bv_stream(bvid):
        global ffmpeg_jobs
        v = video.Video(bvid=bvid)
        download_url_data = sync(v.get_download_url(0))
        duration = download_url_data['timelength']
        output_video_path = f'/tmp/bv_output_{bvid}.flv'
        
        
        if ffmpeg_jobs.bv == bvid:
            pass
        else:
            # stop pre jobs
            ffmpeg_jobs.stop_event.set()
            for task in ffmpeg_jobs.tasks:
                task.join()
            
            # get bv stream
            detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
            streams = detecter.detect_best_streams(codecs=[video.VideoCodecs.AVC])
            if not detecter.check_video_and_audio_stream():
                raise Exception(f'can not get video and audio stream by bvid:{bvid}')
            
            # create pipe file
            input_video_pipe = f'/tmp/bv_video_{bvid}.m4s'
            input_audio_pipe = f'/tmp/bv_audio_{bvid}.m4s'
            if os.path.exists(input_video_pipe):
                os.remove(input_video_pipe)
            if os.path.exists(input_audio_pipe):
                os.remove(input_audio_pipe)
            os.mkfifo(input_video_pipe)
            os.mkfifo(input_audio_pipe)
            
            ffmpeg_jobs.bv = bvid
            ffmpeg_jobs.stop_event.clear()
            ffmpeg_jobs.size_map = {}
            ffmpeg_jobs.tasks = [
                threading.Thread(target=download_stream, args=(streams[0].url, input_video_pipe)),
                threading.Thread(target=download_stream, args=(streams[1].url, input_audio_pipe)),
                threading.Thread(target=ffmpeg, args=(input_video_pipe, input_audio_pipe, output_video_path)),
            ]
            for task in ffmpeg_jobs.tasks:
                task.start()
        
        MAX_WAIT = 30  # 最大等待时间（秒）
        CHECK_INTERVAL = 0.1  # 检查间隔（秒）
        
        start_time = time.time()
        while True:
            # 超时检查
            if time.time() - start_time > MAX_WAIT:
                logger.error(f"Error: Video generation timeout")
                return json_fail('Video generation timeout')
            
            # 等待文件创建
            if os.path.exists(output_video_path):
                break
            time.sleep(CHECK_INTERVAL)
        time.sleep(5)
        size = os.path.getsize(output_video_path)
        merge_size = sum(ffmpeg_jobs.size_map.values())
        data = {
            "size": size,
            'merge_size': merge_size,
            "file": output_video_path
        }
        
        # 创建JSON响应
        response = make_response(jsonify(data), 200)
        
        # 添加自定义headers
        response.headers['Content-Type'] = 'application/json'
        response.headers['BV-Content-Length'] = merge_size
        response.headers['BV-Duration'] = duration
        
        return response
    
    @app.route('/api/bilibili/bangumi_ss/<string:sid>/<int:idx>/info', methods=['GET'])
    def get_bilibili_bangumi_info(sid, idx):
        global ffmpeg_jobs
        bgm = bangumi.Bangumi(ssid=sid)
        ep_lst = sync(bgm.get_episodes())
        logger.info(f'ep list:{ep_lst}')
        bvid = sync(ep_lst[idx].get_bvid())
        return return_bv_stream(bvid)
            
    @app.route('/api/bilibili/bv/<string:bvid>/info', methods=['GET'])
    def get_bilibili_video_info(bvid):
        return return_bv_stream(bvid)

    @app.route('/api/bilibili/bv/<string:bvid>', methods=['GET'])
    def get_bilibili_video_chunk(bvid):
        output_video_path = f'/tmp/bv_output_{bvid}.flv'
        range_header = request.headers.get('range') # bytes=0-524287
        start, end = range_header.replace('bytes=', '').split('-')

        # 将 start 和 end 转换为整数
        start = int(start)
        end = int(end)
        length = end - start + 1
            
        DONE_FILE = f'{output_video_path}.done'
        CHECK_INTERVAL = 0.1  # 检查间隔（秒）
        
        final_size = -1
        # wait done or file size > end
        bitrate = get_video_bitrate(output_video_path)
        logger.info(f'bitrate:{bitrate} kb/s')
        while True:
            size = os.path.getsize(output_video_path)
            if os.path.exists(DONE_FILE):
                final_size = size
                break
            if size >= end:
                break
            time.sleep(CHECK_INTERVAL)
        
        def generate():
            with open(output_video_path, 'rb') as f:
                f.seek(start)
                chunk = f.read(length)
                yield chunk
        logger.info(f'final_size:{final_size}')
        resp = Response(stream_with_context(generate()), mimetype='video/mp4', headers={'BV-Content-Length': final_size, 'Content-Length': length})
        return resp

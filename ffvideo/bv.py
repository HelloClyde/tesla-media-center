from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file
import requests
from bilibili_api import video, Credential, HEADERS, bangumi, sync, homepage, hot, rank, search
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

ffplay_stop_event = threading.Event()

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

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

    def ffmpeg(input_video_pipe, input_audio_pipe, output_video_path):
        # ffmpeg_cmd = f'{FFMPEG_PATH} -re -i {input_video_pipe}  -i {input_audio_pipe} -c copy  -movflags faststart -f flv {output_video_path} -y'
        # ffmpeg_cmd = f'{FFMPEG_PATH} -re -i {input_video_pipe}  -i {input_audio_pipe} -c:v libx264 -x264-params keyint=30:scenecut=0 -c:a aac -movflags faststart -f flv {output_video_path} -y'
        ffmpeg_cmd = f'{FFMPEG_PATH} -i {input_video_pipe}  -i {input_audio_pipe} -c:v libx264 -x264-params keyint=30:scenecut=0 -c:a copy -f flv {output_video_path} -y' # http-flv重新编码，头部关键帧
        
        logger.info(f'cmd:{ffmpeg_cmd}')
        process = subprocess.Popen(ffmpeg_cmd, shell=True)
        return_code = process.wait()
        with open(f'{output_video_path}.done', 'w') as f:
            pass
        logger.info(f'ret code:{return_code}, write done file')
        
    def ffplay(video_path, output_pipe):
        # 等待文件创建
        while True:
            if not os.path.exists(video_path):
                time.sleep(1)
                continue
            break
        time.sleep(5)
        ffplay_stop_event.clear()
        ffmpeg_cmd = f'{FFMPEG_PATH} -re -i {video_path} -c copy -f flv {output_pipe} -y'
        logger.info(f'cmd:{ffmpeg_cmd}')
        process = subprocess.Popen(ffmpeg_cmd, shell=True)
        
        while True:
            if ffplay_stop_event.is_set():
                logger.info(f"terminate ffplay:{ffmpeg_cmd}")
                process.terminate()
                try:
                    outs, errs = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.info(f"terminate timeout,kill")
                    process.kill()
            
            if process.poll() is not None:  # 如果子进程已经结束
                return_code = process.wait()
                logger.info(f'ret code:{return_code}')
                break
            time.sleep(0.1)
        

    @app.route('/api/bilibili/bv/<string:bvid>', methods=['GET'])
    def get_bilibili_video_info(bvid):
        v = video.Video(bvid=bvid)
        download_url_data = sync(v.get_download_url(0))
        detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
        streams = detecter.detect_best_streams(codecs=[video.VideoCodecs.AVC])
        if detecter.check_video_and_audio_stream():
            for stream in streams:
                logger.info(f'url:{stream.url}')
            
            # create pipe file
            input_video_pipe = f'/tmp/bv_video_{bvid}.m4s'
            input_audio_pipe = f'/tmp/bv_audio_{bvid}.m4s'
            output_video_path = f'/tmp/bv_output_{bvid}.flv'
            output_video_pipe = f'/tmp/bv_ouput_{bvid}.flv'
            if os.path.exists(input_video_pipe):
                os.remove(input_video_pipe)
            if os.path.exists(input_audio_pipe):
                os.remove(input_audio_pipe)
            if os.path.exists(output_video_pipe):
                os.remove(output_video_pipe)
            os.mkfifo(input_video_pipe)
            os.mkfifo(input_audio_pipe)
            os.mkfifo(output_video_pipe)
            
            tasks = [
                threading.Thread(target=futils.download_stream, args=(streams[0].url, input_video_pipe)),
                threading.Thread(target=futils.download_stream, args=(streams[1].url, input_audio_pipe)),
                threading.Thread(target=ffmpeg, args=(input_video_pipe, input_audio_pipe, output_video_pipe)),
                # threading.Thread(target=ffplay, args=(output_video_path, output_video_pipe))
            ]
            for task in tasks:
                task.start()
            
            # ffmpeg_cmd = f'{FFMPEG_PATH} -i {input_video_pipe}  -i {input_audio_pipe} -c copy -movflags faststart -f flv {output_video_path} -y'
            # logger.info(f'cmd:{ffmpeg_cmd}')
            # process = subprocess.Popen(ffmpeg_cmd, shell=True)
            # return_code = process.wait()
            # logger.info(f'ret code:{return_code}')
            DONE_FILE = f'{output_video_path}.done'
            MAX_WAIT = 30  # 最大等待时间（秒）
            CHECK_INTERVAL = 0.1  # 检查间隔（秒）
            CHUNK_SIZE = 1024 * 100  # 每次读取100kb
            
            def generate():
                try:
                    with open(f'{output_video_pipe}', 'rb') as video_file:
                        data = video_file.read(10240)
                        while data:
                            yield data
                            data = video_file.read(10240)
                            # logger.info(f'req state:{request.is_terminated}')
                except Exception as e:
                    logger.error(f'disconnect e:{e}')
                finally:
                    ffplay_stop_event.set()
                    logger.info(f'ffplay finished')
                # last_position = 0
                # start_time = time.time()
                
                # while True:
                #     # 超时检查
                #     if time.time() - start_time > MAX_WAIT:
                #         yield b"Error: Video generation timeout"
                #         break
                    
                #     # 等待文件创建
                #     if not os.path.exists(output_video_path):
                #         time.sleep(CHECK_INTERVAL)
                #         continue
                    
                #     try:
                #         with open(output_video_path, 'rb') as f:
                #             f.seek(last_position)
                #             while True:
                #                 chunk = f.read(CHUNK_SIZE)
                #                 if chunk:
                #                     last_position = f.tell()
                #                     yield chunk
                #                 else:
                #                     # 检查是否处理完成
                #                     if os.path.exists(DONE_FILE):
                #                         return
                #                     # 等待新数据
                #                     time.sleep(CHECK_INTERVAL)
                #     except (FileNotFoundError, IOError):
                #         time.sleep(CHECK_INTERVAL)

            return Response(stream_with_context(generate()), mimetype='application/octet-stream')
            # self.ffmgeg_proc = await asyncio.create_subprocess_shell(cmd)
        return jsonify(bvid)

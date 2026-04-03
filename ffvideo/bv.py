from flask import Flask, request, Response, jsonify, stream_with_context, redirect, send_from_directory, abort, send_file, make_response
import requests
from bilibili_api import video, Credential, HEADERS, bangumi, sync, homepage, hot, rank, search, ass
from loguru import logger
import imageio_ffmpeg
import subprocess
import time
import threading
from ffvideo import utils as futils
from ffvideo.utils import json_ok, json_fail, login_check
from config import put_config_by_key, get_config_by_key, get_all_config_safe
import os
from werkzeug.exceptions import ClientDisconnected
import re
import shutil
from bilibili_api.exceptions import ResponseCodeException
from bilibili_api import utils as bilibili_utils

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


DEFAULT_BILIBILI_CACHE_DIR = '/tmp/tesla-media-center/bilibili-cache'
DEFAULT_BILIBILI_CACHE_SIZE_MB = 2048


def get_bilibili_cache_dir():
    cache_dir = get_config_by_key('bilibili_cache_dir', DEFAULT_BILIBILI_CACHE_DIR)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_bilibili_cache_limit_bytes():
    cache_size_mb = get_config_by_key('bilibili_cache_size_mb', DEFAULT_BILIBILI_CACHE_SIZE_MB)
    try:
        cache_size_mb = int(cache_size_mb)
    except (TypeError, ValueError):
        cache_size_mb = DEFAULT_BILIBILI_CACHE_SIZE_MB
    cache_size_mb = max(cache_size_mb, 256)
    return cache_size_mb * 1024 * 1024


def get_cache_done_path(output_video_path):
    return f'{output_video_path}.done'


def get_managed_cache_entries():
    cache_dir = get_bilibili_cache_dir()
    entries = []
    for entry in os.scandir(cache_dir):
        if not entry.is_file():
            continue
        if not entry.name.startswith('bv_output_'):
            continue
        if not (entry.name.endswith('.flv') or entry.name.endswith('.flv.done')):
            continue
        stat = entry.stat()
        entries.append({
            'path': entry.path,
            'name': entry.name,
            'size': stat.st_size,
            'mtime': stat.st_mtime,
        })
    return sorted(entries, key=lambda item: item['mtime'])


def get_bilibili_cache_stats():
    cache_dir = get_bilibili_cache_dir()
    entries = get_managed_cache_entries()
    total_size = sum(entry['size'] for entry in entries)
    disk_usage = shutil.disk_usage(cache_dir)
    return {
        'cacheDir': cache_dir,
        'maxSizeMb': get_bilibili_cache_limit_bytes() // (1024 * 1024),
        'sizeBytes': total_size,
        'sizeMb': round(total_size / 1024 / 1024, 2),
        'fileCount': len(entries),
        'diskFreeMb': round(disk_usage.free / 1024 / 1024, 2),
        'files': [
            {
                'name': entry['name'],
                'sizeBytes': entry['size'],
                'sizeMb': round(entry['size'] / 1024 / 1024, 2),
                'mtime': int(entry['mtime']),
            }
            for entry in reversed(entries)
        ],
    }


def clear_bilibili_cache(exclude_paths=None):
    exclude_paths = set(exclude_paths or [])
    deleted_size = 0
    deleted_count = 0
    for entry in get_managed_cache_entries():
        if entry['path'] in exclude_paths:
            continue
        try:
            os.remove(entry['path'])
            deleted_size += entry['size']
            deleted_count += 1
        except FileNotFoundError:
            continue
    return {
        'deletedCount': deleted_count,
        'deletedSizeBytes': deleted_size,
        'deletedSizeMb': round(deleted_size / 1024 / 1024, 2),
    }


def enforce_bilibili_cache_limit(exclude_paths=None):
    exclude_paths = set(exclude_paths or [])
    limit_bytes = get_bilibili_cache_limit_bytes()
    entries = get_managed_cache_entries()
    total_size = sum(entry['size'] for entry in entries)
    if total_size <= limit_bytes:
        return {
            'deletedCount': 0,
            'deletedSizeBytes': 0,
            'deletedSizeMb': 0,
        }

    deleted_size = 0
    deleted_count = 0
    for entry in entries:
        if total_size <= limit_bytes:
            break
        if entry['path'] in exclude_paths:
            continue
        try:
            os.remove(entry['path'])
            total_size -= entry['size']
            deleted_size += entry['size']
            deleted_count += 1
        except FileNotFoundError:
            continue

    if deleted_count > 0:
        logger.info(f'evicted bilibili cache, deleted_count:{deleted_count}, deleted_size:{deleted_size}')
    return {
        'deletedCount': deleted_count,
        'deletedSizeBytes': deleted_size,
        'deletedSizeMb': round(deleted_size / 1024 / 1024, 2),
    }


def get_output_video_path(bvid, cid, start_ms=0):
    cache_dir = get_bilibili_cache_dir()
    if start_ms > 0:
        return os.path.join(cache_dir, f'bv_output_{bvid}_{cid}_{start_ms}.flv')
    return os.path.join(cache_dir, f'bv_output_{bvid}_{cid}.flv')


def wait_for_output_file(output_video_path, timeout=30):
    start_time = time.time()
    while True:
        if os.path.exists(output_video_path):
            return True
        if time.time() - start_time > timeout:
            return False
        time.sleep(0.1)


def stop_current_jobs():
    global ffmpeg_jobs
    ffmpeg_jobs.stop_event.set()
    for task in ffmpeg_jobs.tasks:
        task.join()
    ffmpeg_jobs.tasks = []


def make_ffmpeg_headers():
    header_lines = []
    for key, value in HEADERS.items():
        header_lines.append(f'{key}: {value}')
    return '\r\n'.join(header_lines) + '\r\n'


def extract_bangumi_episode_items(payload):
    episodes = []
    seen_ids = set()

    def add_episode_list(items):
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            ep_id = item.get('id') or item.get('ep_id') or item.get('episode_id')
            if ep_id in seen_ids:
                continue
            seen_ids.add(ep_id)
            episodes.append(item)

    def walk(node):
        if isinstance(node, dict):
            add_episode_list(node.get('episodes'))
            main_section = node.get('main_section')
            if isinstance(main_section, dict):
                add_episode_list(main_section.get('episodes'))
            for section_key in ('sections', 'section'):
                sections = node.get(section_key)
                if isinstance(sections, list):
                    for section in sections:
                        if isinstance(section, dict):
                            add_episode_list(section.get('episodes'))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    walk(item)

    walk(payload)
    return episodes


def add_bv_route(app):
    @app.route('/api/bilibili/cache', methods=['GET'])
    @login_check
    def get_bilibili_cache_info():
        return json_ok(get_bilibili_cache_stats())

    @app.route('/api/bilibili/cache/settings', methods=['POST'])
    @login_check
    def set_bilibili_cache_settings():
        data = request.json or {}
        max_size_mb = data.get('maxSizeMb')
        try:
            max_size_mb = int(max_size_mb)
        except (TypeError, ValueError):
            return json_fail('invalid_cache_size'), 400
        max_size_mb = max(max_size_mb, 256)
        put_config_by_key('bilibili_cache_size_mb', max_size_mb)
        cleanup = enforce_bilibili_cache_limit()
        stats = get_bilibili_cache_stats()
        stats['cleanup'] = cleanup
        return json_ok(stats)

    @app.route('/api/bilibili/cache/clear', methods=['POST'])
    @login_check
    def clear_bilibili_cache_route():
        stop_current_jobs()
        cleanup = clear_bilibili_cache()
        ffmpeg_jobs.bv = None
        stats = get_bilibili_cache_stats()
        stats['cleanup'] = cleanup
        return json_ok(stats)

    @app.route('/api/bilibili/rank', methods=['GET'])
    @login_check
    def bl_rank():
        type = request.args.get('type', 'All') 
        logger.info(f'rank type:{type}')
        resp = sync(rank.get_rank(rank.RankType[type]))
        return json_ok(resp)

    @app.route('/api/bilibili/hot', methods=['GET'])
    @login_check
    def bl_hot():
        pn = int(request.args.get('pn', '1'))
        ps = int(request.args.get('ps', '20'))
        resp = sync(hot.get_hot_videos(pn=pn, ps=ps))
        return json_ok(resp)

    @app.route('/api/bilibili/home', methods=['GET'])
    @login_check
    def bl_home():
        resp = sync(homepage.get_videos())
        return json_ok(resp)

    @app.route('/api/bilibili/search', methods=['GET'])
    @login_check
    def bl_search():
        keyword = request.args.get('keyword') 
        page_no = request.args.get('pageNo', '1') 
        resp = sync(search.search(keyword, page_no))
        return json_ok(resp)

    
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
        
        DONE_FILE = get_cache_done_path(output_video_path)
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
            with open(DONE_FILE, 'w') as f:
                pass
            enforce_bilibili_cache_limit(exclude_paths={output_video_path, DONE_FILE})
            logger.info(f'ret code:{return_code}, write done file')
        else:
            logger.warning(f'ffmpeg error exit, code:{return_code}')

    def ffmpeg_seek_streams(video_url, audio_url, output_video_path, start_ms):
        global ffmpeg_jobs

        DONE_FILE = get_cache_done_path(output_video_path)
        if os.path.exists(DONE_FILE):
            os.remove(DONE_FILE)
        if os.path.exists(output_video_path):
            os.remove(output_video_path)

        start_sec = max(start_ms / 1000.0, 0)
        ffmpeg_cmd = [
            FFMPEG_PATH,
            '-headers', make_ffmpeg_headers(),
            '-ss', str(start_sec),
            '-i', video_url,
            '-headers', make_ffmpeg_headers(),
            '-ss', str(start_sec),
            '-i', audio_url,
            '-c:v', 'libx264',
            '-x264-params', 'keyint=30:scenecut=0',
            '-c:a', 'copy',
            '-f', 'flv',
            output_video_path,
            '-y'
        ]

        logger.info(f'cmd:{ffmpeg_cmd}')
        process = subprocess.Popen(ffmpeg_cmd)

        while True:
            if ffmpeg_jobs.stop_event.is_set():
                logger.info(f"terminate ffmpeg:{ffmpeg_cmd}")
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.info(f"terminate timeout,kill")
                    process.kill()

            if process.poll() is not None:
                break
            time.sleep(0.1)

        return_code = process.wait()
        logger.info(f'ret code:{return_code}')
        if return_code == 0:
            with open(DONE_FILE, 'w') as f:
                pass
            enforce_bilibili_cache_limit(exclude_paths={output_video_path, DONE_FILE})
            logger.info(f'ret code:{return_code}, write done file')
        else:
            logger.warning(f'ffmpeg error exit, code:{return_code}')

    def ffmpeg_single_stream(input_url, output_video_path, start_ms=0):
        global ffmpeg_jobs

        DONE_FILE = get_cache_done_path(output_video_path)
        if os.path.exists(DONE_FILE):
            os.remove(DONE_FILE)
        if os.path.exists(output_video_path):
            os.remove(output_video_path)

        ffmpeg_cmd = [
            FFMPEG_PATH,
            '-headers', make_ffmpeg_headers(),
        ]
        if start_ms > 0:
            ffmpeg_cmd.extend(['-ss', str(max(start_ms / 1000.0, 0))])
        ffmpeg_cmd.extend([
            '-i', input_url,
            '-c:v', 'libx264',
            '-x264-params', 'keyint=30:scenecut=0',
            '-c:a', 'copy',
            '-f', 'flv',
            output_video_path,
            '-y'
        ])

        logger.info(f'cmd:{ffmpeg_cmd}')
        process = subprocess.Popen(ffmpeg_cmd)

        while True:
            if ffmpeg_jobs.stop_event.is_set():
                logger.info(f"terminate ffmpeg:{ffmpeg_cmd}")
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.info("terminate timeout,kill")
                    process.kill()

            if process.poll() is not None:
                break
            time.sleep(0.1)

        return_code = process.wait()
        logger.info(f'ret code:{return_code}')
        if return_code == 0:
            with open(DONE_FILE, 'w') as f:
                pass
            enforce_bilibili_cache_limit(exclude_paths={output_video_path, DONE_FILE})
            logger.info(f'ret code:{return_code}, write done file')
        else:
            logger.warning(f'ffmpeg error exit, code:{return_code}')
            
            
    @app.route('/api/bilibili/bv/<string:bvid>/dm/<int:seg>', methods=['GET'])
    @login_check
    def get_bilibili_video_dm(bvid, seg):        
        v = video.Video(bvid=bvid)
        dms = sync(v.get_danmakus(0, from_seg=seg, to_seg=seg+1))
        return json_ok({
            'dm': list(map(lambda x: x.__dict__, dms))
        })
    
    def return_bv_stream(bvid, cid, start_ms=0):
        global ffmpeg_jobs
        v = video.Video(bvid=bvid)
        v_detail = sync(v.get_detail())
        download_url_data = sync(v.get_download_url(cid=cid))
        duration = download_url_data['timelength']
        output_video_path = get_output_video_path(bvid, cid, start_ms)
        done_file_path = get_cache_done_path(output_video_path)
        job_key = f'{bvid}_{cid}_{start_ms}'
        enforce_bilibili_cache_limit(exclude_paths={output_video_path, done_file_path})
        
        if ffmpeg_jobs.bv == job_key:
            pass
        else:
            stop_current_jobs()
            
            # get bv stream
            detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
            streams = detecter.detect_best_streams(codecs=[video.VideoCodecs.AVC])
            if not detecter.check_video_and_audio_stream():
                raise Exception(f'can not get video and audio stream by bvid:{bvid}')

            ffmpeg_jobs.bv = job_key
            ffmpeg_jobs.stop_event.clear()
            ffmpeg_jobs.size_map = {}
            if start_ms > 0:
                ffmpeg_jobs.tasks = [
                    threading.Thread(
                        target=ffmpeg_seek_streams,
                        args=(streams[0].url, streams[1].url, output_video_path, start_ms)
                    ),
                ]
            else:
                input_video_pipe = f'/tmp/bv_video_{bvid}_{cid}.m4s'
                input_audio_pipe = f'/tmp/bv_audio_{bvid}_{cid}.m4s'
                if os.path.exists(input_video_pipe):
                    os.remove(input_video_pipe)
                if os.path.exists(input_audio_pipe):
                    os.remove(input_audio_pipe)
                os.mkfifo(input_video_pipe)
                os.mkfifo(input_audio_pipe)
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
        merge_size = sum(ffmpeg_jobs.size_map.values()) if ffmpeg_jobs.size_map else size
        data = {
            "size": size,
            'merge_size': merge_size,
            "file": output_video_path,
            'detail': v_detail,
        }
        
        # 创建JSON响应
        response = make_response(jsonify(data), 200)
        
        # 添加自定义headers
        response.headers['Content-Type'] = 'application/json'
        response.headers['BV-Content-Length'] = merge_size
        response.headers['BV-Duration'] = duration
        
        return response

    def return_bangumi_stream(epid, cid, start_ms=0, as_response=True):
        global ffmpeg_jobs
        ep = bangumi.Episode(epid=int(epid))
        try:
            download_url_data = sync(ep.get_download_url())
        except ResponseCodeException as e:
            logger.warning(f'bangumi download url failed for epid={epid}, code={e.code}, msg={e.msg}')
            if e.code == -10403:
                return json_fail('region_restricted', data={'epid': epid}, message='该番剧因地区限制暂时无法播放'), 451
            if e.code == -404:
                return json_fail('not_found', data={'epid': epid}, message='该番剧分集暂时无法获取播放地址'), 404
            raise

        stream_info = download_url_data.get('video_info', download_url_data)
        duration = stream_info.get('timelength', 0)
        output_video_path = get_output_video_path(f'ep_{epid}', cid, start_ms)
        done_file_path = get_cache_done_path(output_video_path)
        job_key = f'ep_{epid}_{cid}_{start_ms}'
        enforce_bilibili_cache_limit(exclude_paths={output_video_path, done_file_path})

        if ffmpeg_jobs.bv != job_key:
            stop_current_jobs()

            detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
            streams = detecter.detect_best_streams(codecs=[video.VideoCodecs.AVC])

            ffmpeg_jobs.bv = job_key
            ffmpeg_jobs.stop_event.clear()
            ffmpeg_jobs.size_map = {}
            if detecter.check_video_and_audio_stream():
                if start_ms > 0:
                    ffmpeg_jobs.tasks = [
                        threading.Thread(
                            target=ffmpeg_seek_streams,
                            args=(streams[0].url, streams[1].url, output_video_path, start_ms),
                        ),
                    ]
                else:
                    input_video_pipe = '/tmp/input_video_pipe'
                    input_audio_pipe = '/tmp/input_audio_pipe'
                    if os.path.exists(input_video_pipe):
                        os.remove(input_video_pipe)
                    if os.path.exists(input_audio_pipe):
                        os.remove(input_audio_pipe)
                    os.mkfifo(input_video_pipe)
                    os.mkfifo(input_audio_pipe)
                    ffmpeg_jobs.tasks = [
                        threading.Thread(target=download_stream, args=(streams[0].url, input_video_pipe)),
                        threading.Thread(target=download_stream, args=(streams[1].url, input_audio_pipe)),
                        threading.Thread(target=ffmpeg, args=(input_video_pipe, input_audio_pipe, output_video_path)),
                    ]
            elif streams and getattr(streams[0], 'url', None):
                ffmpeg_jobs.tasks = [
                    threading.Thread(
                        target=ffmpeg_single_stream,
                        args=(streams[0].url, output_video_path, start_ms),
                    ),
                ]
            else:
                raise Exception(f'can not get usable bangumi stream by epid:{epid}')
            for task in ffmpeg_jobs.tasks:
                task.start()

        if not wait_for_output_file(output_video_path):
            return json_fail('Video generation timeout'), 504

        payload = {
            'size': os.path.getsize(output_video_path),
            'file': output_video_path,
            'detail': {'epid': epid, 'cid': cid},
        }
        if not as_response:
            return payload, duration

        response = make_response(jsonify(payload), 200)
        response.headers['Content-Type'] = 'application/json'
        response.headers['BV-Duration'] = duration
        return response

    @app.route('/api/bilibili/bangumi_ss/<string:sid>', methods=['GET'])
    @login_check
    def get_bilibili_bangumi_info(sid):
        bgm = bangumi.Bangumi(ssid=sid)
        episode_list_payload = sync(bgm.get_episode_list())
        episode_items = extract_bangumi_episode_items(episode_list_payload)
        logger.info(f'bangumi episode payload type:{type(episode_list_payload)}')
        logger.info(f'bangumi episode count:{len(episode_items)}')
        if not episode_items:
            logger.error(f'No bangumi episodes found for ssid={sid}, payload={episode_list_payload}')
            return json_fail('empty_episode_list'), 502

        ep_dict_lst = []
        for idx, ep_meta in enumerate(episode_items):
            ep_id = ep_meta.get('id') or ep_meta.get('ep_id') or ep_meta.get('episode_id')
            if not ep_id:
                continue
            title = ep_meta.get('share_copy') or ep_meta.get('long_title') or ep_meta.get('longtitle') or ep_meta.get('show_title') or ep_meta.get('title')
            cover = ep_meta.get('cover')
            bvid = ep_meta.get('bvid')
            cid = ep_meta.get('cid')
            aid = ep_meta.get('aid')

            if not bvid and aid:
                try:
                    bvid = bilibili_utils.aid_bvid_transformer.aid2bvid(int(aid))
                except Exception:
                    logger.warning(f'failed to transform aid to bvid for ssid={sid}, epid={ep_id}, aid={aid}')

            if not bvid or not cid:
                ep = bangumi.Episode(epid=ep_id)
                try:
                    if not bvid:
                        bvid = sync(ep.get_bvid())
                    if not cid:
                        cid = sync(ep.get_cid())
                except ResponseCodeException as e:
                    logger.warning(f'bangumi episode lookup failed for ssid={sid}, epid={ep_id}, code={e.code}, msg={e.msg}')
                    if e.code == -10403:
                        return json_fail(
                            'region_restricted',
                            data={
                                'ssid': sid,
                                'epid': ep_id,
                                'title': title or str(idx + 1),
                            },
                            message='该番剧因地区限制暂时无法播放',
                        ), 451
                    raise

            ep_dict_lst.append({
                'idx': idx,
                'epid': ep_id,
                'bvid': bvid,
                'cid': cid,
                'title': title or str(idx + 1),
                'cover': cover,
            })
        return json_ok(ep_dict_lst)
    
    
    # @app.route('/api/bilibili/bangumi_ss/<string:sid>/<int:idx>', methods=['GET'])
    # def get_bilibili_bangumi_chunk(sid, idx):
    #     bgm = bangumi.Bangumi(ssid=sid)
    #     ep_lst = sync(bgm.get_episodes())
    #     logger.info(f'ep list:{ep_lst}')
    #     bvid = sync(ep_lst[idx].get_bvid())
    #     output_video_path = f'/tmp/bv_output_{bvid}.flv'
    #     range_header = request.headers.get('range') # bytes=0-524287
    #     start, end = range_header.replace('bytes=', '').split('-')
    #     logger.info(f'get range, start:{start}, end:{end}')

    #     # 将 start 和 end 转换为整数
    #     start = int(start)
    #     end = int(end)
    #     length = end - start + 1
            
    #     DONE_FILE = f'{output_video_path}.done'
    #     CHECK_INTERVAL = 0.1  # 检查间隔（秒）
        
    #     final_size = -1
    #     # wait done or file size > end
    #     # bitrate = get_video_bitrate(output_video_path)
    #     # logger.info(f'bitrate:{bitrate} kb/s')
    #     while True:
    #         size = os.path.getsize(output_video_path)
    #         if os.path.exists(DONE_FILE):
    #             final_size = size
    #             end = min(end, size - 1)
    #             length = end - start + 1 if end > start else 0
    #             break
    #         if size >= end:
    #             break
    #         time.sleep(CHECK_INTERVAL)
        
    #     def generate():
    #         with open(output_video_path, 'rb') as f:
    #             f.seek(start)
    #             chunk = f.read(length)
    #             yield chunk
    #     logger.info(f'final_size:{final_size}')
    #     resp = Response(stream_with_context(generate()), mimetype='video/mp4', headers={
    #         'BV-Content-Length': final_size, 
    #         'Content-Length': length,
    #         'Content-Range': f'bytes {start}-{end}/{final_size if final_size > 0 else "*"}',
    #     })
    #     return resp
            
    @app.route('/api/bilibili/video/<string:bvid>', methods=['GET'])
    @login_check
    def get_bilibili_video_info(bvid):
        v = video.Video(bvid=bvid)
        v_detail = sync(v.get_detail())
        epList = []
        for page in v_detail['View']['pages']:
            epList.append({
                'bvid': bvid,
                'cid': page['cid'],
                'title': page['part'],
                'idx': page['page'],
                'cover': page.get('first_frame')
            })
        
        return json_ok({
            'title': v_detail['View']['title'],
            'desc': v_detail['View']['desc'],
            'epList': epList
        })
    
    @app.route('/api/bilibili/bv/<string:bvid>/<string:cid>/info', methods=['GET'])    
    @login_check
    def get_bilibili_bv_info_stream(bvid, cid):
        start_ms = int(request.args.get('start_ms', '0'))
        return return_bv_stream(bvid, cid, start_ms)

    @app.route('/api/bilibili/bv/<string:bvid>/<string:cid>', methods=['GET'])
    @login_check
    def get_bilibili_bv_chunk(bvid, cid):
        start_ms = int(request.args.get('start_ms', '0'))
        output_video_path = get_output_video_path(bvid, cid, start_ms)
        range_header = request.headers.get('range') # bytes=0-524287
        start, end = range_header.replace('bytes=', '').split('-')
        logger.info(f'get range, start:{start}, end:{end}')

        # 将 start 和 end 转换为整数
        start = int(start)
        end = int(end)
        length = end - start + 1
            
        DONE_FILE = get_cache_done_path(output_video_path)
        CHECK_INTERVAL = 0.1  # 检查间隔（秒）

        if not os.path.exists(output_video_path):
            return_bv_stream(bvid, cid, start_ms)
        if not wait_for_output_file(output_video_path):
            return json_fail('Video generation timeout'), 504
        
        final_size = -1
        # wait done or file size > end
        # bitrate = get_video_bitrate(output_video_path)
        # logger.info(f'bitrate:{bitrate} kb/s')
        while True:
            size = os.path.getsize(output_video_path)
            if os.path.exists(DONE_FILE):
                final_size = size
                end = min(end, size - 1)
                length = end - start + 1 if end > start else 0
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
        resp = Response(stream_with_context(generate()), mimetype='video/mp4', headers={
            'BV-Content-Length': final_size, 
            'Content-Length': length,
            'Content-Range': f'bytes {start}-{end}/{final_size if final_size > 0 else "*"}',
        })
        return resp

    @app.route('/api/bilibili/bangumi_ep/<string:epid>/<string:cid>/info', methods=['GET'])
    @login_check
    def get_bilibili_bangumi_info_stream(epid, cid):
        start_ms = int(request.args.get('start_ms', '0'))
        return return_bangumi_stream(epid, cid, start_ms)

    @app.route('/api/bilibili/bangumi_ep/<string:epid>/<string:cid>', methods=['GET'])
    @login_check
    def get_bilibili_bangumi_chunk(epid, cid):
        start_ms = int(request.args.get('start_ms', '0'))
        output_video_path = get_output_video_path(f'ep_{epid}', cid, start_ms)
        range_header = request.headers.get('range')
        start, end = range_header.replace('bytes=', '').split('-')
        logger.info(f'get bangumi range, start:{start}, end:{end}, epid:{epid}')

        start = int(start)
        end = int(end)
        length = end - start + 1

        DONE_FILE = get_cache_done_path(output_video_path)
        CHECK_INTERVAL = 0.1

        if not os.path.exists(output_video_path):
            result = return_bangumi_stream(epid, cid, start_ms, as_response=False)
            if not (isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], dict)):
                return result
        if not wait_for_output_file(output_video_path):
            return json_fail('Video generation timeout'), 504

        final_size = -1
        while True:
            size = os.path.getsize(output_video_path)
            if os.path.exists(DONE_FILE):
                final_size = size
                end = min(end, size - 1)
                length = end - start + 1 if end > start else 0
                break
            if size >= end:
                break
            time.sleep(CHECK_INTERVAL)

        def generate():
            with open(output_video_path, 'rb') as f:
                f.seek(start)
                chunk = f.read(length)
                yield chunk

        return Response(stream_with_context(generate()), mimetype='video/mp4', headers={
            'BV-Content-Length': final_size,
            'Content-Length': length,
            'Content-Range': f'bytes {start}-{end}/{final_size if final_size > 0 else "*"}',
        })

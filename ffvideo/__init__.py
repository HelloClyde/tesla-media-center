from loguru import logger
import os
from bilibili_api import video, Credential, HEADERS, bangumi
import imageio_ffmpeg
import requests
import asyncio
import aiohttp


import os
import multiprocessing  
import threading


# init pipe
output_pipe = '/tmp/output_pipe'
if os.path.exists(output_pipe):
    os.remove(output_pipe)
os.mkfifo(output_pipe)

# config
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
# 1100x624
FFMPEG_VF_ARG = '-vf "scale=1100:624:force_original_aspect_ratio=decrease,pad=1100:624:(ow-iw)/2:(oh-ih)/2"'
chunk_size = 10240
video_q = '-q 10'


# context
cur_video_config = None
cur_video = None
# playing pause stop
play_state = 'playing'


class LocalVideo:
    def __init__(self, path):
        self.path = path
        
    async def start(self):
        cmd = f'{FFMPEG_PATH} -re -i {self.path} -codec:v mpeg1video {video_q} -r 24 -bf 0 -codec:a mp2 -f mpegts {FFMPEG_VF_ARG} {output_pipe} -y'
        self.ffmgeg_proc = await asyncio.create_subprocess_shell(cmd)
        
    async def seek(self, ts):
        pass
    
    async def close(self):
        self.ffmgeg_proc.terminate()

class BiliDlVideo:
    def __init__(self, bvid):
        self.bvid = bvid
        self.input_video_pipe = '/tmp/input_video_pipe'
        self.input_audio_pipe = '/tmp/input_audio_pipe'
        if os.path.exists(self.input_video_pipe):
            os.remove(self.input_video_pipe)
        if os.path.exists(self.input_audio_pipe):
            os.remove(self.input_audio_pipe)
        os.mkfifo(self.input_video_pipe)
        os.mkfifo(self.input_audio_pipe)
        
    def download_stream(self, url, pipe_path):
        try:
            logger.info(f'url:{url}, pipe_path:{pipe_path}')
            response = requests.get(url, stream=True, headers=HEADERS)
            response.raise_for_status()

            logger.info(f'start download..')
            with open(pipe_path, 'wb') as wf:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    # logger.info(f'chunk, pipe:{pipe_path}')
                    if chunk:
                        wf.write(chunk)
            logger.info(f'download finished, url:{url}')
        except Exception as e:
            logger.exception("download fail.")
            self.close()

    
    async def start(self):
        # 获取下载链接
        v = video.Video(bvid=self.bvid)
        download_url_data = await v.get_download_url(0)
        detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
        streams = detecter.detect_best_streams()
        if detecter.check_video_and_audio_stream():
            self.tasks = [
                threading.Thread(target=self.download_stream, args=(streams[0].url, self.input_video_pipe)),
                threading.Thread(target=self.download_stream, args=(streams[1].url, self.input_audio_pipe))
            ]
            for task in self.tasks:
                task.start()
            cmd = f'{FFMPEG_PATH} -i {self.input_video_pipe} -i {self.input_audio_pipe} -codec:v mpeg1video {video_q} -r 24 -bf 0 -codec:a mp2 -f mpegts {FFMPEG_VF_ARG} /tmp/{self.bvid}.ts -y'
            logger.info(f'cmd:{cmd}')
            self.ffmgeg_proc = await asyncio.create_subprocess_shell(cmd)
        else:
            # self.tasks = [
            #     threading.Thread(target=self.download_stream, args=(streams[0].url, self.input_video_pipe)),
            # ]
            # cmd = f'{FFMPEG_PATH} -re -i {self.input_video_pipe} -codec:v mpeg1video {video_q} -r 24 -bf 0 -codec:a mp2 -f mpegts {FFMPEG_VF_ARG} {output_pipe} -y'
            # self.ffmgeg_proc = await asyncio.create_subprocess_shell(cmd)
            pass
        
    async def seek(self, ts):
        pass
    
    async def close(self):
        self.ffmgeg_proc.terminate()

class BiliVideo:
    def __init__(self, bvid):
        self.bvid = bvid
        self.input_video_pipe = '/tmp/input_video_pipe'
        self.input_audio_pipe = '/tmp/input_audio_pipe'
        if os.path.exists(self.input_video_pipe):
            os.remove(self.input_video_pipe)
        if os.path.exists(self.input_audio_pipe):
            os.remove(self.input_audio_pipe)
        os.mkfifo(self.input_video_pipe)
        os.mkfifo(self.input_audio_pipe)
        
    def download_stream(self, url, pipe_path):
        try:
            logger.info(f'url:{url}, pipe_path:{pipe_path}')
            response = requests.get(url, stream=True, headers=HEADERS)
            response.raise_for_status()

            logger.info(f'start download..')
            with open(pipe_path, 'wb') as wf:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    # logger.info(f'chunk, pipe:{pipe_path}')
                    if chunk:
                        wf.write(chunk)
            logger.info(f'download finished, url:{url}')
        except Exception as e:
            logger.exception("download fail.")
            self.close()

    
    async def start(self):
        # 获取下载链接
        v = video.Video(bvid=self.bvid)
        download_url_data = await v.get_download_url(0)
        detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
        streams = detecter.detect_best_streams()
        logger.info(f'detecter:{detecter.__dict__}')
        if detecter.check_video_and_audio_stream():
            self.tasks = [
                threading.Thread(target=self.download_stream, args=(streams[0].url, self.input_video_pipe)),
                threading.Thread(target=self.download_stream, args=(streams[1].url, self.input_audio_pipe))
            ]
            for task in self.tasks:
                task.start()
            cmd = f'{FFMPEG_PATH} -re -i {self.input_video_pipe} -i {self.input_audio_pipe} -codec:v mpeg1video {video_q} -r 24 -bf 0 -codec:a mp2 -f mpegts {FFMPEG_VF_ARG} {output_pipe} -y'
            self.ffmgeg_proc = await asyncio.create_subprocess_shell(cmd)
        else:
            self.tasks = [
                threading.Thread(target=self.download_stream, args=(streams[0].url, self.input_video_pipe)),
            ]
            cmd = f'{FFMPEG_PATH} -re -i {self.input_video_pipe} -codec:v mpeg1video {video_q} -r 24 -bf 0 -codec:a mp2 -f mpegts {FFMPEG_VF_ARG} {output_pipe} -y'
            self.ffmgeg_proc = await asyncio.create_subprocess_shell(cmd)
        
    async def seek(self, ts):
        pass
    
    async def close(self):
        self.ffmgeg_proc.terminate()
        

def set_video_config(video_config):
    global cur_video_config
    cur_video_config = video_config
    
def set_play_state(state):
    global play_state
    play_state = state
    
async def cleanup():
    global cur_video
    logger.info(f'try to close last video')
    try:
        if cur_video is not None:
            await cur_video.close()
            cur_video = None
    except Exception as e:
        logger.exception('close fail.')

async def sync_to_ws(ws):
    logger.info(f'sync to ws func')
    # create video
    global cur_video_config
    global cur_video
    global play_state
    
    try:
        logger.info(f'{cur_video_config} {cur_video} {play_state}')
        if cur_video_config is None:
            logger.error(f'not video config')
            raise Exception('not video config')
        if cur_video is not None:
            await cleanup()

        video_type = cur_video_config['type']
        if video_type == 'bv':
            cur_video = BiliVideo(bvid=cur_video_config['bvid'])
        elif video_type == 'bangumi_ss':
            bgm = bangumi.Bangumi(ssid=cur_video_config['sid'])
            ep_lst = await bgm.get_episodes()
            logger.info(f'ep list:{ep_lst}')
            bv_id = ep_lst[0].get_bvid()
            logger.info(f'bvid:{bv_id}')
            cur_video = BiliVideo(bvid=bv_id)
        elif video_type == 'local':
            cur_video = LocalVideo(path=cur_video_config['path'])
        else:
            raise Exception('not support')
        
        # start video thread
        logger.info(f'video :{cur_video}')
        await cur_video.start()
        logger.info(f'video bg thread start, video type:{video_type}')
        
        context_video = cur_video
        with open(output_pipe, 'rb') as pipe:  
            while True:
                try:
                    if context_video != cur_video:
                        logger.error(f'cur video stream closed!')
                        break
                    if play_state == 'playing':
                        chunk = pipe.read(chunk_size)
                        if not chunk:
                            break
                        await ws.send_bytes(chunk)
                    elif play_state == 'pause':
                        await asyncio.sleep(1)
                    else:
                        raise Exception(f'not support play state:{play_state}')
                except asyncio.CancelledError:
                    logger.info("Task was cancelled")
                    break
    except Exception as e:
        logger.exception('sync to ws fail')
    finally:
        await cleanup()
    
    
        

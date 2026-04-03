<script setup lang="ts">
import { ref, onMounted, reactive, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import { ElMessage } from 'element-plus';
import { generateSilentWav } from '@/functions/audioUtils';


const playerCanvas = ref(null);
const videoLoading = ref(null);
const timeTrack = ref(null);
const timeLabel = ref(null);

let videoPlayer: any = null;

const state = reactive({
    curFiles: [] as any[],
    playFile: null,
    path: '',
    isPlay: false,
    curUrl: null as string | null,
    isLongVideo: false,
    isAutoContinue: true,
    showScreen: true
})

function playOrPause() {
    const currentState = videoPlayer.getState();
    console.info('player state', currentState);
    if (currentState == playerStatePlaying) {
        state.isPlay = false;
        videoPlayer.pause();
    } else if (currentState == playerStateIdle) {
        videoPlayer.isPlay = false;
    } else if (currentState == playerStatePausing) {
        state.isPlay = true;
        videoPlayer.resume()
    }
}

function fullscreen() {
    videoPlayer.fullscreen();
}

function playVideo(url: string, isStream=false) {
    videoPlayer.stop();
    console.log(playerCanvas);
    const waitHeaderLength = state.isLongVideo ? 8 * 1024 * 1024 : 512 * 1024;
    console.log('waitHeaderLength', waitHeaderLength);
    videoPlayer.play(url, playerCanvas.value, function (e: any) {
        console.error(e);
        console.error("play error " + e.error + " status " + e.status + ".");
        if (e.error == 1) {
            console.info("Finished.");
        }
    }, waitHeaderLength, isStream);
    state.curUrl = url;
    state.isPlay = true;

    videoPlayer.setTrack(timeTrack.value, timeLabel.value);

    
    const audio:any = document.getElementById("silentAudio");
    // 生成1分钟静音音频
    const base64SilentAudio = generateSilentWav(60);
    audio.src = 'data:audio/wav;base64,' + base64SilentAudio;
    // console.log(base64SilentAudio); // 输出完整base64字符串
    audio.play().catch(() => {
        document.addEventListener("click", () => audio.play());
    });
}


function fileAction(file: any) {
    if (file.fileType == 'DIR') {
        fetchFileList(state.path + '/' + file.fileName);
    } else {
        const fName = file.fileName as string;
        if (!fName.endsWith(".mp4") && !fName.endsWith('.flv')) {
            ElMessage.error('不支持的视频格式');
            return;
        }

        const playUrl = file.url;
        playVideo(playUrl);
        state.playFile = file;
    }
}

function backLastFolder() {
    const parts = state.path.split('\/');
    console.log(parts);
    if (parts.length > 1) {
        const curParts = parts.slice(0, parts.length - 1);
        const newPath = curParts.join('\/');
        console.log('new path:', newPath)
        fetchFileList(newPath);
    } else if (parts[0] != '') {
        fetchFileList('');
    }
}

function fetchFileList(path: string) {
    get(`/api/video/list?path=${path}`, '获取文件列表失败')
        .then(data => {
            state.curFiles = data;
            state.path = path;
        });
}


onMounted(() => {
    fetchFileList(state.path);
    videoPlayer = new Player();
    videoPlayer.setLoadingDiv(videoLoading.value);
    videoPlayer.setFinishCallback(() => {
        if (state.isAutoContinue) {
            const fromIdx = state.curFiles.lastIndexOf(state.playFile);
            for (let i = fromIdx + 1; i < state.curFiles.length; i++) {
                const file = state.curFiles[i];
                const fName = file.fileName as string;
                if (!fName.endsWith(".mp4") && !fName.endsWith(".flv")) {
                    continue;
                }

                ElMessage.info(`自动播放下一集:${fName}`);
                fileAction(file)
                return;
            }
        }
    });
})

onUnmounted(() => {
    // if (videoPlayer.value != null) {
    //     console.log(videoPlayer);
    //     videoPlayer.value.destroy();
    // }
    videoPlayer.stop();
})

</script>

<template>
    <div class="local-video-page">
        <div ref="videoWrapper" class="local-player-stage">
            <canvas id="player-canvas" ref="playerCanvas" width="1100" height="623"></canvas>
            <div v-show="!state.showScreen" class="screenCap"></div>
            <div class="local-video-float" @click="playOrPause">
                <div class="loadEffect" id="loading" ref="videoLoading" style="display:none;">
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
                <div class="local-video-play-btn" v-if="!state.isPlay">
                    <el-icon :size="100">
                        <VideoPlay />
                    </el-icon>
                </div>
            </div>
        </div>
        <div class="local-bottom-controller">
            <div>
                <input class="local-progress" id="timeTrack" ref="timeTrack" type="range" value="0">
            </div>
            <div class="local-controller-btn">
                <label id="timeLabel" ref="timeLabel" style="padding-left:10px;">00:00:00/00:00:00</label>
                <el-switch class="long-video-switch" inline-prompt v-model="state.isLongVideo" size="large" active-text="长视频"
                    inactive-text="短视频" />
                <el-switch class="long-video-switch" inline-prompt v-model="state.isAutoContinue" size="large" active-text="续播"
                    inactive-text="单播" />
                <el-switch class="long-video-switch" inline-prompt v-model="state.showScreen" size="large" active-text="视频"
                    inactive-text="仅音频" />
                <el-icon :size="35" class="right" @click="fullscreen">
                    <FullScreen />
                </el-icon>
                <audio id="silentAudio" loop controls style="height: 28px;">
                    <source src="data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAABCxAgAEABAAZGF0YQAAAAA=">
                </audio>
            </div>
        </div>
        <div class="local-playlist">
            <div class="local-playlist-grid">
                <el-card class="local-playlist-item" @click="backLastFolder">
                    <template #header>
                        <div class="local-playlist-item-icon">
                            <el-icon>
                                <ArrowLeftBold />
                            </el-icon>
                        </div>
                    </template>
                    <el-text size="large" class="local-playlist-back">返回上一级</el-text>
                </el-card>
                <el-card v-for="item of state.curFiles" class="local-playlist-item" @click="fileAction(item)">
                    <template #header>
                        <div class="local-playlist-item-icon" :class="{ 'local-playlist-active': item === state.playFile }">
                            <el-icon v-if="item.fileType == 'DIR'">
                                <Folder />
                            </el-icon>
                            <el-icon v-else>
                                <Film />
                            </el-icon>
                        </div>
                    </template>
                    <el-text line-clamp="2" size="large" :class="{ 'local-playlist-active': item === state.playFile }">
                        {{ item.fileName }}
                    </el-text>
                </el-card>
            </div>
        </div>
    </div>
</template>


<style>
.local-video-page {
    width: 100%;
    height: 100%;
    min-height: 100%;
    display: flex;
    flex-direction: column;
    overflow-x: hidden;
    overflow-y: auto;
    background: var(--color-surface);
}

.screenCap {
    position: absolute;
    width: 100%;
    height: 100%;
    top: 0;
    background-image: url('/screen-cap.jpg');
}

.long-video-switch {
    font-size: 14px;
    line-height: 24px;
    height: 40px;
    margin-left: 10px;
    margin-right: 10px;
}

.right {
    float: right;
    margin-right: 20px;
}

.local-controller-btn {
    font-size: 25px;
}

.local-progress {
    width: 100%;
    height: 34px;
}

.local-video-float {
    position: absolute;
    inset: 0;
}

.local-video-play-btn {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #808080;
}

.local-bottom-controller {
    width: 100%;
    flex: 0 0 auto;
    padding: 12px 16px 0;
    box-sizing: border-box;
}

.local-player-stage {
    position: relative;
    width: 100%;
    max-width: 100%;
    aspect-ratio: 1100 / 623;
    background: #000;
    overflow: hidden;
}

.local-player-stage > canvas {
    width: 100%;
    height: 100%;
    display: block;
    background-color: black;
}

.local-playlist {
    flex: 0 0 auto;
    overflow: auto;
    padding: 12px 16px 16px;
    box-sizing: border-box;
}

.local-playlist-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 14px;
    align-items: stretch;
}

.local-playlist-active {
    color: rgb(64, 158, 255) !important;
}

.local-playlist-back {
    display: inline-block;
    text-align: center;
}

.local-playlist-item {
    position: relative;
    min-height: 120px;
}

.local-playlist-item .el-text {
    width: 100%;
}

.local-playlist-item .el-card__header {
    padding: 4px;
}

.local-playlist-item .el-card__body {
    padding: 4px;
}

.local-playlist-item-icon {
    font-size: 50px;
    line-height: 50px;
    text-align: center;
    color: rgb(80, 77, 77);
}

.playlist-item-title {
    font-size: 24px;
    color: rgb(80, 77, 77);
    text-align: center;
    line-height: 24px;
    margin-top: -15px;
}


.loadEffect {
    width: 120px;
    height: 120px;
    position: absolute;
    margin: auto;
    top: 0;
    left: 0;
    bottom: 0;
    right: 0;
    z-index: 999;
}

.loadEffect span {
    display: inline-block;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #808080;
    position: absolute;
    -webkit-animation: load 1.04s ease infinite;
}

@-webkit-keyframes load {
    0% {
        opacity: 1;
    }

    100% {
        opacity: 0.2;
    }
}

.loadEffect span:nth-child(1) {
    left: 0;
    top: 50%;
    margin-top: -8px;
    -webkit-animation-delay: 0.13s;
}

.loadEffect span:nth-child(2) {
    left: 14px;
    top: 14px;
    -webkit-animation-delay: 0.26s;
}

.loadEffect span:nth-child(3) {
    left: 50%;
    top: 0;
    margin-left: -8px;
    -webkit-animation-delay: 0.39s;
}

.loadEffect span:nth-child(4) {
    top: 14px;
    right: 14px;
    -webkit-animation-delay: 0.52s;
}

.loadEffect span:nth-child(5) {
    right: 0;
    top: 50%;
    margin-top: -8px;
    -webkit-animation-delay: 0.65s;
}

.loadEffect span:nth-child(6) {
    right: 14px;
    bottom: 14px;
    -webkit-animation-delay: 0.78s;
}

.loadEffect span:nth-child(7) {
    bottom: 0;
    left: 50%;
    margin-left: -8px;
    -webkit-animation-delay: 0.91s;
}

.loadEffect span:nth-child(8) {
    bottom: 14px;
    left: 14px;
    -webkit-animation-delay: 1.04s;
}
</style>

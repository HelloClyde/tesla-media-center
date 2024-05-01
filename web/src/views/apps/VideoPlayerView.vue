<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import { ElMessage } from 'element-plus';


const playerCanvas = ref(null);
const videoLoading = ref(null);
const timeTrack = ref(null);
const timeLabel = ref(null);

let videoPlayer = shallowRef<any>(null);

const state = reactive({
    curFiles: [] as any[],
    path: '',
    isPlay: false,
    curUrl: null as string | null,
    isLongVideo: false
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

function playVideo(url: string) {
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
    }, waitHeaderLength, false);
    state.curUrl = url;
    state.isPlay = true;

    videoPlayer.setTrack(timeTrack.value, timeLabel.value);
}


function fileAction(file: any) {
    if (file.fileType == 'DIR') {
        fetchFileList(state.path + '/' + file.fileName);
    } else {
        const fName = file.fileName as string;
        if (!fName.endsWith(".mp4")) {
            ElMessage.error('不支持的视频格式');
            return;
        }

        const playUrl = file.url;
        playVideo(playUrl);
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

})

onUnmounted(() => {
    // if (videoPlayer.value != null) {
    //     console.log(videoPlayer);
    //     videoPlayer.value.destroy();
    // }
})

</script>

<template>
    <!-- player -->
    <div ref="videoWrapper" class="player">
        <canvas id="player-canvas" ref="playerCanvas" width="1100" height="623"></canvas>
        <div class="video-float" @click="playOrPause">
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
            <div class="video-play-btn" v-if="!state.isPlay">
                <el-icon :size="100">
                    <VideoPlay />
                </el-icon>
            </div>
        </div>
    </div>
    <div class="buttom-controller">
        <div>
            <input class="progress" id="timeTrack" ref="timeTrack" type="range" value="0">
        </div>
        <div class="controller-btn">
            <label id="timeLabel" ref="timeLabel" style="padding-left:10px;">00:00:00/00:00:00</label>
            <el-switch class="long-video-switch" v-model="state.isLongVideo" size="large" active-text="长视频" inactive-text="短视频" />
            <el-icon :size="35" class="right" @click="fullscreen">
                <FullScreen />
            </el-icon>
        </div>
    </div>
    <!-- video menu -->
    <div class="playlist">
        <div class="playlist-item" @click="backLastFolder">
            <div class="playlist-item-icon">
                <el-icon>
                    <ArrowLeftBold />
                </el-icon>
            </div>
            <div class="playlist-item-title">返回上一级</div>
        </div>
        <div v-for="item of state.curFiles" class="playlist-item" @click="fileAction(item)">
            <div class="playlist-item-icon">
                <el-icon v-if="item.fileType == 'DIR'">
                    <Folder />
                </el-icon>
                <el-icon v-else>
                    <Film />
                </el-icon>
            </div>
            <div class="playlist-item-title">{{ item.fileName }}</div>
        </div>
    </div>
</template>


<style>
.long-video-switch {
    top: -3px;
    margin-left: 10px;
}

.right {
    float: right;
    margin-right: 20px;
}

.controller-btn {
    font-size: 25px;
}

.progress {
    width: 1100px;
    height: 34px;
}

.video-float {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
}

.video-play-btn {
    position: absolute;
    top: 258px;
    left: 500px;
    color: #808080;
}

.buttom-controller {
    /* position: absolute; */
    /* bottom: 0px; */
    width: 1100px;
    height: 80px;
}

.player {
    width: 1100px;
    height: 623px;
    /* position: absolute; */
    /* bottom: 80px; */
}

.player>canvas {
    width: 100%;
    height: 100%;
    background-color: black;
}

.playlist {
    height: 196px;
    border-bottom: 3px solid #ccc;
    overflow: auto;
}

.playlist-item {
    display: inline-block;
    position: relative;
    width: 200px;
    height: 120px;
}

.playlist-item-icon {
    width: 200px;
    height: 80px;
    font-size: 60px;
    text-align: center;
}

.playlist-item-title {
    font-size: 24px;
    color: black;
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
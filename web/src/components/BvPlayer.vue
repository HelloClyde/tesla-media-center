<script setup lang="ts">
import { ref, onMounted, reactive, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import { ElMessage } from 'element-plus';
import { generateSilentWav } from '@/functions/audioUtils';


const playerCanvas = ref<HTMLCanvasElement | null>(null);
const videoLoading = ref<HTMLElement | null>(null);
const timeTrack = ref<HTMLInputElement | null>(null);
const timeLabel = ref<HTMLLabelElement | null>(null);

let videoPlayer: any = null;
const waitHeaderLength = 512 * 1024;
const DEFAULT_DANMU_AREA = 'top_half';
const DEFAULT_DANMU_MAX_COUNT = 30;
const DEFAULT_DANMU_OPACITY = 70;

const state = reactive({
    curFiles: [] as any[],
    playFile: null,
    path: '',
    isPlay: false,
    curUrl: null as string | null,
    isLongVideo: false,
    isAutoContinue: true,
    showScreen: true,
    dms: [] as any[],
    loadedDmKeys: new Set() as Set<string>,
    processedDmKeys: new Set() as Set<string>,
    dm_seg: 0,
    dmSwitch: true,
    epList: [] as any[],
    epid: null as string | null,
    bvid: null as string | null,
    cid: null as string | null,
    title: null as string | null,
    desc: null as string| null,
    danmuArea: DEFAULT_DANMU_AREA,
    danmuMaxCount: DEFAULT_DANMU_MAX_COUNT,
    danmuOpacity: DEFAULT_DANMU_OPACITY,
})

const getDmKey = (dm: any) => dm.id_str;

const currentEpIndex = computed(() => {
    return state.epList.findIndex((ep: any) => {
        if (props.type === 'bangumi_ss') {
            return String(ep.epid) === String(state.epid);
        }
        return ep.bvid === state.bvid && String(ep.cid) === String(state.cid);
    });
});

function playOrPause() {
    // const currentState = videoPlayer.getState();
    // console.info('player state', currentState);
    // if (currentState == playerStatePlaying) {
    //     state.isPlay = false;
    //     videoPlayer.pause();
    // } else if (currentState == playerStateIdle) {
    //     videoPlayer.isPlay = false;
    // } else if (currentState == playerStatePausing) {
    //     state.isPlay = true;
    //     videoPlayer.resume()
    // }
}

function getStreamUrl(startMs = 0) {
    const baseUrl = props.type === 'bangumi_ss'
        ? `/api/bilibili/bangumi_ep/${state.epid}/${state.cid}`
        : `/api/bilibili/bv/${state.bvid}/${state.cid}`;
    if (startMs > 0) {
        return `${baseUrl}?start_ms=${Math.floor(startMs)}`;
    }
    return baseUrl;
}

function clearDanmuScreen() {
    const container = document.getElementById('danmu-container');
    if (container) {
        container.innerHTML = '';
    }
}

function resetDanmuState(startSec = 0) {
    state.dm_seg = Math.floor(startSec / (6 * 60));
    state.dms = [];
    state.loadedDmKeys = new Set();
    state.processedDmKeys = new Set();
    clearDanmuScreen();
}

function loadDanmuForCurrentPosition(startSec = 0) {
    resetDanmuState(startSec);
    return get(`/api/bilibili/bv/${state.bvid}/dm/${state.dm_seg}`).then(data => {
        const initialDms = data.dm.filter((dm: any) => dm.dm_time >= startSec);
        state.dms = initialDms;
        initialDms.forEach((dm: any) => {
            state.loadedDmKeys.add(getDmKey(dm));
        });
    }).catch(() => {
        state.dms = [];
    });
}

function playCurrentVideo(startMs = 0) {
    const streamUrl = getStreamUrl(startMs);
    videoPlayer.stop();
    videoPlayer.play(`stream://${streamUrl}`, playerCanvas.value, function (e: any) {
        console.error(e);
        console.error("play error " + e.error + " status " + e.status + ".");
        if (e.error == 1) {
            console.info("Finished.");
        }
    }, waitHeaderLength, true);
    videoPlayer.streamBaseOffset = startMs / 1000;
    videoPlayer.beginTimeOffset = startMs / 1000;
    if (timeTrack.value) {
        timeTrack.value.value = String(startMs);
    }
    if (timeLabel.value && videoPlayer.displayDuration) {
        timeLabel.value.innerHTML = `${videoPlayer.formatTime(startMs / 1000)}/${videoPlayer.displayDuration}`;
    }
    state.isPlay = true;
    return loadDanmuForCurrentPosition(startMs / 1000);
}

function seekVideo(ms: number) {
    if ((!state.bvid && !state.epid) || !state.cid) {
        return;
    }
    playCurrentVideo(ms);
}

function playNextEp() {
    const nextEp = state.epList[currentEpIndex.value + 1];
    if (!nextEp) {
        return;
    }

    ElMessage.info(`自动播放下一集:${nextEp.title}`);
    switchEp(nextEp);
}

interface VideoProps {
    type: 'bv' | 'bangumi_ss';
    id: string;
    onClose?: () => void;
}

const props = defineProps<VideoProps>();

function popDanmu(t: number) {
    const currentDms = [...state.dms];
    const readyToShow: any[] = [];
    for (const dm of currentDms) {
        const key = getDmKey(dm);
        if (dm.dm_time < t && !state.processedDmKeys.has(key)) {
            readyToShow.push(dm);
        }
    }

    const visibleDanmuCount = getVisibleDanmuCount();
    const availableSlots = Math.max(0, state.danmuMaxCount - visibleDanmuCount);
    const showDanmu = readyToShow.slice(0, availableSlots);
    const newProcessedKeys = new Set<string>();
    showDanmu.forEach(danmu => 
        addDanmu(danmu.text, `#${danmu.color}`)
    );
    showDanmu.forEach((dm) => {
        newProcessedKeys.add(getDmKey(dm));
    });

    newProcessedKeys.forEach(key => 
        state.processedDmKeys.add(key)
    );

    state.dms = state.dms.filter(dm => 
        !newProcessedKeys.has(getDmKey(dm))
    );

    newProcessedKeys.forEach(key => {
        state.loadedDmKeys.delete(key);
    });
}

function getVisibleDanmuCount() {
    const container = document.getElementById('danmu-container');
    if (!container) {
        return 0;
    }
    return container.getElementsByClassName('danmu').length;
}

onMounted(() => {
    videoPlayer = new Player();
    videoPlayer.setLoadingDiv(videoLoading.value);
    videoPlayer.setFinishCallback(() => {
        state.isPlay = false;
        if (state.isAutoContinue) {
            playNextEp();
        }
    });

    get('/api/config', '读取 B 站弹幕设置失败').then((config) => {
        const area = config?.bilibili_danmaku_area;
        const maxCount = Number(config?.bilibili_danmaku_max_count);
        const opacity = Number(config?.bilibili_danmaku_opacity);
        state.danmuArea = ['top_third', 'top_half', 'bottom_half', 'full'].includes(area) ? area : DEFAULT_DANMU_AREA;
        state.danmuMaxCount = Number.isFinite(maxCount) ? Math.min(100, Math.max(5, Math.floor(maxCount))) : DEFAULT_DANMU_MAX_COUNT;
        state.danmuOpacity = Number.isFinite(opacity) ? Math.min(100, Math.max(10, Math.floor(opacity))) : DEFAULT_DANMU_OPACITY;
    }).catch(() => {
        state.danmuArea = DEFAULT_DANMU_AREA;
        state.danmuMaxCount = DEFAULT_DANMU_MAX_COUNT;
        state.danmuOpacity = DEFAULT_DANMU_OPACITY;
    });

    new Promise((resolve, reject) => {
        if (props.type == 'bv'){
            return get(`/api/bilibili/video/${props.id}`).then(data => {
                state.epList = data.epList;
                state.title = data.title;
                state.desc = data.desc;
                console.log('ep_list', state.epList);
                state.epid = null;
                state.bvid = state.epList[0].bvid;
                state.cid = state.epList[0].cid;
                resolve(`/api/bilibili/bv/${state.bvid}/${state.cid}`);
            });
        }else if (props.type == 'bangumi_ss'){
            return get(`/api/bilibili/bangumi_ss/${props.id}`).then(data => {
                state.epList = data;
                console.log('ep_list', state.epList);
                state.epid = state.epList[0].epid;
                state.bvid = state.epList[0].bvid;
                state.cid = state.epList[0].cid;
                resolve(`/api/bilibili/bangumi_ep/${state.epid}/${state.cid}`);
            })
        }
    }).then(url => {
        console.log('url', url);
        return playCurrentVideo(0);
    }).then(() => {
        if (timeTrack.value) {
            timeTrack.value.oninput = (event: Event) => {
                const target = event.target as HTMLInputElement;
                if (timeLabel.value && videoPlayer.duration > 0) {
                    timeLabel.value.innerHTML = `${videoPlayer.formatTime(Number(target.value) / 1000)}/${videoPlayer.displayDuration}`;
                }
            };
            timeTrack.value.onchange = (event: Event) => {
                const target = event.target as HTMLInputElement;
                seekVideo(Number(target.value));
            };
        }
    }).catch((error) => {
        console.error('init bilibili player failed', error);
        state.isPlay = false;
        props.onClose?.();
    });
    
    videoPlayer.setTimeCallback((t: number) => {
        popDanmu(t);
        const seg = Math.floor(t / (6 * 60));
        if (state.dm_seg < seg){
            state.dm_seg = seg;
            get(`/api/bilibili/bv/${state.bvid}/dm/${seg}`).then(data => {
                const newDms = data.dm.filter((dm: any) => {
                    const key = getDmKey(dm);
                    return !state.processedDmKeys.has(key) && !state.loadedDmKeys.has(key);
                });
                newDms.forEach((dm: any) => {
                    state.loadedDmKeys.add(getDmKey(dm));
                });
                state.dms = [...state.dms, ...newDms];
            }).catch(() => {
                // Ignore transient danmu failures; playback should continue.
            });
        }
    })
    state.isPlay = true;

    const audio:any = document.getElementById("silentAudio");
    const base64SilentAudio = generateSilentWav(60);
    audio.src = 'data:audio/wav;base64,' + base64SilentAudio;
    audio.play().catch(() => {
        document.addEventListener("click", () => audio.play());
    });

    videoPlayer.setTrack(timeTrack.value, timeLabel.value);

})

function addDanmu(danmuText: string, color='#fff') {
    const container: any = document.getElementById('danmu-container');
    if (!danmuText || !container) return;

    const danmu = document.createElement('div');
    danmu.className = 'danmu';
    danmu.innerText = danmuText;
    danmu.style.left = `${container.offsetWidth}px`;
    danmu.style.top = `${getDanmuTop(container.offsetHeight)}px`;
    danmu.style.color = color;
    danmu.style.opacity = `${state.danmuOpacity / 100}`;
    danmu.style.backgroundColor = `rgba(0, 0, 0, ${Math.max(0.08, state.danmuOpacity / 200)})`;

    container.appendChild(danmu);

    moveDanmu(danmu, container);
}

function getDanmuTop(containerHeight: number) {
    const maxTop = Math.max(containerHeight - 30, 0);
    if (maxTop === 0) {
        return 0;
    }

    const ranges: Record<string, [number, number]> = {
        top_third: [0, containerHeight / 3],
        top_half: [0, containerHeight / 2],
        bottom_half: [containerHeight / 2, containerHeight],
        full: [0, containerHeight],
    };
    const [rawStart, rawEnd] = ranges[state.danmuArea] || ranges.top_half;
    const start = Math.min(maxTop, Math.max(0, rawStart));
    const end = Math.min(containerHeight, Math.max(start + 1, rawEnd));
    const usableHeight = Math.max(1, end - start - 30);
    return Math.min(maxTop, start + Math.random() * usableHeight);
}

function moveDanmu(elem: any, container: any) {
    let pos = parseInt(elem.style.left);
    const id = setInterval(frame, 50);

    function frame() {
        if (!elem || !elem.parentNode || !container.contains(elem)) {
            clearInterval(id);
            return;
        }
        if (pos < -elem.offsetWidth) {
            clearInterval(id);
            if (elem.parentNode) {
                elem.parentNode.removeChild(elem);
            }
        } else {
            pos -= 5;
            elem.style.left = `${pos}px`;
        }
    }
}

function switchDanmu(){
    state.dmSwitch = !state.dmSwitch;
}

function switchEp(ep: any){
    state.epid = ep.epid ?? null;
    state.bvid = ep.bvid;
    state.cid = ep.cid;
    playCurrentVideo(0);
}

function isCurrentEp(ep: any) {
    if (props.type === 'bangumi_ss') {
        return String(ep.epid) === String(state.epid);
    }
    return ep.bvid === state.bvid && String(ep.cid) === String(state.cid);
}

onUnmounted(() => {
    videoPlayer.stop();
})


</script>

<template>
    <div class="bv-video-play-view">
        <div ref="videoWrapper" class="bv-player-stage">
            <canvas id="player-canvas" ref="playerCanvas" width="1100" height="623"></canvas>
            <div v-show="!state.showScreen" class="screenCap"></div>
            <div id="danmu-container" class="danmu-container" v-show="state.dmSwitch">
                <!-- 弹幕将动态添加到这里 -->
            </div>
            <div class="bv-video-float" @click="playOrPause">
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
                <div class="bv-video-play-btn" v-if="!state.isPlay">
                    <el-icon :size="100">
                        <VideoPlay />
                    </el-icon>
                </div>
            </div>
        </div>
        <div class="bv-bottom-controller">
            <div>
                <input class="progress" id="timeTrack" ref="timeTrack" type="range" value="0">
            </div>
            <div>
                <label id="timeLabel" ref="timeLabel" style="padding-left:10px;">00:00:00/00:00:00</label>
                <el-switch class="long-video-switch" inline-prompt v-model="state.isAutoContinue" size="large" active-text="续播"
                    inactive-text="单播" />
                <audio id="silentAudio" loop controls style="height: 28px;display: none;">
                    <source src="data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAABCxAgAEABAAZGF0YQAAAAA=">
                </audio>
            </div>
            <el-row justify="start">
                <el-col :span="24">
                    <el-button icon="Back" class="btn" size="large" @click="props.onClose" circle />
                    <el-button icon="ChatLineRound" class="btn" size="large" @click="switchDanmu" circle></el-button>
                    <el-text class="bv-title" size="large">{{ state.title }}</el-text>
                </el-col>
            </el-row>
            <el-row justify="start">
                <el-col :span="24">
                    <div class="ep-list">
                        <div class="ep-item" :class="{ 'ep-item-active': isCurrentEp(ep) }" v-for="(ep, index) in state.epList" :key="index" @click="switchEp(ep)">
                            <img :src="ep.cover || 'https://i0.hdslb.com/bfs/static/studio/creativecenter-platform/img/article_empty.716e40d2.png'" :fit="'cover'" />
                            <el-text line-clamp="2" class="ep-title" :class="{ 'ep-title-active': isCurrentEp(ep) }">
                                {{ ep.title }}
                            </el-text>
                        </div>    
                    </div>
                </el-col>
            </el-row>
        </div>
    </div>
</template>

<style>
.btn {
    font-size: 26px !important;
}

.bv-title {
    font-size: 26px !important;
    line-height: 28px;
}

.bv-desc {
    margin-left: 8px !important;
}

.long-video-switch {
    font-size: 14px;
    line-height: 24px;
    height: 40px;
    margin-left: 10px;
    margin-right: 10px;
}

.bv-player-stage {
    position: relative;
    width: 100%;
    max-width: 100%;
    aspect-ratio: 1100 / 623;
    background: #000;
    overflow: hidden;
}

.bv-player-stage > canvas {
    width: 100%;
    height: 100%;
    display: block;
    background: #000;
}

.bv-video-float {
    position: absolute;
    inset: 0;
}

.bv-video-play-btn {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #808080;
}

.bv-bottom-controller {
    width: 100%;
    flex: 0 0 auto;
    overflow: visible;
    padding: 12px 16px 0;
    box-sizing: border-box;
}

.progress {
    width: 100%;
    height: 34px;
}

.ep-list  {
    margin-top: 4px;
    display: flex;
    width: 100%;
    max-width: 100%;
    height: 164px;
    overflow-x: auto;
    scrollbar-width: none;
    padding: 6px 0 10px;
    box-sizing: border-box;
}

.ep-item {
    margin-bottom: 5px;
    margin-left: 0 !important;
    margin-right: 10px;
    width: clamp(140px, 16vw, 150px);
    min-width: clamp(140px, 16vw, 150px);
    height: 134px;
    display: inline-block;
    border-radius: 14px;
    padding: 6px;
    box-sizing: border-box;
    background: var(--color-card-gradient);
    border: 1px solid rgba(15, 23, 42, 0.08);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease, background 160ms ease;
    cursor: pointer;
}

.ep-item > img {
    width: 100%;
    height: 85px;
    border-radius: 10px;
    display: block;
    object-fit: cover;
}

.ep-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 30px rgba(15, 23, 42, 0.1);
}

.ep-item-active {
    background: linear-gradient(180deg, var(--color-surface-strong) 0%, var(--color-accent-soft) 100%);
    border-color: var(--color-border-hover);
    box-shadow: 0 18px 34px var(--color-shadow);
    transform: translateY(-3px);
}

.ep-item-active > img {
    border-radius: 10px;
}

.ep-title {
    display: block;
    margin-top: 8px;
    min-height: 36px;
    line-height: 18px;
    color: #475569;
    transition: color 160ms ease;
}

.ep-title-active {
    color: #0f172a !important;
    font-weight: 700;
}

.danmu-container {
    border: 0px solid rgb(0, 0, 0);
    position: absolute;
    inset: 0;
    top: 0;
    overflow: hidden;
}


.danmu {
    position: absolute;
    white-space: nowrap;
    font-size: 20px;
    color: white;
    padding: 5px;
    margin: 5px;
    border-radius: 5px;
    background-color: rgba(0, 0, 0, 0.5);
}

#videoWrapper {
    width: 100%;
    height: 100%;
}

.bv-video-play-view {
    width: 100%;
    height: 100%;
    min-height: 100%;
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    overflow-x: hidden;
    overflow-y: auto;
    color: var(--color-text);
    background: var(--color-surface-strong);
}

.videoCtl {
    padding: 20px;
}
</style>

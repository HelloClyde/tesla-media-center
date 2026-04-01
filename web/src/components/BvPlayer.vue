<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import { ElMessage } from 'element-plus';
import { generateSilentWav } from '@/functions/audioUtils';


const playerCanvas = ref<HTMLCanvasElement | null>(null);
const videoLoading = ref<HTMLElement | null>(null);
const timeTrack = ref<HTMLInputElement | null>(null);
const timeLabel = ref<HTMLLabelElement | null>(null);

let videoPlayer = shallowRef<any>(null);
const waitHeaderLength = 512 * 1024 * 1;

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
    bvid: null as string | null,
    cid: null as string | null,
    title: null as string | null,
    desc: null as string| null,
})

const getDmKey = (dm: any) => dm.id_str;

const currentEpIndex = computed(() => {
    return state.epList.findIndex((ep: any) => ep.bvid === state.bvid && String(ep.cid) === String(state.cid));
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
    const baseUrl = `/api/bilibili/bv/${state.bvid}/${state.cid}`;
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
    if (!state.bvid || !state.cid) {
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
    // 使用当前弹幕的副本进行处理
    const currentDms = [...state.dms];
    const toRemove: any[] = [];
    const newProcessedKeys = new Set<string>();

    // 遍历副本，避免处理过程中原数组被修改
    for (const dm of currentDms) {
        const key = getDmKey(dm);
        if (dm.dm_time < t && !state.processedDmKeys.has(key)) {
            toRemove.push(dm);
            newProcessedKeys.add(key);
        }
    }

    // 显示弹幕（截断至100条）
    const showDanmu = toRemove.slice(0, 100);
    showDanmu.forEach(danmu => 
        addDanmu(danmu.text, `#${danmu.color}`)
    );

    // 更新已处理的弹幕键
    newProcessedKeys.forEach(key => 
        state.processedDmKeys.add(key)
    );

    // 从原数组中过滤已处理的弹幕
    state.dms = state.dms.filter(dm => 
        !newProcessedKeys.has(getDmKey(dm))
    );

    newProcessedKeys.forEach(key => {
        state.loadedDmKeys.delete(key);
    });
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

    new Promise((resolve, reject) => {
        if (props.type == 'bv'){
            return get(`/api/bilibili/video/${props.id}`).then(data => {
                state.epList = data.epList;
                state.title = data.title;
                state.desc = data.desc;
                console.log('ep_list', state.epList);
                state.bvid = state.epList[0].bvid;
                state.cid = state.epList[0].cid;
                resolve(`/api/bilibili/bv/${state.bvid}/${state.cid}`);
            });
        }else if (props.type == 'bangumi_ss'){
            return get(`/api/bilibili/bangumi_ss/${props.id}`).then(data => {
                state.epList = data;
                console.log('ep_list', state.epList);
                state.bvid = state.epList[0].bvid;
                state.cid = state.epList[0].cid;
                resolve(`/api/bilibili/bv/${state.bvid}/${state.cid}`);
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
    })
    ;
    
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
    if (!danmuText) return;

    const danmu = document.createElement('div');
    danmu.className = 'danmu';
    danmu.innerText = danmuText;
    danmu.style.left = `${container.offsetWidth}px`;
    danmu.style.top = `${Math.random() * (container.offsetHeight * 2 / 3 - 20)}px`;
    danmu.style.color = color

    container.appendChild(danmu);

    moveDanmu(danmu, container);
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
    state.bvid = ep.bvid;
    state.cid = ep.cid;
    playCurrentVideo(0);
}

function isCurrentEp(ep: any) {
    return ep.bvid === state.bvid && String(ep.cid) === String(state.cid);
}

onUnmounted(() => {
    videoPlayer.stop();
})


</script>

<template>
    <div class="videoPlayView">
        <div ref="videoWrapper" class="player">
            <canvas id="player-canvas" ref="playerCanvas" width="1100" height="623"></canvas>
            <div v-show="!state.showScreen" class="screenCap"></div>
            <div id="danmu-container" class="danmu-container" v-show="state.dmSwitch">
                <!-- 弹幕将动态添加到这里 -->
            </div>
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

.ep-list  {
    margin-top: 4px;
    display: flex;
    width: 1100px;
    height: 164px;
    overflow-x: auto;
    scrollbar-width: none;
    padding: 6px 0 10px;
}

.ep-item {
    margin-bottom: 5px;
    margin-left: 0 !important;
    margin-right: 10px;
    width: 150px;
    min-width: 150px;
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
    width: 138px;
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
    width: 1100px;
    height: 623px;
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
    width: 1100px;
    height: 624px;
}

.videoPlayView {
    width: 1100px;
    height: 899px;
    position: absolute;
    top: 0px;
    /* z-index: 1000; */
    color: var(--color-text);
    background: var(--color-surface-strong);
}

.videoCtl {
    padding: 20px;
}
</style>

<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import { ElMessage } from 'element-plus';
import { generateSilentWav } from '@/functions/audioUtils';


const playerCanvas = ref(null);
const videoLoading = ref(null);
const timeTrack = ref(null);
const timeLabel = ref(null);

let videoPlayer = shallowRef<any>(null);

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
    dm_seg: 0,
    dmSwitch: true,
})

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

interface VideoProps {
    type: 'bv' | 'local';
    url: string;
    id: string;
    onClose?: () => void;
}

const props = defineProps<VideoProps>();

function popDanmu(t: number) {
    // 创建一个新的数组用于存储需要移除的对象
    const toRemove: any[] = [];

    // 遍历原数组，找到所有 dm_time 小于 t 的对象
    for (let i = 0; i < state.dms.length; i++) {
        if (state.dms[i].dm_time < t) {
            toRemove.push(state.dms[i]); // 将符合条件的对象加入到移除列表
        }
    }
    
    let showDanmu = toRemove;
    if (toRemove.length > 100){
        console.warn('弹幕数量大于100，截断');
        showDanmu = toRemove.slice(0, 100);
    }
    
    for (const danmu of showDanmu){
        addDanmu(danmu.text, `#${danmu.color}`);
    }
    

    // 使用 filter 方法创建一个新数组，过滤掉需要移除的对象
    if (toRemove.length > 0){
        state.dms = state.dms.filter((item: any) => !toRemove.includes(item));
    }
    
}



onMounted(() => {
    videoPlayer = new Player();
    videoPlayer.setLoadingDiv(videoLoading.value);
    const waitHeaderLength = 512 * 1024 * 1;
    console.log('waitHeaderLength', waitHeaderLength);
    videoPlayer.play(`stream://${props.url}`, playerCanvas.value, function (e: any) {
        console.error(e);
        console.error("play error " + e.error + " status " + e.status + ".");
        if (e.error == 1) {
            console.info("Finished.");
        }
    }, waitHeaderLength, true);
    videoPlayer.setTimeCallback((t: number) => {
        popDanmu(t);
        const seg = t / (6 * 60);
        if (state.dm_seg < seg){
            state.dm_seg = state.dm_seg + 1;
            get(`/api/bilibili/bv/${props.id}/dm/${state.dm_seg}`).then(data => {
                console.log('加载下一波弹幕', data);
                state.dms = [...state.dms, ...data.dm];
            })
        }
    })
    state.isPlay = true;

    // 生成1分钟静音音频
    const audio:any = document.getElementById("silentAudio");
    const base64SilentAudio = generateSilentWav(60);
    audio.src = 'data:audio/wav;base64,' + base64SilentAudio;
    audio.play().catch(() => {
        document.addEventListener("click", () => audio.play());
    });

    videoPlayer.setTrack(timeTrack.value, timeLabel.value);

    // 加载弹幕
    state.dm_seg = 0;
    get(`/api/bilibili/bv/${props.id}/dm/${state.dm_seg}`).then(data => {
        console.log(data);
        state.dms = data.dm;
    })
})

function addDanmu(danmuText: string, color='#fff') {
    const container: any = document.getElementById('danmu-container');
    if (!danmuText) return;

    const danmu = document.createElement('div');
    danmu.className = 'danmu';
    danmu.innerText = danmuText;
    danmu.style.left = `${container.offsetWidth}px`; // 初始位置在右侧外部
    danmu.style.top = `${Math.random() * (container.offsetHeight - 20)}px`; // 随机高度
    danmu.style.color = color

    container.appendChild(danmu);

    moveDanmu(danmu, container);
}

function moveDanmu(elem: any, container: any) {
    let pos = parseInt(elem.style.left);
    const id = setInterval(frame, 50); // 每5ms移动一次

    function frame() {
        if (pos < -elem.offsetWidth) { // 如果完全离开左侧
            clearInterval(id);
            elem.parentNode.removeChild(elem); // 删除元素
        } else {
            pos -= 5; // 向左移动
            elem.style.left = `${pos}px`;
        }
    }
}

function switchDanmu(){
    state.dmSwitch = !state.dmSwitch;
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
                <audio id="silentAudio" loop controls style="height: 28px;">
                    <source src="data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAABCxAgAEABAAZGF0YQAAAAA=">
                </audio>
            </div>
            <el-row justify="start">
                <el-col :span="4">
                    <el-button icon="Back" class="btn" size="large" @click="props.onClose" circle />
                    <el-button icon="ChatLineRound" class="btn" size="large" @click="switchDanmu" circle></el-button>
                </el-col>
            </el-row>
        </div>
    </div>
</template>

<style>
.btn {
    font-size: 26px !important;
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
    background: #fff;
}

.videoCtl {
    padding: 20px;
}
</style>

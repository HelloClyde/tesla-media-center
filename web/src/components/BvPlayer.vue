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
    processedDmKeys: new Set() as Set<string>,
    dm_seg: 0,
    dmSwitch: true,
    epList: [] as any[],
    bvid: null as string | null,
})

const getDmKey = (dm: any) => dm.id_str;

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
}

// function popDanmu(t: number) {
//     // 创建一个新的数组用于存储需要移除的对象
//     const toRemove: any[] = [];

//     // 遍历原数组，找到所有 dm_time 小于 t 的对象
//     for (let i = 0; i < state.dms.length; i++) {
//         if (state.dms[i].dm_time < t) {
//             toRemove.push(state.dms[i]); // 将符合条件的对象加入到移除列表
//         }
//     }
    
//     let showDanmu = toRemove;
//     if (toRemove.length > 100){
//         console.warn('弹幕数量大于100，截断');
//         showDanmu = toRemove.slice(0, 100);
//     }
    
//     for (const danmu of showDanmu){
//         addDanmu(danmu.text, `#${danmu.color}`);
//     }
    

//     // 使用 filter 方法创建一个新数组，过滤掉需要移除的对象
//     if (toRemove.length > 0){
//         state.dms = state.dms.filter((item: any) => !toRemove.includes(item));
//     }
    
// }



onMounted(() => {
    videoPlayer = new Player();
    videoPlayer.setLoadingDiv(videoLoading.value);

    new Promise((resolve, reject) => {
        if (props.type == 'bv'){
            state.bvid = props.id;
            resolve(`/api/bilibili/bv/${props.id}` );
        }else if (props.type == 'bangumi_ss'){
            return get(`/api/bilibili/bangumi_ss/${props.id}/info`).then(data => {
                state.epList = data;
                console.log('ep_list', state.epList);
                state.bvid = state.epList[0].bvid;
                resolve(`/api/bilibili/bv/${state.bvid}`);
            })
        }
    }).then(url => {
        console.log('url', url);
        videoPlayer.play(`stream://${url}`, playerCanvas.value, function (e: any) {
            console.error(e);
            console.error("play error " + e.error + " status " + e.status + ".");
            if (e.error == 1) {
                console.info("Finished.");
            }
        }, waitHeaderLength, true);
        
        // 加载弹幕
        state.dm_seg = 0;
        return get(`/api/bilibili/bv/${state.bvid}/dm/${state.dm_seg}`)
    }).then(data => {
        console.log('danmu', data);
        state.dms = data.dm;
    })
    ;
    
    videoPlayer.setTimeCallback((t: number) => {
        popDanmu(t);
        // const seg = t / (6 * 60);
        const seg = t / 30;
        if (state.dm_seg < seg){
            state.dm_seg = state.dm_seg + 1;
            // 在加载新弹幕的请求中
            get(`/api/bilibili/bv/${state.bvid}/dm/${state.dm_seg}`).then(data => {
                const newDms = data.dm.filter((dm: any) => 
                    !state.processedDmKeys.has(getDmKey(dm))
                );
                state.dms = [...state.dms, ...newDms];
            });
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

})

function addDanmu(danmuText: string, color='#fff') {
    const container: any = document.getElementById('danmu-container');
    if (!danmuText) return;

    const danmu = document.createElement('div');
    danmu.className = 'danmu';
    danmu.innerText = danmuText;
    danmu.style.left = `${container.offsetWidth}px`; // 初始位置在右侧外部
    danmu.style.top = `${Math.random() * (container.offsetHeight * 2 / 3 - 20)}px`; // 随机高度
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

function switchEp(ep: any){
    new Promise((resolve, reject) => {
        state.bvid = ep.bvid;
        resolve(`/api/bilibili/bv/${ep.bvid}`);
    }).then(url => {
        console.log('url', url);
        videoPlayer.stop();
        videoPlayer.play(`stream://${url}`, playerCanvas.value, function (e: any) {
            console.error(e);
            console.error("play error " + e.error + " status " + e.status + ".");
            if (e.error == 1) {
                console.info("Finished.");
            }
        }, waitHeaderLength, true);
        
        // 加载弹幕
        state.dm_seg = 0;
        return get(`/api/bilibili/bv/${state.bvid}/dm/${state.dm_seg}`)
    }).then(data => {
        console.log('danmu', data);
        state.dms = data.dm;
    })
    ;
    
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
                <audio id="silentAudio" loop controls style="height: 28px;display: none;">
                    <source src="data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAABCxAgAEABAAZGF0YQAAAAA=">
                </audio>
            </div>
            <el-row justify="start">
                <el-col :span="4">
                    <el-button icon="Back" class="btn" size="large" @click="props.onClose" circle />
                    <el-button icon="ChatLineRound" class="btn" size="large" @click="switchDanmu" circle></el-button>
                </el-col>
                <el-col :span="20">
                    <el-button v-for="(ep, index) in state.epList" class="ep-item" @click="switchEp(ep)">{{ index + 1 }}</el-button>
                </el-col>
            </el-row>
        </div>
    </div>
</template>

<style>
.btn {
    font-size: 26px !important;
}

.ep-item {
    margin-bottom: 5px;
    margin-left: 0 !important;
    margin-right: 5px;
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

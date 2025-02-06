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
    showScreen: true
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
    onClose?: () => void;
}

const props = defineProps<VideoProps>();


// function playVideo() {
//     if (props.type == 'bv'){
//         const waitHeaderLength = 512 * 1024 * 2;
//         // const 
//         console.log('waitHeaderLength', waitHeaderLength);
//         videoPlayer.play(`/api/bilibili/bv/${props.url}`, playerCanvas.value, function (e: any) {
//             console.error(e);
//             console.error("play error " + e.error + " status " + e.status + ".");
//             if (e.error == 1) {
//                 console.info("Finished.");
//             }
//         }, waitHeaderLength, true);
//         state.isPlay = true;

//         videoPlayer.setTrack(timeTrack.value, timeLabel.value);
//     } else if (props.type == 'local'){

//     }
    // videoPlayer.stop();
    // console.log(playerCanvas);
    // const waitHeaderLength = state.isLongVideo ? 8 * 1024 * 1024 : 512 * 1024;
    // console.log('waitHeaderLength', waitHeaderLength);
    // videoPlayer.play(url, playerCanvas.value, function (e: any) {
    //     console.error(e);
    //     console.error("play error " + e.error + " status " + e.status + ".");
    //     if (e.error == 1) {
    //         console.info("Finished.");
    //     }
    // }, waitHeaderLength, isStream);
    // state.curUrl = url;
    // state.isPlay = true;

    // videoPlayer.setTrack(timeTrack.value, timeLabel.value);

    
    // const audio:any = document.getElementById("silentAudio");
    // // 生成1分钟静音音频
    // const base64SilentAudio = generateSilentWav(60);
    // audio.src = 'data:audio/wav;base64,' + base64SilentAudio;
    // // console.log(base64SilentAudio); // 输出完整base64字符串
    // audio.play().catch(() => {
    //     document.addEventListener("click", () => audio.play());
    // });
// }


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

onUnmounted(() => {
    videoPlayer.stop();
})


</script>

<template>
    <div class="videoPlayView">
        <div ref="videoWrapper" class="player">
            <canvas id="player-canvas" ref="playerCanvas" width="1100" height="623"></canvas>
            <div v-show="!state.showScreen" class="screenCap"></div>
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
                    <el-button icon="Back" size="large" @click="props.onClose" circle />
                </el-col>
            </el-row>
        </div>
    </div>
</template>

<style>
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

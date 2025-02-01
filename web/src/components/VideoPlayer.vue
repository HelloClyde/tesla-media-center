<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import JSMpeg from '@/components/JsmpegPlayer';
import { generateSilentWav} from '@/functions/audioUtils';



const state = reactive({
    streamWsUrl: '',
    ctlWs: null as any,
    player: null as any,
    curTime: 0,
    totalTime: -1,
})

interface VideoProps {
    type: 'bv' | 'local';
    videoConfig: any;
    onClose?: () => void;
}

const props = defineProps<VideoProps>();


function send_ctl_msg(type: string, args: any) {
    state.ctlWs.send(JSON.stringify({
        type,
        args,
    }))
}

onMounted(() => {
    console.log('props', props);

    var hostname = document.location.hostname;
    var port = document.location.port;
    var schema = window.location.protocol;
    var wsSchema = 'ws:'
    if (schema == 'https:'){
        wsSchema = 'wss:'
    }

    state.streamWsUrl = `${wsSchema}//${hostname}:${port}/api/ws`
    state.ctlWs = new WebSocket(`${wsSchema}//${hostname}:${port}/api/ws/ctl`);
    const videoConfig = props.videoConfig;
    videoConfig['type'] = props.type;

    state.ctlWs.onopen = function (event: any) {
        send_ctl_msg('init', videoConfig);
    };


    state.ctlWs.onmessage = function (event: any) {
        const msg = event.data;
        if (msg == 'init_ok'){
            const canvasEl = document.getElementById('videoWrapper');
            state.player = new JSMpeg.Player(state.streamWsUrl, {
                canvas: canvasEl,
                progressive: true,
                onVideoDecode: (decoder:  any, time: any) => {
                    state.curTime = time;
                },
                videoBufferSize: 512*1024 * 4,
                audioBufferSize: 128*1024 * 4,
                maxAudioLag: 0.25 * 4,
            });
        }
    };

    
    const audio:any = document.getElementById("silentAudio");
    // 生成1分钟静音音频
    const base64SilentAudio = generateSilentWav(60);
    audio.src = 'data:audio/wav;base64,' + base64SilentAudio;
    // console.log(base64SilentAudio); // 输出完整base64字符串
    audio.play().catch(() => {
        document.addEventListener("click", () => audio.play());
    });
})

const formatTooltip = (val: number) => {
    return `${state.curTime} / ${state.totalTime}`
}


onUnmounted(() => {
    state.player.destroy();
})


</script>

<template>
    <div class="videoPlayView">
        <canvas id="videoWrapper"></canvas>
        <div class="videoCtl">
            <el-row justify="center">
                <el-col :span="18">
                    <el-slider v-model="state.curTime" :format-tooltip="formatTooltip" :disabled="true" />
                </el-col>
                <el-col :span="6">
                    <audio id="silentAudio" loop controls style="height: 28px;">
                        <source src="data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAABCxAgAEABAAZGF0YQAAAAA=">
                    </audio>
                </el-col>
            </el-row>
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
    z-index: 99999;
    background: #fff;
}

.videoCtl {
    padding: 20px;
}
</style>

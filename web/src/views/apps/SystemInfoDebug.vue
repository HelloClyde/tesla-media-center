

<script setup lang="ts">
import SimpleView from '@/components/SimpleView.vue';
import { reactive } from 'vue'
import { onMounted, computed } from 'vue'
import { useGeoLocationStore } from '@/stores/geoLocation';
import getAMap from '@/functions/amapConfig';
import { get } from '@/functions/requests'
import { ElMessage } from 'element-plus';
import { RouterView,useRouter, useRoute } from 'vue-router';


const router = useRouter();

const state = reactive({
    screenInfo: {
        width: 0,
        height: 0,
    },
    screenView: {
        width: 0,
        height: 0
    },
    tts: {
        voices: ''
    },
    media: {
        devices: ''
    },
    browser: ''
})

let recorder: MediaRecorder | null = null;

const postionState = useGeoLocationStore();

const formatedPostion = computed(() => {
    const curPos = postionState.getCurPosition();
    return JSON.stringify(curPos, null, '\t')
})

function refresh() {
    state.screenInfo = window.screen;
    state.screenView = {
        width: window.innerWidth,
        height: window.innerHeight
    };
    state.tts = {
        voices: JSON.stringify(window.speechSynthesis.getVoices(), null, '\t'),
    }

    navigator.mediaDevices.enumerateDevices()
        .then(function (devices) {
            state.media.devices = JSON.stringify(devices, null, '\t');
        })
        .catch(function (err) {
            state.media.devices = err.name + ": " + err.message
        });
}

function h5TTS(text: string) {
    const utterThis = new window.SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterThis);
    console.info('tts played');
}

function audioTest(){
    var audioCtx = new window.AudioContext();

    // Stereo
    var channels = 2;
    // Create an empty two second stereo buffer at the
    // sample rate of the AudioContext
    var frameCount = audioCtx.sampleRate * 2.0;

    var myArrayBuffer = audioCtx.createBuffer(2, frameCount, audioCtx.sampleRate);
    // Fill the buffer with white noise;
    //just random values between -1.0 and 1.0
    for (var channel = 0; channel < channels; channel++) {
        // This gives us the actual ArrayBuffer that contains the data
        var nowBuffering = myArrayBuffer.getChannelData(channel);
        for (var i = 0; i < frameCount; i++) {
        // Math.random() is in [0; 1.0]
        // audio needs to be in [-1.0; 1.0]
        nowBuffering[i] = Math.random() * 2 - 1;
        }
    }

    // Get an AudioBufferSourceNode.
    // This is the AudioNode to use when we want to play an AudioBuffer
    var source = audioCtx.createBufferSource();
    // set the buffer in the AudioBufferSourceNode
    source.buffer = myArrayBuffer;
    // connect the AudioBufferSourceNode to the
    // destination so we can hear the sound
    source.connect(audioCtx.destination);
    // start the source playing
    source.start();
}

function startRec() {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        console.log('get audio stream');
        recorder = new MediaRecorder(stream);
        recorder.addEventListener('dataavailable', event => {
            console.log(stream);
        })
        recorder.start();
    }).catch(e => {
        console.error('get audio stream fail.', e)
        console.log(e.message);
    })
}

function stopRec() {
    if (recorder !== null) {
        recorder.stop();
    }
}

function logout() {
    get('/api/logout').then(data => {
        console.log('logout', data);
        ElMessage.success('已退出登陆');
        router.push('/login');
    })
}


onMounted(() => {
    refresh();
    postionState.init();
    getAMap().then(amap => {
        state.browser = JSON.stringify(amap?.Browser, null, '\t');
    })
})
</script>

<template>
    <SimpleView>
        <el-descriptions title="系统调试信息" :column="1" size="default" border>
            <template #extra>
                <div><el-button type="primary" round @click="refresh">刷新</el-button></div>
            </template>
            <el-descriptions-item label="屏幕像素" width="30px">
                {{ state.screenInfo.width }} * {{ state.screenInfo.height }}
            </el-descriptions-item>
            <el-descriptions-item label="显示区像素">
                {{ state.screenView.width }} * {{ state.screenView.height }}
            </el-descriptions-item>
            <el-descriptions-item label="当前定位">
                {{ formatedPostion }}
            </el-descriptions-item>
            <el-descriptions-item label="媒体设备">
                <div class="text-block">{{ state.media.devices }}</div>
            </el-descriptions-item>
            <el-descriptions-item label="录音">
                <el-button type="default" round @click="startRec">开始录音</el-button>
                <el-button type="default" round @click="stopRec">结束录音</el-button>
                <a href="https://recorder.zhuyuntao.cn/">录音demo</a>
            </el-descriptions-item>
            <el-descriptions-item label="浏览器详情">
                <div class="text-block">{{ state.browser }}</div>
            </el-descriptions-item>
            <el-descriptions-item label="TTS">
                <el-button type="default" round @click="h5TTS('你好，特斯拉！')">H5TTS播放“你好特斯拉”</el-button>
                <el-button type="default" round @click="h5TTS('hello tesla!')">H5TTS播放“hello tesla”</el-button>
            </el-descriptions-item>
            <el-descriptions-item label="Audio">
                <el-button type="default" round @click="audioTest()">AudioTest</el-button>
            </el-descriptions-item>
            <el-descriptions-item label="账号">
                <el-button type="default" round @click="logout()">退出登陆</el-button>
            </el-descriptions-item>
        </el-descriptions>
    </SimpleView>
</template>

<style>
.text-block {
    word-break: break-word;
    white-space: pre-wrap;
}
</style>

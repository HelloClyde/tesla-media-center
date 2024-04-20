

<script setup lang="ts">
import SimpleView from '@/components/SimpleView.vue';
import { reactive } from 'vue'
import { onMounted, computed } from 'vue'
import { useGeoLocationStore } from '@/stores/geoLocation';
import AMapLoader from '@amap/amap-jsapi-loader';

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


onMounted(() => {
    refresh();
    postionState.init();
    state.browser = JSON.stringify((window as any).AMap.Browser, null, '\t');
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
        </el-descriptions>
    </SimpleView>
</template>

<style>
.text-block {
    word-break: break-word;
    white-space: pre-wrap;
}
</style>

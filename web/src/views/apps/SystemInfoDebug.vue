

<script setup lang="ts">
import SimpleView from '@/components/SimpleView.vue';
import { reactive } from 'vue'
import { onMounted, computed } from 'vue'
import { useGeoLocationStore } from '@/stores/geoLocation';
import getAMap from '@/functions/amapConfig';
import { get, post } from '@/functions/requests'
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
    ,
    bilibiliCache: {
        cacheDir: '',
        maxSizeMb: 2048,
        sizeMb: 0,
        fileCount: 0,
        diskFreeMb: 0
    },
    cacheForm: {
        maxSizeMb: 2048
    },
    cacheLoading: false,
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

    refreshBilibiliCache();
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

function logout() {
    get('/api/logout').then(data => {
        console.log('logout', data);
        ElMessage.success('已退出登陆');
        router.push('/login');
    })
}

function refreshBilibiliCache() {
    state.cacheLoading = true;
    get('/api/bilibili/cache', '读取缓存信息失败').then(data => {
        state.bilibiliCache = data;
        state.cacheForm.maxSizeMb = data.maxSizeMb;
    }).finally(() => {
        state.cacheLoading = false;
    });
}

function saveBilibiliCacheSettings() {
    state.cacheLoading = true;
    post('/api/bilibili/cache/settings', {
        maxSizeMb: state.cacheForm.maxSizeMb,
    }, '保存缓存配置失败').then(data => {
        state.bilibiliCache = data;
        state.cacheForm.maxSizeMb = data.maxSizeMb;
        const deletedSizeMb = data.cleanup?.deletedSizeMb ?? 0;
        ElMessage.success(deletedSizeMb > 0 ? `缓存上限已保存，并回收了 ${deletedSizeMb} MB` : '缓存上限已保存');
    }).finally(() => {
        state.cacheLoading = false;
    });
}

function clearBilibiliCache() {
    state.cacheLoading = true;
    post('/api/bilibili/cache/clear', {}, '清理缓存失败').then(data => {
        state.bilibiliCache = data;
        state.cacheForm.maxSizeMb = data.maxSizeMb;
        const deletedSizeMb = data.cleanup?.deletedSizeMb ?? 0;
        ElMessage.success(`缓存已清理，释放 ${deletedSizeMb} MB`);
    }).finally(() => {
        state.cacheLoading = false;
    });
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
            <el-descriptions-item label="账号">
                <el-button type="default" round @click="logout()">退出登陆</el-button>
            </el-descriptions-item>
            <el-descriptions-item label="B站缓存">
                <div class="cache-panel" v-loading="state.cacheLoading">
                    <div>缓存目录：{{ state.bilibiliCache.cacheDir || '-' }}</div>
                    <div>当前占用：{{ state.bilibiliCache.sizeMb }} MB</div>
                    <div>缓存文件：{{ state.bilibiliCache.fileCount }}</div>
                    <div>磁盘剩余：{{ state.bilibiliCache.diskFreeMb }} MB</div>
                    <div class="cache-actions">
                        <el-input-number v-model="state.cacheForm.maxSizeMb" :min="256" :step="256" :max="102400" />
                        <span>MB</span>
                        <el-button type="primary" round @click="saveBilibiliCacheSettings">保存缓存上限</el-button>
                        <el-button type="danger" plain round @click="clearBilibiliCache">一键清理缓存</el-button>
                    </div>
                </div>
            </el-descriptions-item>
        </el-descriptions>
    </SimpleView>
</template>

<style>
.text-block {
    word-break: break-word;
    white-space: pre-wrap;
}

.cache-panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.cache-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 4px;
}
</style>

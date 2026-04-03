<script setup lang="ts">
import SimpleView from '@/components/SimpleView.vue';
import { reactive, onMounted, computed } from 'vue';
import { useGeoLocationStore } from '@/stores/geoLocation';
import getAMap from '@/functions/amapConfig';
import { get, post } from '@/functions/requests';
import { ElMessage } from 'element-plus';
import { useRouter } from 'vue-router';

const router = useRouter();

const state = reactive({
    screenInfo: {
        width: 0,
        height: 0,
    },
    screenView: {
        width: 0,
        height: 0,
    },
    tts: {
        voices: '',
    },
    media: {
        devices: '',
    },
    browser: '',
    mapConfig: {
        amapKey: '',
    },
    mapLoading: false,
});

let recorder: MediaRecorder | null = null;

const postionState = useGeoLocationStore();

const formatedPostion = computed(() => {
    const curPos = postionState.getCurPosition();
    return JSON.stringify(curPos, null, '\t');
});

function refresh() {
    state.screenInfo = window.screen;
    state.screenView = {
        width: window.innerWidth,
        height: window.innerHeight,
    };
    state.tts = {
        voices: JSON.stringify(window.speechSynthesis.getVoices(), null, '\t'),
    };

    navigator.mediaDevices.enumerateDevices()
        .then((devices) => {
            state.media.devices = JSON.stringify(devices, null, '\t');
        })
        .catch((err) => {
            state.media.devices = err.name + ': ' + err.message;
        });

    refreshMapConfig();
}

function h5TTS(text: string) {
    const utterThis = new window.SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterThis);
}

function startRec() {
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        recorder = new MediaRecorder(stream);
        recorder.addEventListener('dataavailable', () => {
            console.log(stream);
        });
        recorder.start();
    }).catch((e) => {
        console.error('get audio stream fail.', e);
    });
}

function stopRec() {
    if (recorder !== null) {
        recorder.stop();
    }
}

function logout() {
    get('/api/logout').then(() => {
        ElMessage.success('已退出登陆');
        router.push('/login');
    });
}

function refreshMapConfig() {
    state.mapLoading = true;
    get('/api/config', '读取配置失败').then((data) => {
        state.mapConfig.amapKey = data.amap_key || '';
    }).finally(() => {
        state.mapLoading = false;
    });
}

function saveMapConfig() {
    state.mapLoading = true;
    post('/api/config', {
        amap_key: state.mapConfig.amapKey.trim(),
    }, '保存高德 Key 失败').then(() => {
        ElMessage.success('地图配置已保存');
    }).finally(() => {
        state.mapLoading = false;
    });
}

onMounted(() => {
    refresh();
    postionState.init();
    getAMap().then((amap) => {
        state.browser = JSON.stringify(amap?.Browser, null, '\t');
    });
});
</script>

<template>
    <SimpleView>
        <section class="settings-page">
            <header class="settings-hero">
                <div>
                    <p class="hero-kicker">Settings</p>
                    <h1>系统设置与调试</h1>
                    <p class="hero-copy">集中管理缓存、账号和设备状态，常用配置放前面，诊断信息放后面。</p>
                </div>
                <el-button type="primary" round @click="refresh">刷新状态</el-button>
            </header>

            <section class="settings-grid">
                <article class="settings-card">
                    <div class="card-head">
                        <div>
                            <p class="card-kicker">Maps</p>
                            <h2>高德地图</h2>
                        </div>
                    </div>
                    <div class="setting-input" v-loading="state.mapLoading">
                        <span class="setting-label">Web JS API Key</span>
                        <el-input
                            v-model="state.mapConfig.amapKey"
                            type="textarea"
                            :rows="3"
                            placeholder="请输入高德地图 Web 端 Key"
                        />
                    </div>
                    <div class="button-row top-gap">
                        <el-button type="primary" round @click="saveMapConfig">保存 Key</el-button>
                    </div>
                </article>

                <article class="settings-card">
                    <div class="card-head">
                        <div>
                            <p class="card-kicker">Account</p>
                            <h2>账号与语音</h2>
                        </div>
                    </div>
                    <div class="button-column">
                        <el-button type="default" round @click="h5TTS('你好，特斯拉！')">测试中文 TTS</el-button>
                        <el-button type="default" round @click="h5TTS('hello tesla!')">测试英文 TTS</el-button>
                        <el-button type="danger" plain round @click="logout()">退出登录</el-button>
                    </div>
                </article>

                <article class="settings-card">
                    <div class="card-head">
                        <div>
                            <p class="card-kicker">Audio</p>
                            <h2>录音调试</h2>
                        </div>
                    </div>
                    <div class="button-column">
                        <el-button type="default" round @click="startRec">开始录音</el-button>
                        <el-button type="default" round @click="stopRec">结束录音</el-button>
                        <a class="link-button" href="https://recorder.zhuyuntao.cn/" target="_blank" rel="noreferrer">打开录音 Demo</a>
                    </div>
                </article>
            </section>

            <section class="diagnostics-panel">
                <div class="panel-head">
                    <div>
                        <p class="card-kicker">Diagnostics</p>
                        <h2>设备与环境信息</h2>
                    </div>
                </div>

                <div class="diagnostics-grid">
                    <article class="diagnostic-card">
                        <span class="diagnostic-title">屏幕像素</span>
                        <strong>{{ state.screenInfo.width }} × {{ state.screenInfo.height }}</strong>
                    </article>
                    <article class="diagnostic-card">
                        <span class="diagnostic-title">显示区域</span>
                        <strong>{{ state.screenView.width }} × {{ state.screenView.height }}</strong>
                    </article>
                    <article class="diagnostic-card diagnostic-card--full">
                        <span class="diagnostic-title">当前定位</span>
                        <pre class="text-block">{{ formatedPostion }}</pre>
                    </article>
                    <article class="diagnostic-card diagnostic-card--full">
                        <span class="diagnostic-title">媒体设备</span>
                        <pre class="text-block">{{ state.media.devices }}</pre>
                    </article>
                    <article class="diagnostic-card diagnostic-card--full">
                        <span class="diagnostic-title">浏览器详情</span>
                        <pre class="text-block">{{ state.browser }}</pre>
                    </article>
                </div>
            </section>
        </section>
    </SimpleView>
</template>

<style>
.settings-page {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.settings-hero {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 20px;
    padding: 24px 28px;
    border: 1px solid var(--color-border);
    border-radius: 28px;
    background: linear-gradient(135deg, rgba(28, 126, 214, 0.12) 0%, rgba(255, 255, 255, 0.82) 44%, rgba(255, 255, 255, 0.96) 100%);
    box-shadow: 0 18px 40px var(--color-shadow);
    overflow: hidden;
}

:root[data-theme='dark'] .settings-hero {
    background: linear-gradient(135deg, rgba(108, 182, 255, 0.18) 0%, rgba(18, 32, 48, 0.88) 46%, rgba(12, 20, 32, 0.96) 100%);
}

.hero-kicker,
.card-kicker {
    font-size: 12px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--color-text-soft);
    margin-bottom: 6px;
}

.settings-hero h1,
.panel-head h2,
.card-head h2 {
    margin: 0;
    color: var(--color-heading);
}

.hero-copy {
    margin-top: 8px;
    max-width: 560px;
    color: var(--color-text-soft);
}

.settings-grid {
    display: grid;
    grid-template-columns: 1.6fr 1fr 1fr;
    gap: 16px;
}

.settings-card,
.diagnostics-panel {
    border: 1px solid var(--color-border);
    border-radius: 24px;
    background: var(--color-surface);
    box-shadow: 0 14px 28px var(--color-shadow);
    backdrop-filter: blur(16px);
}

.settings-card {
    padding: 22px;
}

.settings-card--wide {
    min-width: 0;
}

.card-head,
.panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 18px;
}

.usage-pill {
    min-width: 64px;
    padding: 8px 14px;
    border-radius: 999px;
    background: var(--color-accent-soft);
    color: var(--color-accent);
    text-align: center;
    font-weight: 600;
}

.metric-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 16px;
}

.metric-box {
    padding: 14px 16px;
    border-radius: 18px;
    background: var(--color-panel-muted);
    border: 1px solid var(--color-border);
}

.metric-label,
.setting-label,
.diagnostic-title {
    display: block;
    margin-bottom: 6px;
    color: var(--color-text-soft);
    font-size: 13px;
}

.metric-box strong,
.diagnostic-card strong {
    color: var(--color-heading);
    font-size: 20px;
    font-weight: 600;
}

.progress-track {
    height: 10px;
    border-radius: 999px;
    background: var(--color-background-mute);
    overflow: hidden;
    margin-bottom: 16px;
}

.progress-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--color-accent) 0%, #53a8ff 100%);
}

.setting-line {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 14px 16px;
    border-radius: 18px;
    background: var(--color-panel-muted);
    border: 1px solid var(--color-border);
    margin-bottom: 16px;
}

.setting-value {
    color: var(--color-heading);
    word-break: break-all;
}

.setting-actions {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
}

.setting-input {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.inline-control,
.button-row,
.button-column {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
}

.top-gap {
    margin-top: 16px;
}

.button-column {
    flex-direction: column;
}

.unit {
    color: var(--color-text-soft);
    align-self: center;
}

.link-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 40px;
    padding: 0 16px;
    border-radius: 999px;
    border: 1px solid var(--color-border);
    color: var(--color-text);
    text-decoration: none;
    background: var(--color-panel-muted);
}

.diagnostics-panel {
    padding: 22px;
}

.diagnostics-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
}

.diagnostic-card {
    padding: 16px 18px;
    border-radius: 18px;
    background: var(--color-panel-muted);
    border: 1px solid var(--color-border);
}

.diagnostic-card--full {
    grid-column: 1 / -1;
}

.text-block {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--color-text);
    font-size: 13px;
    line-height: 1.55;
}

@media (max-width: 1120px) {
    .settings-grid {
        grid-template-columns: 1fr;
    }

    .metric-row {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 768px) {
    .settings-hero {
        padding: 20px;
        border-radius: 22px;
        flex-direction: column;
        align-items: flex-start;
    }

    .settings-card,
    .diagnostics-panel {
        padding: 18px;
        border-radius: 20px;
    }

    .metric-row,
    .diagnostics-grid {
        grid-template-columns: 1fr;
    }

    .setting-actions {
        align-items: stretch;
    }

    .button-row,
    .inline-control {
        width: 100%;
    }
}
</style>

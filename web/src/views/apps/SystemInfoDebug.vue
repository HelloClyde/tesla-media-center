<script setup lang="ts">
import { navigationCoordinateMode, setNavigationCoordinateMode } from '@/functions/navigationCoordinates';
import MapCacheSettings from '@/components/MapCacheSettings.vue';
import SimpleView from '@/components/SimpleView.vue';
import H5Recorder from '@/components/H5Recorder.vue';
import AudioOutputTest from '@/components/AudioOutputTest.vue';
import NavigationSpeechTest from '@/components/NavigationSpeechTest.vue';
import CameraTest from '@/components/CameraTest.vue';
import WebGLComputeTest from '@/components/WebGLComputeTest.vue';
import ViewportDiagnostics from '@/components/ViewportDiagnostics.vue';
import { reactive, ref, onMounted, onUnmounted, computed } from 'vue';
import { useGeoLocationStore } from '@/stores/geoLocation';
import { get, post } from '@/functions/requests';
import { ElMessage } from 'element-plus';
import { useRouter } from 'vue-router';
import { vConsoleEnabled, setVConsoleEnabled } from '@/functions/debugConsole';

const router = useRouter();
const activeTab = ref('diagnostics');

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
        securityCode: '',
    },
    mapLoading: false,
});

const postionState = useGeoLocationStore();

const formatedPostion = computed(() => {
    const curPos = postionState.getCurPosition();
    return JSON.stringify(curPos, null, '\t');
});

function refreshViewport() {
    state.screenInfo = { width: window.screen.width, height: window.screen.height };
    state.screenView = {
        width: window.innerWidth,
        height: window.innerHeight,
    };
    const viewport = window.visualViewport;
    state.browser = JSON.stringify({
        // The application appends compatibility tokens to navigator.userAgent.
        userAgent: navigator.userAgent,
        language: navigator.language,
        devicePixelRatio: window.devicePixelRatio,
        viewport: state.screenView,
        visualViewport: viewport ? {
            width: Math.round(viewport.width),
            height: Math.round(viewport.height),
            scale: viewport.scale,
        } : null,
        touchPoints: navigator.maxTouchPoints,
        isSecureContext: window.isSecureContext,
    }, null, 2);
}

function refresh() {
    refreshViewport();
    state.tts = {
        voices: JSON.stringify(window.speechSynthesis?.getVoices() || [], null, '\t'),
    };

    navigator.mediaDevices?.enumerateDevices()
        .then((devices) => {
            state.media.devices = JSON.stringify(devices, null, '\t');
        })
        .catch((err) => {
            state.media.devices = err.name + ': ' + err.message;
        });

    refreshMapConfig();
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
        state.mapConfig.securityCode = data.amap_security_js_code || '';
    }).finally(() => {
        state.mapLoading = false;
    });
}

function saveMapConfig() {
    state.mapLoading = true;
    post('/api/config', {
        amap_key: state.mapConfig.amapKey.trim(),
        amap_security_js_code: state.mapConfig.securityCode.trim(),
    }, '保存高德 Key 失败').then(() => {
        ElMessage.success('地图配置已保存');
    }).finally(() => {
        state.mapLoading = false;
    });
}

onMounted(() => {
    window.addEventListener('resize', refreshViewport);
    window.visualViewport?.addEventListener('resize', refreshViewport);
    refresh();
    postionState.init();
});

onUnmounted(() => {
    window.removeEventListener('resize', refreshViewport);
    window.visualViewport?.removeEventListener('resize', refreshViewport);
});
</script>

<template>
    <SimpleView>
        <section class="settings-page">
            <el-tabs v-model="activeTab" class="debug-tabs">
            <el-tab-pane label="设置与账号" name="settings">
            <section class="settings-grid">
                <article class="settings-card">
                    <div class="card-head">
                        <h2>调试控制台</h2>
                        <el-switch :model-value="vConsoleEnabled" aria-label="开启 vConsole" @update:model-value="setVConsoleEnabled($event === true)" />
                    </div>
                    <p class="console-hint">开启后显示 vConsole 悬浮入口，用于查看日志和网络请求。设置仅保存在当前浏览器，刷新后仍生效。</p>
                </article>
                <article class="settings-card">
                    <div class="card-head">
                        <div>
                            <p class="card-kicker">Maps</p>
                            <h2>高德搜索与行程轨迹</h2>
                        </div>
                    </div>
                    <p class="console-hint">用于导航页地点搜索和特斯拉行程轨迹。地点搜索使用 Web JS API 1.4.15；请按需输入 Key 配套的安全密钥。</p>
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
                        <el-input v-model="state.mapConfig.securityCode" type="password" show-password placeholder="安全密钥 securityJsCode（按 Key 要求填写）" aria-label="高德安全密钥" />
                        <el-button type="primary" round @click="saveMapConfig">保存 Key</el-button>
                    </div>
                </article>

                <article class="settings-card">
                    <div class="card-head"><h2>导航定位坐标</h2></div>
                    <el-select :model-value="navigationCoordinateMode" aria-label="导航定位坐标转换" @update:model-value="setNavigationCoordinateMode($event)">
                        <el-option label="不转换（默认）" value="direct" />
                        <el-option label="WGS-84 → GCJ-02" value="wgs84" />
                    </el-select>
                    <p class="console-hint">默认直接使用浏览器返回的经纬度。若浏览器提供 WGS-84 坐标，可选择转换为高德坐标。仅影响导航的浏览器定位，不影响搜索结果或特斯拉车辆数据。选择自动保存在当前浏览器，返回导航后重新定位生效。</p>
                </article>

                <article class="settings-card">
                    <div class="card-head">
                        <div>
                            <p class="card-kicker">Account</p>
                            <h2>账号</h2>
                        </div>
                    </div>
                    <div class="button-column">
                        <el-button type="danger" plain round @click="logout()">退出登录</el-button>
                    </div>
                </article>

            </section>
            </el-tab-pane>
            <el-tab-pane label="地图缓存" name="map-cache"><MapCacheSettings v-if="activeTab === 'map-cache'" /></el-tab-pane>
            <el-tab-pane label="录音与语音" name="audio">
            <section class="settings-grid">
                <article class="settings-card">
                    <div class="card-head"><h2>语音播报</h2></div>
                    <div class="button-column">
                        <el-button type="primary" round @click="activeTab = 'sound'">打开端侧语音测试</el-button>
                    </div>
                </article>
                <article class="settings-card">
                    <div class="card-head">
                        <div>
                            <p class="card-kicker">Audio</p>
                            <h2>H5 录音</h2>
                        </div>
                    </div>
                    <H5Recorder v-if="activeTab === 'audio'" />
                </article>
            </section>

            </el-tab-pane>
            <el-tab-pane label="声音测试" name="sound"><template v-if="activeTab === 'sound'"><NavigationSpeechTest /><AudioOutputTest /></template></el-tab-pane>
            <el-tab-pane label="摄像头测试" name="camera">
                <article class="settings-card">
                    <div class="card-head"><h2>摄像头测试</h2></div>
                    <CameraTest v-if="activeTab === 'camera'" />
                </article>
            </el-tab-pane>
            <el-tab-pane label="WebGL 算力" name="webgl"><WebGLComputeTest v-if="activeTab === 'webgl'" /></el-tab-pane>
            <el-tab-pane label="布局诊断" name="layout"><ViewportDiagnostics /></el-tab-pane>
            <el-tab-pane label="设备诊断" name="diagnostics">
            <section class="diagnostics-panel">
                <div class="panel-head">
                    <div>
                        <p class="card-kicker">Diagnostics</p>
                        <h2>设备与环境信息</h2>
                    </div>
                    <el-button type="primary" round @click="refresh">刷新状态</el-button>
                </div>

                <div class="diagnostics-grid">
                    <article class="diagnostic-card">
                        <span class="diagnostic-title">屏幕尺寸（CSS 像素）</span>
                        <strong>{{ state.screenInfo.width }} × {{ state.screenInfo.height }}</strong>
                    </article>
                    <article class="diagnostic-card">
                        <span class="diagnostic-title">显示区域（布局依据）</span>
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
            </el-tab-pane>
            </el-tabs>
        </section>
    </SimpleView>
</template>

<style scoped>
.console-hint { margin: 0; color: var(--color-text-soft); font-size: 13px; line-height: 1.6; }
.debug-tabs { min-width: 0; }
.debug-tabs :deep(.el-tabs__item) { font-size: clamp(14px, 1.8vw, 18px); height: 44px; padding: 0 14px; }
.debug-tabs :deep(.el-tabs__nav) { height: 44px; }
.debug-tabs :deep(.el-tabs__content) { overflow: visible; }

.settings-page {
    display: flex;
    flex-direction: column;
    gap: var(--page-space);
}

.card-kicker {
    font-size: 12px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--color-text-soft);
    margin-bottom: 6px;
}

.panel-head h2,
.card-head h2 {
    margin: 0;
    color: var(--color-heading);
}

.panel-head h2,
.card-head h2 {
    font-size: clamp(18px, 2vw, 24px);
}

.settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
    gap: 16px;
}

.settings-card,
.diagnostics-panel {
    border: 1px solid var(--color-border);
    min-width: 0;
    border-radius: var(--panel-radius);
    background: var(--color-surface);
    box-shadow: 0 14px 28px var(--color-shadow);
    backdrop-filter: blur(16px);
}

.settings-card {
    padding: var(--panel-space);
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
    padding: var(--panel-space);
}

.diagnostics-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
}

.diagnostic-card {
    min-width: 0;
    padding: var(--page-space);
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
    .metric-row {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 768px) {
    .settings-card,
    .diagnostics-panel {
        padding: var(--panel-space);
        border-radius: 20px;
    }

    .metric-row {
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

@media (max-width: 480px) {
    .diagnostics-grid {
        grid-template-columns: 1fr;
    }
}
</style>

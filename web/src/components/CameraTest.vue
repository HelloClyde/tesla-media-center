<script setup lang="ts">
import { onUnmounted, ref } from 'vue';

const video = ref<HTMLVideoElement | null>(null);
const devices = ref<MediaDeviceInfo[]>([]);
const selected = ref('');
const loading = ref(false);
const active = ref(false);
const error = ref('');
const details = ref('');
let stream: MediaStream | null = null;
let requestId = 0;

function stop() {
    requestId++;
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    if (video.value) video.value.srcObject = null;
    active.value = false;
    loading.value = false;
    details.value = '';
}

async function start() {
    stop();
    error.value = '';
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        error.value = '摄像头不可用，请使用 HTTPS 或 localhost 打开页面。';
        return;
    }
    const currentRequest = requestId;
    loading.value = true;
    try {
        const input = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: selected.value ? { deviceId: { exact: selected.value } } : true,
        });
        if (currentRequest !== requestId) {
            input.getTracks().forEach(track => track.stop());
            return;
        }
        stream = input;
        const track = input.getVideoTracks()[0];
        track.addEventListener('ended', () => {
            if (stream !== input) return;
            stop();
            error.value = '摄像头已断开，请重新开启预览。';
        });
        if (!video.value) { stop(); return; }
        video.value.srcObject = input;
        await video.value.play();
        if (currentRequest !== requestId) return;
        active.value = true;
        const settings = track.getSettings();
        details.value = `${settings.width || video.value.videoWidth} × ${settings.height || video.value.videoHeight}`
            + (settings.frameRate ? ` · ${Math.round(settings.frameRate)} fps` : '');
        selected.value = settings.deviceId || selected.value;
        // Labels become available after permission is granted. Listing failure
        // must not interrupt an otherwise working preview.
        try {
            const list = await navigator.mediaDevices.enumerateDevices();
            if (currentRequest === requestId) devices.value = list.filter(device => device.kind === 'videoinput');
        } catch { /* Keep the current camera usable. */ }
    } catch (reason) {
        if (currentRequest !== requestId) return;
        stop();
        const name = reason instanceof Error ? reason.name : '';
        error.value = name === 'NotAllowedError' ? '摄像头权限被拒绝，请允许访问后重试。'
            : name === 'NotFoundError' ? '没有找到可用的摄像头，当前设备可能未向浏览器开放摄像头。'
            : name === 'NotReadableError' ? '无法读取摄像头，可能正在被其他程序占用。'
            : name === 'OverconstrainedError' ? '所选摄像头不可用，请选择默认摄像头后重试。'
            : '无法开启预览，请检查摄像头和浏览器权限。';
    } finally {
        if (currentRequest === requestId) loading.value = false;
    }
}

function changeCamera() {
    if (active.value) void start();
}

onUnmounted(stop);
</script>

<template>
    <div class="camera-test">
        <p>画面仅在当前页面预览，不录制或上传。切换 Tab 时自动关闭摄像头。</p>
        <div class="camera-actions">
            <label for="debug-camera">摄像头</label>
            <select id="debug-camera" v-model="selected" :disabled="loading" @change="changeCamera">
                <option value="">默认摄像头</option>
                <option v-for="(device, index) in devices" :key="device.deviceId" :value="device.deviceId">{{ device.label || `摄像头 ${index + 1}` }}</option>
            </select>
            <el-button type="primary" round :disabled="loading || active" @click="start">开启预览</el-button>
            <el-button round :disabled="!loading && !active" @click="stop">停止预览</el-button>
        </div>
        <p role="status" aria-live="polite">{{ loading ? '正在请求摄像头权限…' : active ? `预览中 · ${details}` : '摄像头未开启' }}</p>
        <p v-if="error" class="camera-error" role="alert">{{ error }}</p>
        <video ref="video" class="camera-preview" autoplay muted playsinline aria-label="摄像头实时预览"></video>
    </div>
</template>

<style scoped>
.camera-test { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.camera-test p { color: var(--color-text-soft); font-size: 13px; }
.camera-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.camera-actions select { min-width: 0; max-width: 100%; flex: 1 1 180px; padding: 10px; border-radius: 10px; border: 1px solid var(--color-border); color: var(--color-text); background: var(--color-panel-muted); }
.camera-actions .el-button { margin: 0; }
.camera-preview { display: block; width: 100%; height: clamp(180px, 40vh, 480px); object-fit: contain; background: #09111d; border-radius: 14px; }
.camera-test .camera-error { color: var(--el-color-danger); }
</style>

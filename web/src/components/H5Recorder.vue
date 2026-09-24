<script setup lang="ts">
import { onUnmounted, ref } from 'vue';

const canvas = ref<HTMLCanvasElement | null>(null);
const phase = ref<'idle' | 'requesting' | 'recording' | 'stopping'>('idle');
const error = ref('');
const audioUrl = ref('');
let recorder: MediaRecorder | null = null;
let stream: MediaStream | null = null;
let context: AudioContext | null = null;
let frame = 0;
let disposed = false;

function releaseMicrophone() {
    cancelAnimationFrame(frame);
    stream?.getTracks().forEach(track => track.stop());
    stream = null;
    if (context) void context.close().catch(() => {});
    context = null;
}

function draw(analyser: AnalyserNode) {
    const samples = new Uint8Array(analyser.fftSize);
    const render = () => {
        const element = canvas.value;
        const paint = element?.getContext('2d');
        if (!element || !paint) return;
        const width = element.clientWidth;
        const height = element.clientHeight;
        const ratio = window.devicePixelRatio || 1;
        if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
            element.width = Math.round(width * ratio);
            element.height = Math.round(height * ratio);
        }
        paint.setTransform(ratio, 0, 0, ratio, 0, 0);
        paint.clearRect(0, 0, width, height);
        analyser.getByteTimeDomainData(samples);
        paint.strokeStyle = getComputedStyle(element).getPropertyValue('--color-accent').trim() || '#1c7ed6';
        paint.lineWidth = 2;
        paint.beginPath();
        samples.forEach((sample, index) => {
            const x = index * width / (samples.length - 1);
            const y = sample / 255 * height;
            if (index === 0) paint.moveTo(x, y);
            else paint.lineTo(x, y);
        });
        paint.stroke();
        frame = requestAnimationFrame(render);
    };
    render();
}

async function start() {
    if (phase.value !== 'idle') return;
    error.value = '';
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        error.value = '麦克风不可用，请使用 HTTPS 或 localhost 打开页面。';
        return;
    }
    if (!window.MediaRecorder || !window.AudioContext) {
        error.value = '当前浏览器不支持 H5 录音或音频波形分析。';
        return;
    }
    phase.value = 'requesting';
    try {
        // Create/resume during the user gesture; never connect the mic to speakers.
        context = new AudioContext();
        await context.resume();
        if (disposed) return;
        const input = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (disposed) {
            input.getTracks().forEach(track => track.stop());
            return;
        }
        stream = input;
        const analyser = context.createAnalyser();
        analyser.fftSize = 2048;
        context.createMediaStreamSource(input).connect(analyser);
        const activeRecorder = new MediaRecorder(input);
        recorder = activeRecorder;
        const chunks: Blob[] = [];
        activeRecorder.ondataavailable = event => {
            if (event.data.size) chunks.push(event.data);
        };
        activeRecorder.onstop = () => {
            releaseMicrophone();
            recorder = null;
            if (disposed) return;
            if (chunks.length) {
                if (audioUrl.value) URL.revokeObjectURL(audioUrl.value);
                audioUrl.value = URL.createObjectURL(new Blob(chunks, { type: activeRecorder.mimeType || chunks[0].type }));
            } else if (!error.value) {
                error.value = '未采集到录音数据，请重试。';
            }
            phase.value = 'idle';
        };
        activeRecorder.onerror = () => {
            error.value = '录音中断，请检查麦克风后重试。';
            stop();
        };
        input.getAudioTracks().forEach(track => track.addEventListener('ended', stop));
        activeRecorder.start();
        if (audioUrl.value) URL.revokeObjectURL(audioUrl.value);
        audioUrl.value = '';
        phase.value = 'recording';
        draw(analyser);
    } catch (reason) {
        releaseMicrophone();
        recorder = null;
        if (disposed) return;
        phase.value = 'idle';
        const name = reason instanceof Error ? reason.name : '';
        error.value = name === 'NotAllowedError' ? '麦克风权限被拒绝，请允许访问后重试。'
            : name === 'NotFoundError' ? '没有找到可用的麦克风。'
            : name === 'NotReadableError' ? '麦克风无法读取，可能正在被其他程序占用。'
            : '无法开始录音，请检查浏览器和麦克风。';
    }
}

function stop() {
    if (recorder && recorder.state !== 'inactive') {
        phase.value = 'stopping';
        recorder.stop();
    }
    releaseMicrophone();
}

onUnmounted(() => {
    disposed = true;
    stop();
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value);
});
</script>

<template>
    <div class="h5-recorder">
        <p role="status" aria-live="polite">{{ phase === 'recording' ? '正在录音，请对着麦克风说话…' : phase === 'requesting' ? '正在请求麦克风权限…' : phase === 'stopping' ? '正在生成录音…' : audioUrl ? '录音完成，可以回放' : '开始录音后显示实时波形' }}</p>
        <canvas ref="canvas" class="recording-waveform" aria-label="麦克风实时音频波形"></canvas>
        <div class="recording-actions">
            <el-button type="primary" round :disabled="phase !== 'idle'" @click="start">开始录音</el-button>
            <el-button round :disabled="phase !== 'recording'" @click="stop">结束录音</el-button>
        </div>
        <p v-if="error" class="recording-error" role="alert">{{ error }}</p>
        <audio v-if="audioUrl" :src="audioUrl" controls aria-label="回放录音"></audio>
    </div>
</template>

<style scoped>
.h5-recorder { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.h5-recorder p { font-size: 13px; color: var(--color-text-soft); }
.recording-waveform { display: block; width: 100%; height: 100px; border: 1px solid var(--color-border); border-radius: 12px; background: var(--color-panel-muted); }
.recording-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.recording-actions .el-button { margin: 0; }
.h5-recorder .recording-error { color: var(--el-color-danger); }
.h5-recorder audio { width: 100%; min-width: 0; }
</style>

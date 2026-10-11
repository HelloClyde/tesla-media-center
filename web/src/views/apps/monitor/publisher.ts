import { shallowReactive } from 'vue';
import { removeBackgroundApp, updateBackgroundApp } from '@/stores/backgroundApps';
import { AUDIO, VIDEO, MonitorConnection, type RelayPhase } from './relay';
import { CameraFrames, MonitorAudio, captureError, requireCaptureSupport } from './media';

export interface PublishOptions {
  name: string; video: boolean; audio: boolean; width: number; cameraId?: string; microphoneId?: string;
}
export const monitorPublisher = shallowReactive({
  phase: 'idle' as RelayPhase | 'starting', message: '', error: '', stream: null as MediaStream | null,
  viewers: 0, talking: false, video: false, audio: false, name: '',
});
let connection: MonitorConnection | undefined, audio: MonitorAudio | undefined, camera: CameraFrames | undefined;
let generation = 0;
let deviceId: string | undefined;
export function monitorDeviceId() {
  if (deviceId) return deviceId;
  const key = 'tmc:monitor:device:v1';
  let id: string | null = null;
  try { id = sessionStorage.getItem(key); } catch {}
  if (!id || !/^[a-zA-Z0-9_-]{12,64}$/.test(id)) {
    id = typeof crypto.randomUUID === 'function' ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
    try { sessionStorage.setItem(key, id); } catch {}
  }
  return deviceId = id;
}
function publishStatus() {
  if (monitorPublisher.phase === 'idle') { removeBackgroundApp('monitor'); return; }
  updateBackgroundApp({id: 'monitor', name: '车内监控', route: '/apps/monitor', icon: '/icon/MONITOR_LOGO.svg',
    running: monitorPublisher.phase === 'connected',
    detail: monitorPublisher.phase === 'connected' ? `${monitorPublisher.viewers} 人正在观看${monitorPublisher.talking ? ' · 车主正在对讲' : ''}` : monitorPublisher.message});
}

export async function startMonitorPublisher(options: PublishOptions) {
  if (monitorPublisher.phase !== 'idle') return;
  const attempt = ++generation;
  Object.assign(monitorPublisher, {phase: 'starting', message: '等待摄像头和麦克风授权…', error: '', name: options.name});
  publishStatus();
  let acquired: MediaStream | undefined;
  try {
    requireCaptureSupport();
    if (!options.video && !options.audio) throw Error('请至少启用摄像头或麦克风');
    if (!options.name.trim()) throw Error('请填写设备名称');
    audio = new MonitorAudio(samples => connection?.sendMedia(AUDIO, samples));
    const engine = audio;
    await engine.start();
    if (attempt !== generation) return;
    acquired = await navigator.mediaDevices.getUserMedia({
      video: options.video ? {
        width: {ideal: options.width}, height: {ideal: options.width * 9 / 16}, frameRate: {ideal: 10, max: 15},
        ...(options.cameraId ? {deviceId: {exact: options.cameraId}} : {facingMode: 'user'}),
      } : false,
      audio: options.audio ? {echoCancellation: true, noiseSuppression: true, autoGainControl: true,
        ...(options.microphoneId ? {deviceId: {exact: options.microphoneId}} : {})} : false,
    });
    if (attempt !== generation) { acquired.getTracks().forEach(track => track.stop()); return; }
    monitorPublisher.stream = acquired;
    monitorPublisher.video = acquired.getVideoTracks().length > 0;
    monitorPublisher.audio = acquired.getAudioTracks().length > 0;
    engine.setInput(acquired);
    for (const track of acquired.getTracks()) track.addEventListener('ended', () => {
      if (attempt === generation) { stopMonitorPublisher(); monitorPublisher.error = '摄像头或麦克风已断开，请重新启用监控'; }
    }, {once: true});
    connection = new MonitorConnection({role: 'publisher', deviceId: monitorDeviceId(), name: options.name.trim(),
      video: monitorPublisher.video, audio: monitorPublisher.audio}, {
      status(phase, message) {
        if (attempt !== generation) return;
        monitorPublisher.phase = phase; monitorPublisher.message = message;
        if (phase !== 'connected') {
          monitorPublisher.viewers = 0; monitorPublisher.talking = false;
          engine.setCapture(false); engine.resetPlayback(); if (camera) camera.wanted = false;
        }
        publishStatus();
      },
      control(message) {
        if (attempt !== generation || !message.device) return;
        monitorPublisher.viewers = message.device.viewers; monitorPublisher.talking = message.device.talking;
        engine.setCapture(monitorPublisher.audio && message.device.viewers > 0);
        if (camera) camera.wanted = message.device.viewers > 0;
        publishStatus();
      },
      media(kind, samples) { if (kind === AUDIO) engine.play(samples); },
      fatal(message) { if (attempt === generation) { stopMonitorPublisher(); monitorPublisher.error = message; } },
    });
    if (monitorPublisher.video) {
      camera = new CameraFrames(acquired, frame => connection?.sendMedia(VIDEO, frame), options.width);
      await camera.start();
      if (attempt !== generation) return;
    }
    await connection.start();
  } catch (error) {
    acquired?.getTracks().forEach(track => track.stop());
    if (attempt === generation) { stopMonitorPublisher(); monitorPublisher.error = captureError(error); }
  }
}

export function stopMonitorPublisher() {
  ++generation;
  camera?.stop(); camera = undefined;
  connection?.stop(); connection = undefined;
  audio?.stop(); audio = undefined;
  monitorPublisher.stream?.getTracks().forEach(track => track.stop());
  Object.assign(monitorPublisher, {phase: 'idle', stream: null, viewers: 0, talking: false, video: false, audio: false, message: ''});
  removeBackgroundApp('monitor');
}

import { shallowReactive } from 'vue';
import { AUDIO, VIDEO, MonitorConnection, type MonitorDevice, type RelayPhase } from './relay';
import { FrameRenderer, MonitorAudio, captureError, requireCaptureSupport } from './media';

export const monitorViewer = shallowReactive({
  phase: 'idle' as RelayPhase | 'starting', message: '', error: '', device: null as MonitorDevice | null,
  muted: false, talking: false, requestingTalk: false, peerId: '', lastFrameAt: 0,
});
let connection: MonitorConnection | undefined, audio: MonitorAudio | undefined, microphone: MediaStream | undefined;
let generation = 0, talkGeneration = 0, talkTimeout: ReturnType<typeof setTimeout> | undefined;
const renderer = new FrameRenderer(() => { monitorViewer.lastFrameAt = Date.now(); });
export function setMonitorCanvas(canvas: HTMLCanvasElement | null) { renderer.setCanvas(canvas); }

export async function startMonitorViewer(device: MonitorDevice) {
  stopMonitorViewer();
  const attempt = ++generation;
  Object.assign(monitorViewer, {phase: 'starting', device, message: '正在连接车机…', error: '', muted: false});
  try {
    audio = new MonitorAudio(samples => connection?.sendMedia(AUDIO, samples));
    const engine = audio;
    await engine.start();
    if (attempt !== generation) return;
    connection = new MonitorConnection({role: 'viewer', deviceId: device.id}, {
      status(phase, message) {
        if (attempt !== generation) return;
        monitorViewer.phase = phase; monitorViewer.message = message;
        if (phase !== 'connected') { stopMonitorTalk(); engine.resetPlayback(); monitorViewer.lastFrameAt = 0; }
      },
      control(message) {
        if (attempt !== generation) return;
        if (message.peerId) monitorViewer.peerId = message.peerId;
        if (message.device) {
          monitorViewer.device = message.device;
          if (!message.device.online || message.device.talkerId !== monitorViewer.peerId && monitorViewer.talking) {
            stopMonitorTalk(); engine.resetPlayback();
          }
          if (!message.device.online) { monitorViewer.lastFrameAt = 0; renderer.clear(); }
        }
        if (message.type === 'talk_granted') {
          if (!microphone || !monitorViewer.requestingTalk) { connection?.sendControl({type: 'talk_stop'}); return; }
          clearTimeout(talkTimeout); monitorViewer.requestingTalk = false; monitorViewer.talking = true;
          engine.setCapture(true);
        } else if (message.type === 'talk_denied') {
          stopMonitorTalk(); monitorViewer.error = message.message || '对讲暂时不可用';
        }
        if (message.ended) { stopMonitorViewer(); monitorViewer.error = '车机已停止监控'; }
      },
      media(kind, samples) {
        if (kind === VIDEO) renderer.offer(samples);
        else if (kind === AUDIO) engine.play(samples);
      },
      fatal(message) { if (attempt === generation) { stopMonitorViewer(); monitorViewer.error = message; } },
    });
    await connection.start();
  } catch (error) {
    if (attempt === generation) { stopMonitorViewer(); monitorViewer.error = captureError(error); }
  }
}

export async function startMonitorTalk() {
  if (monitorViewer.phase !== 'connected' || !monitorViewer.device?.online || monitorViewer.talking || monitorViewer.requestingTalk) return;
  const attempt = ++talkGeneration;
  monitorViewer.requestingTalk = true; monitorViewer.error = '';
  let acquired: MediaStream | undefined;
  try {
    requireCaptureSupport();
    await audio?.resume();
    acquired = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}, video: false});
    if (attempt !== talkGeneration || monitorViewer.phase !== 'connected') { acquired.getTracks().forEach(track => track.stop()); return; }
    microphone = acquired; audio?.setInput(acquired);
    acquired.getTracks().forEach(track => track.addEventListener('ended', stopMonitorTalk, {once: true}));
    connection?.sendControl({type: 'talk_start'});
    talkTimeout = setTimeout(() => { stopMonitorTalk(); monitorViewer.error = '对讲请求超时，请重试'; }, 5000);
  } catch (error) {
    acquired?.getTracks().forEach(track => track.stop());
    if (attempt === talkGeneration) { stopMonitorTalk(); monitorViewer.error = captureError(error); }
  }
}
export function stopMonitorTalk() {
  ++talkGeneration; clearTimeout(talkTimeout);
  if (monitorViewer.talking || monitorViewer.requestingTalk) connection?.sendControl({type: 'talk_stop'});
  audio?.setCapture(false); audio?.setInput(null);
  microphone?.getTracks().forEach(track => track.stop()); microphone = undefined;
  monitorViewer.talking = monitorViewer.requestingTalk = false;
}
export function muteMonitorViewer() { monitorViewer.muted = !monitorViewer.muted; audio?.setMuted(monitorViewer.muted); }
export function stopMonitorViewer() {
  ++generation; stopMonitorTalk();
  connection?.stop(); connection = undefined;
  audio?.stop(); audio = undefined; renderer.clear();
  Object.assign(monitorViewer, {phase: 'idle', device: null, peerId: '', lastFrameAt: 0, message: ''});
}

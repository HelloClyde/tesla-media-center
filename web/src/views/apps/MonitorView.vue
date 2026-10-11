<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';
import { VideoCamera, Microphone, VideoPlay, VideoPause, Refresh, Mute, Headset, Close } from '@element-plus/icons-vue';
import { monitorPublisher as publisher, startMonitorPublisher, stopMonitorPublisher } from './monitor/publisher';
import { monitorViewer as viewer, startMonitorViewer, stopMonitorViewer, startMonitorTalk, stopMonitorTalk, muteMonitorViewer, setMonitorCanvas } from './monitor/viewer';
import { listMonitorDevices, type MonitorDevice } from './monitor/relay';
defineOptions({name: 'MonitorView'});

const mode = ref<'car' | 'owner'>(publisher.phase !== 'idle' || /tesla/i.test(navigator.userAgent) ? 'car' : 'owner');
const deviceName = ref((() => { try { return localStorage.getItem('tmc:monitor:name') || '我的车辆'; } catch { return '我的车辆'; } })());
const cameraEnabled = ref(true), microphoneEnabled = ref(true), width = ref(640);
const cameras = ref<MediaDeviceInfo[]>([]), microphones = ref<MediaDeviceInfo[]>([]);
const cameraId = ref(''), microphoneId = ref('');
const localVideo = ref<HTMLVideoElement>(), remoteCanvas = ref<HTMLCanvasElement>();
const devices = ref<MonitorDevice[]>([]), loading = ref(false), listError = ref('');
const active = ref(true), now = ref(Date.now());
const publishing = computed(() => publisher.phase !== 'idle');
const watching = computed(() => viewer.phase !== 'idle');
const connected = computed(() => viewer.phase === 'connected' && !!viewer.device?.online);
const pictureLive = computed(() => connected.value && viewer.lastFrameAt > 0 && now.value - viewer.lastFrameAt < 4000);
const otherTalking = computed(() => viewer.device?.talking && viewer.device.talkerId !== viewer.peerId);
let listController: AbortController | undefined, polling: ReturnType<typeof setInterval> | undefined;
let clock: ReturnType<typeof setInterval> | undefined;

async function refreshDevices() {
  if (!active.value || mode.value !== 'owner' || loading.value) return;
  loading.value = true; listController = new AbortController();
  const deadline = setTimeout(() => listController?.abort(), 10000);
  try {
    const result = await listMonitorDevices(listController.signal);
    if (!active.value) return;
    devices.value = result.devices; listError.value = '';
  } catch (error) { if (active.value && (error as Error).name !== 'AbortError') listError.value = (error as Error).message; }
  finally { clearTimeout(deadline); loading.value = false; }
}
async function enumerateDevices() {
  try {
    const all = await navigator.mediaDevices?.enumerateDevices();
    cameras.value = all?.filter(device => device.kind === 'videoinput') || [];
    microphones.value = all?.filter(device => device.kind === 'audioinput') || [];
  } catch { /* Permission guidance is shown by the explicit enable action. */ }
}
async function enable() {
  try { localStorage.setItem('tmc:monitor:name', deviceName.value.trim()); } catch {}
  await startMonitorPublisher({name: deviceName.value, video: cameraEnabled.value, audio: microphoneEnabled.value,
    width: width.value, cameraId: cameraId.value, microphoneId: microphoneId.value});
  await enumerateDevices();
}
function switchMode(value: 'car' | 'owner') {
  if (value === 'car') stopMonitorViewer();
  mode.value = value;
  if (value === 'owner') void refreshDevices();
}
async function view(device: MonitorDevice) {
  const connecting = startMonitorViewer(device);
  await nextTick(); setMonitorCanvas(remoteCanvas.value || null);
  await connecting;
}
watch(() => publisher.stream, async stream => {
  await nextTick();
  if (localVideo.value) { localVideo.value.srcObject = stream; if (stream) void localVideo.value.play().catch(() => {}); }
});
watch(localVideo, video => { if (video && publisher.stream) { video.srcObject = publisher.stream; void video.play().catch(() => {}); } });
watch(remoteCanvas, canvas => setMonitorCanvas(canvas || null));
function activate() {
  active.value = true;
  if (!polling) polling = setInterval(refreshDevices, 6000);
  if (!clock) clock = setInterval(() => { now.value = Date.now(); }, 1000);
  void refreshDevices();
}
function deactivate() {
  active.value = false; clearInterval(polling); polling = undefined; clearInterval(clock); clock = undefined;
  listController?.abort(); stopMonitorViewer(); setMonitorCanvas(null);
}
onMounted(() => { activate(); void enumerateDevices(); });
onActivated(activate);
onDeactivated(deactivate);
onBeforeUnmount(deactivate);
</script>

<template>
  <section class="monitor-app" aria-label="车内监控">
    <header class="monitor-heading">
      <div class="heading-title"><img src="/icon/MONITOR_LOGO.svg" alt=""/><div><h1>监控</h1><p>车内画面，随时相伴</p></div></div>
      <nav class="mode-switch" aria-label="监控端选择"><button :class="{selected:mode==='car'}" :aria-pressed="mode==='car'" @click="switchMode('car')">车机端</button><button :class="{selected:mode==='owner'}" :aria-pressed="mode==='owner'" @click="switchMode('owner')">远程查看</button></nav>
    </header>

    <template v-if="mode === 'car'">
      <div class="monitor-layout">
        <section class="camera-panel">
          <div class="panel-title"><strong>车机实时画面</strong><span class="status-pill" :class="{live:publisher.phase==='connected'}"><i/>{{ publisher.phase === 'connected' ? '监控已开启' : publishing ? '正在连接' : '未开启' }}</span></div>
          <div class="video-stage">
            <video v-if="publisher.video" ref="localVideo" autoplay muted playsinline aria-label="车机摄像头预览"/>
            <div v-else class="stage-placeholder"><VideoCamera v-if="!publishing || cameraEnabled"/><Microphone v-else/><strong>{{ publisher.phase === 'starting' ? '等待设备授权' : publisher.audio ? '仅麦克风监控' : '摄像头尚未开启' }}</strong><p>{{ publisher.audio ? '车主可远程收听和对讲' : '点击启用，允许摄像头和麦克风权限' }}</p></div>
            <div v-if="publisher.talking" class="talking-overlay"><Microphone/>车主正在说话</div>
          </div>
          <div class="camera-details"><span><i :class="{online:publisher.phase==='connected'}"/>{{ publisher.phase==='connected' ? `${publisher.viewers} 人正在观看` : publisher.message || '设备将在启用后显示到远程列表' }}</span><span v-if="publishing">{{ publisher.video ? '视频' : '' }}{{ publisher.video && publisher.audio ? ' + ' : '' }}{{ publisher.audio ? '声音' : '' }}</span></div>
        </section>
        <section class="settings-panel">
          <h2>在车机上启用</h2><p class="panel-description">开启后，车主登录同一个 TMC 即可远程连接。</p>
          <label class="field-label">设备名称<input v-model="deviceName" maxlength="40" :disabled="publishing" placeholder="如：我的 Model Y"/></label>
          <div class="capture-options"><label><input type="checkbox" v-model="cameraEnabled" :disabled="publishing"/><VideoCamera/>摄像头</label><label><input type="checkbox" v-model="microphoneEnabled" :disabled="publishing"/><Microphone/>麦克风</label></div>
          <label v-if="cameraEnabled && cameras.length > 1" class="field-label">摄像头<select v-model="cameraId" :disabled="publishing"><option value="">默认摄像头</option><option v-for="(device,index) in cameras" :key="device.deviceId" :value="device.deviceId">{{ device.label || `摄像头 ${index+1}` }}</option></select></label>
          <label v-if="microphoneEnabled && microphones.length > 1" class="field-label">麦克风<select v-model="microphoneId" :disabled="publishing"><option value="">默认麦克风</option><option v-for="(device,index) in microphones" :key="device.deviceId" :value="device.deviceId">{{ device.label || `麦克风 ${index+1}` }}</option></select></label>
          <fieldset v-if="cameraEnabled" class="quality-options" :disabled="publishing"><legend>画面清晰度</legend><label :class="{chosen:width===640}"><input type="radio" :value="640" v-model="width"/>流畅 <small>360p</small></label><label :class="{chosen:width===1280}"><input type="radio" :value="1280" v-model="width"/>清晰 <small>720p</small></label></fieldset>
          <p v-if="publisher.error" class="error-message" role="alert">{{ publisher.error }}</p>
          <button v-if="!publishing" class="primary-button enable-monitor" :disabled="!cameraEnabled && !microphoneEnabled" @click="enable"><VideoCamera/>启用监控</button><button v-else class="stop-button" @click="stopMonitorPublisher"><VideoPause/>停止监控</button>
          <p class="privacy-note">启用后切换到导航可继续监控。关闭网页或车机休眠会中断；音视频只实时转发，不保存录像。</p>
        </section>
      </div>
    </template>

    <template v-else>
      <div class="monitor-layout owner-layout">
        <section class="camera-panel">
          <div class="panel-title"><strong>{{ viewer.device?.name || '车内实时画面' }}</strong><span v-if="watching" class="status-pill" :class="{live:connected}"><i/>{{ connected ? '实时连接' : '正在连接' }}</span></div>
          <div class="video-stage remote-stage">
            <canvas ref="remoteCanvas" aria-label="远程车内画面" :class="{hidden:!pictureLive}"/>
            <div v-if="!pictureLive" class="stage-placeholder"><VideoCamera v-if="viewer.device?.video !== false"/><Headset v-else/><strong>{{ !watching ? '选择一台在线设备' : !connected ? '等待车机连接' : viewer.device?.video ? '等待实时画面' : '已连接车内麦克风' }}</strong><p>{{ !watching ? '车机启用监控后，会出现在右侧列表中' : connected ? viewer.device?.audio ? '正在实时收听车内声音' : '车机未启用麦克风' : viewer.message || '车机暂时离线，正在等待恢复' }}</p></div>
            <div v-if="viewer.talking" class="talking-overlay"><Microphone/>正在向车内说话</div>
          </div>
          <div v-if="watching" class="viewer-controls"><button @click="muteMonitorViewer" :disabled="!connected"><Mute v-if="viewer.muted"/><Headset v-else/>{{ viewer.muted ? '开启声音' : '静音' }}</button><button class="talk-button" :class="{speaking:viewer.talking}" :disabled="!connected || !!otherTalking" @click="viewer.talking || viewer.requestingTalk ? stopMonitorTalk() : startMonitorTalk()"><Microphone/>{{ viewer.talking ? '结束说话' : viewer.requestingTalk ? '取消对讲' : otherTalking ? '其他车主正在对讲' : '开始说话' }}</button><button class="disconnect" @click="stopMonitorViewer"><Close/>断开</button></div>
          <p v-if="viewer.error" class="error-message viewer-error" role="alert">{{ viewer.error }}</p>
        </section>
        <section class="devices-panel">
          <div class="devices-heading"><h2>在线设备 <small>{{ devices.length }}</small></h2><button aria-label="刷新监控设备" :disabled="loading" @click="refreshDevices"><Refresh :class="{spinning:loading}"/></button></div>
          <p class="panel-description">登录同一个 TMC，选择车机开始查看。</p>
          <p v-if="listError" class="error-message" role="alert">{{ listError }}</p>
          <div v-if="!devices.length" class="empty-devices"><VideoCamera/><strong>暂时没有在线设备</strong><p>请在车机浏览器打开“监控”，点击“启用监控”。</p></div>
          <article v-for="device in devices" :key="device.id" class="device-card" :class="{selected:viewer.device?.id===device.id}"><div class="device-icon"><VideoCamera/></div><div class="device-copy"><strong>{{ device.name }}</strong><span><i/>在线 · {{ device.video ? '摄像头' : '仅声音' }}{{ device.video && device.audio ? '与麦克风' : '' }}</span><small>{{ device.viewers }} 人观看{{ device.talking ? ' · 对讲中' : '' }}</small></div><button class="view-button" :disabled="viewer.device?.id===device.id && watching" @click="view(device)"><VideoPlay/>{{ viewer.device?.id===device.id && watching ? '已连接' : '查看' }}</button></article>
          <p class="privacy-note">查看时收听车内声音；点击“开始说话”后允许麦克风，即可与车内的人对讲。</p>
        </section>
      </div>
    </template>
  </section>
</template>

<style scoped>
.monitor-app{height:100%;overflow:auto;box-sizing:border-box;padding:24px clamp(16px,3vw,38px);background:var(--color-background,#eef4f1);color:var(--color-text,#243d35)}.monitor-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}.heading-title{display:flex;align-items:center;gap:12px}.heading-title img{width:46px;height:46px}.heading-title h1{margin:0;font-size:23px;font-weight:650}.heading-title p{margin:3px 0 0;font-size:12px;color:var(--color-text-soft,#73877f)}.mode-switch{display:flex;padding:4px;border-radius:13px;background:var(--color-surface,#fff);box-shadow:0 1px 5px #173b2510}.mode-switch button{padding:9px 18px;border:0;border-radius:10px;background:none;color:var(--color-text-soft,#6b8077);font-size:13px;cursor:pointer}.mode-switch button.selected{background:#e2f5ed;color:#087e5f;font-weight:600}.monitor-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(270px,320px);align-items:start;gap:20px;max-width:1320px;margin:0 auto}.camera-panel,.settings-panel,.devices-panel{background:var(--color-surface,#fff);border:1px solid var(--color-border,#dfe9e4);border-radius:21px;overflow:hidden;box-shadow:0 5px 20px #254a3310}.panel-title{padding:18px 20px;display:flex;align-items:center;justify-content:space-between;gap:10px}.panel-title strong{font-size:14px}.status-pill{font-size:11px;display:flex;align-items:center;gap:5px;padding:5px 8px;border-radius:20px;background:#edf1ef;color:#6f827a}.status-pill i,.camera-details i,.device-copy i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#99a8a0;margin-right:3px}.status-pill.live{color:#13805d;background:#e5f8ee}.status-pill.live i,.camera-details i.online,.device-copy i{background:#17b17d}.video-stage{position:relative;aspect-ratio:16/9;background:#122b28;display:grid;place-items:center;overflow:hidden}.video-stage video,.video-stage canvas{width:100%;height:100%;position:absolute;inset:0;object-fit:contain}.video-stage canvas{object-fit:contain}.video-stage canvas.hidden{visibility:hidden}.stage-placeholder{position:relative;text-align:center;padding:20px;color:#adc5ba;max-width:330px}.stage-placeholder svg{display:block;width:48px;height:48px;margin:0 auto 17px;color:#6f9f8c;stroke-width:.8}.stage-placeholder strong{font-size:16px;color:#d9e9e1;font-weight:500}.stage-placeholder p{font-size:12px;line-height:1.7;margin:9px 0 0}.talking-overlay{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:7px;white-space:nowrap;padding:9px 15px;background:#e9fff3ee;color:#0c795a;border-radius:25px;font-size:12px;box-shadow:0 3px 15px #0002}.talking-overlay svg{width:16px;height:16px}.camera-details{padding:15px 20px;display:flex;gap:8px;align-items:center;justify-content:space-between;font-size:12px;color:var(--color-text-soft,#6e867c)}.settings-panel,.devices-panel{padding:22px;box-sizing:border-box}.settings-panel h2,.devices-panel h2{font-size:16px;font-weight:600;margin:0}.panel-description{font-size:12px;line-height:1.8;color:var(--color-text-soft,#74877d);margin:7px 0 22px}.field-label{display:flex;flex-direction:column;gap:8px;font-size:12px;font-weight:550;margin:0 0 18px}.field-label input,.field-label select{height:42px;padding:0 12px;box-sizing:border-box;width:100%;background:var(--color-background,#f4f8f6);border:1px solid var(--color-border,#d9e6dd);border-radius:10px;color:inherit;outline:none;font-size:13px}.field-label input:focus,.field-label select:focus{border-color:#15b38a;box-shadow:0 0 0 3px #15b38a15}.capture-options{display:flex;gap:20px;margin:18px 0 22px}.capture-options label{display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer}.capture-options svg{width:16px;height:16px}.capture-options input{accent-color:#0fac80;width:16px;height:16px}.quality-options{display:flex;gap:10px;border:0;padding:0;margin:0 0 23px}.quality-options legend{font-size:12px;margin-bottom:9px}.quality-options label{flex:1;display:flex;justify-content:center;align-items:center;gap:7px;cursor:pointer;border:1px solid var(--color-border,#dce7e1);border-radius:10px;padding:10px 6px;font-size:12px}.quality-options input{position:absolute;opacity:0}.quality-options label:focus-within{outline:2px solid #119d84;outline-offset:2px}.quality-options label.chosen{background:#e8f8f0;border-color:#7bcfae;color:#0f7f5c}.quality-options small{font-size:10px;opacity:.7}.primary-button,.stop-button{display:flex;align-items:center;justify-content:center;gap:8px;cursor:pointer;width:100%;height:46px;border-radius:12px;border:0;background:#119d7d;color:white;font-size:14px;font-weight:550}.primary-button svg,.stop-button svg{width:19px;height:19px}.primary-button:disabled{opacity:.45;cursor:default}.stop-button{background:#fff0ef;color:#a13f36;border:1px solid #ebc1bd}.privacy-note{font-size:11px;line-height:1.9;color:var(--color-text-soft,#81938a);margin:16px 0 0}.error-message{padding:10px 12px;border-radius:10px;background:#fff0ee;color:#a43f35;font-size:12px;line-height:1.7;margin:12px 0}.viewer-error{margin:0 16px 16px}.viewer-controls{display:flex;gap:9px;padding:18px;flex-wrap:wrap}.viewer-controls button{border:1px solid var(--color-border,#dce7e1);background:var(--color-surface,#fff);color:inherit;border-radius:11px;font-size:12px;padding:11px 14px;display:flex;align-items:center;justify-content:center;gap:6px;cursor:pointer}.viewer-controls svg{width:16px;height:16px}.viewer-controls button.talk-button{background:#119d7d;color:white;border-color:#119d7d;flex:1}.viewer-controls button.talk-button.speaking{background:#d44948;border-color:#d44948}.viewer-controls button:disabled{opacity:.45;cursor:default}.viewer-controls .disconnect{color:#74887e}.devices-heading{display:flex;align-items:center;justify-content:space-between}.devices-heading h2 small{background:#edf5f0;color:#6e8f7e;padding:2px 7px;border-radius:7px;font-size:11px;margin-left:6px}.devices-heading button{border:0;background:none;cursor:pointer;color:#7d9789;padding:5px}.devices-heading svg{width:18px;height:18px}.spinning{animation:monitor-spin 1s linear infinite}@keyframes monitor-spin{to{transform:rotate(360deg)}}.empty-devices{padding:28px 5px;text-align:center}.empty-devices svg{width:36px;height:36px;color:#a1baac;margin-bottom:12px}.empty-devices strong{display:block;font-size:13px;font-weight:500}.empty-devices p{font-size:12px;line-height:1.8;color:#81958a;margin:8px 0 0}.device-card{display:flex;align-items:center;gap:10px;border:1px solid var(--color-border,#dfe9e2);border-radius:14px;padding:13px 11px;margin-bottom:10px}.device-card.selected{background:#f0fbf5;border-color:#99d9bd}.device-icon{border-radius:11px;background:#e7f5ed;color:#179775;width:34px;height:38px;display:grid;place-items:center;flex-shrink:0}.device-icon svg{width:20px;height:20px}.device-copy{min-width:0;flex:1}.device-copy strong{font-size:13px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.device-copy span,.device-copy small{display:block;font-size:10px;color:#83958b;margin-top:5px}.device-copy i{width:5px;height:5px}.view-button{display:flex;align-items:center;gap:4px;padding:8px;border:0;background:#e0f3e9;color:#087554;border-radius:9px;cursor:pointer;font-size:11px;flex-shrink:0}.view-button:disabled{opacity:.6;cursor:default}.view-button svg{width:14px;height:14px}@media(max-width:880px){.monitor-layout{grid-template-columns:minmax(0,1fr) 270px;gap:14px}.monitor-app{padding:18px 14px}.settings-panel,.devices-panel{padding:17px}.viewer-controls{padding:14px;gap:6px}.viewer-controls button{padding:10px}}@media(max-width:680px){.monitor-layout{grid-template-columns:1fr}.monitor-heading{margin-bottom:16px;gap:10px}.heading-title img{width:37px;height:37px}.heading-title h1{font-size:20px}.heading-title p{display:none}.mode-switch button{padding:8px 13px}.owner-layout .devices-panel{order:-1}.empty-devices{padding:12px 0}.devices-panel .privacy-note{display:none}.devices-panel .panel-description{margin-bottom:14px}}
</style>

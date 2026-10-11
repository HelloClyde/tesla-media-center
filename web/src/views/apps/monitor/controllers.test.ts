import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
const mocks = vi.hoisted(() => ({connections: [] as any[], audio: [] as any[], cameras: [] as any[], getMedia: vi.fn()}));
vi.mock('./media', () => ({
  requireCaptureSupport: vi.fn(), captureError: (error: Error) => error.message,
  MonitorAudio: class {
    start = vi.fn(async () => {}); resume = vi.fn(async () => {}); stop = vi.fn();
    setInput = vi.fn(); setCapture = vi.fn(); resetPlayback = vi.fn(); play = vi.fn(); setMuted = vi.fn();
    constructor() { mocks.audio.push(this); }
  },
  CameraFrames: class {wanted = false; start = vi.fn(async () => {}); stop = vi.fn(); constructor() { mocks.cameras.push(this); }},
  FrameRenderer: class {setCanvas = vi.fn(); clear = vi.fn(); offer = vi.fn();},
}));
vi.mock('./relay', () => ({AUDIO: 2, VIDEO: 1,
  MonitorConnection: class {
    constructor(public options: any, public hooks: any) { mocks.connections.push(this); }
    start = vi.fn(async () => {
      this.hooks.status('connected', '已连接');
      this.hooks.control({type: 'ready', peerId: 'test-owner', device: device});
    });
    stop = vi.fn(); sendControl = vi.fn(); sendMedia = vi.fn();
  },
}));
import { monitorPublisher, startMonitorPublisher, stopMonitorPublisher } from './publisher';
import { monitorViewer, startMonitorViewer, stopMonitorViewer, startMonitorTalk, stopMonitorTalk } from './viewer';
const device = {id: 'test-vehicle-0001', name: '车辆', video: true, audio: true, online: true,
  viewers: 0, talking: false, talkerId: null, startedAt: 1};
function stream(video = true) {
  const audioTrack = {stop: vi.fn(), addEventListener: vi.fn()}, videoTrack = {stop: vi.fn(), addEventListener: vi.fn()};
  return {getTracks: () => video ? [audioTrack, videoTrack] : [audioTrack], getVideoTracks: () => video ? [videoTrack] : [],
    getAudioTracks: () => [audioTrack]} as unknown as MediaStream;
}
beforeEach(() => {
  mocks.connections.length = mocks.audio.length = mocks.cameras.length = 0; mocks.getMedia.mockReset();
  vi.stubGlobal('navigator', {mediaDevices: {getUserMedia: mocks.getMedia}});
});
afterEach(() => { stopMonitorPublisher(); stopMonitorViewer(); vi.unstubAllGlobals(); });
it('releases a late permission result if capture was cancelled while awaiting the browser', async () => {
  let finish!: (value: MediaStream) => void;
  mocks.getMedia.mockReturnValue(new Promise(resolve => {finish = resolve;}));
  const started = startMonitorPublisher({name: '车辆', video: true, audio: true, width: 640});
  await flushPromises(); expect(monitorPublisher.phase).toBe('starting');
  stopMonitorPublisher(); const acquired = stream(); finish(acquired); await started;
  acquired.getTracks().forEach(track => expect(track.stop).toHaveBeenCalledTimes(1));
  expect(mocks.connections).toHaveLength(0); expect(monitorPublisher.phase).toBe('idle');
  expect(mocks.audio[0].stop).toHaveBeenCalled();
});
it('uploads only with viewers and frees all capture resources on stop', async () => {
  const acquired = stream(); mocks.getMedia.mockResolvedValue(acquired);
  await startMonitorPublisher({name: '车辆', video: true, audio: true, width: 640});
  expect(monitorPublisher.phase).toBe('connected'); expect(mocks.cameras[0].wanted).toBe(false);
  expect(mocks.audio[0].setCapture).toHaveBeenLastCalledWith(false);
  mocks.connections[0].hooks.control({type: 'state', device: {...device, viewers: 1}});
  expect(mocks.cameras[0].wanted).toBe(true); expect(mocks.audio[0].setCapture).toHaveBeenLastCalledWith(true);
  mocks.connections[0].hooks.status('reconnecting', '正在重连');
  expect(mocks.cameras[0].wanted).toBe(false); expect(mocks.audio[0].setCapture).toHaveBeenLastCalledWith(false);
  stopMonitorPublisher();
  acquired.getTracks().forEach(track => expect(track.stop).toHaveBeenCalledTimes(1));
  expect(mocks.connections[0].stop).toHaveBeenCalled(); expect(mocks.cameras[0].stop).toHaveBeenCalled();
});
it('does not request the remote microphone until talk is clicked and only sends after the grant', async () => {
  await startMonitorViewer(device); expect(mocks.getMedia).not.toHaveBeenCalled();
  const acquired = stream(false); mocks.getMedia.mockResolvedValue(acquired);
  await startMonitorTalk(); expect(monitorViewer.requestingTalk).toBe(true); expect(monitorViewer.talking).toBe(false);
  expect(mocks.audio[0].setCapture).not.toHaveBeenCalledWith(true);
  mocks.connections[0].hooks.control({type: 'talk_granted'});
  expect(monitorViewer.talking).toBe(true); expect(mocks.audio[0].setCapture).toHaveBeenLastCalledWith(true);
  stopMonitorTalk(); expect(monitorViewer.talking).toBe(false);
  acquired.getTracks().forEach(track => expect(track.stop).toHaveBeenCalledTimes(1));
  expect(mocks.connections[0].sendControl).toHaveBeenLastCalledWith({type: 'talk_stop'});
});
it('cancels a pending talk permission and rejects a late grant', async () => {
  await startMonitorViewer(device);
  let finish!: (value: MediaStream) => void;
  mocks.getMedia.mockReturnValue(new Promise(resolve => {finish = resolve;}));
  const started = startMonitorTalk(); await flushPromises(); stopMonitorTalk();
  const acquired = stream(false); finish(acquired); await started;
  acquired.getTracks().forEach(track => expect(track.stop).toHaveBeenCalledTimes(1));
  mocks.connections[0].hooks.control({type: 'talk_granted'});
  expect(monitorViewer.talking).toBe(false); expect(mocks.audio[0].setCapture).not.toHaveBeenCalledWith(true);
});

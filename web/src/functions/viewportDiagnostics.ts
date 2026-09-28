import { ref } from 'vue';
export const layoutRecording = ref((() => { try { return localStorage.getItem('tmc:layout-recording') === '1'; } catch { return false; } })());
export interface LayoutSample {
  time: string; reason: string; viewport: string; visual: string; scroll: string;
  player: string; footer: string; shell: string; page: string; change: string; media: string;
}
export const layoutSamples = ref<LayoutSample[]>([]);
let stop: (() => void) | undefined;
let last: number[] | undefined;
const round = (n: number) => Math.round(n * 10) / 10;
export function captureLayout(reason = '布局变化', force = false) {
  if (!layoutRecording.value) return;
  const vv = window.visualViewport;
  const audio = document.querySelector<HTMLAudioElement>('[data-qqmusic-player]');
  const panel = document.querySelector('.listening')?.getBoundingClientRect();
  const footer = document.querySelector('.listening > footer')?.getBoundingClientRect();
  const shell = document.querySelector('.app-shell')?.getBoundingClientRect();
  const page = document.querySelector('.main-view')?.getBoundingClientRect();
  const scroll = document.querySelector('.main-view')?.scrollTop || 0;
  const values = [innerWidth, innerHeight, vv?.width || 0, vv?.height || 0, vv?.offsetTop || 0,
    window.scrollY, scroll, panel?.top ?? -1, panel?.height ?? -1, footer?.top ?? -1, footer?.height ?? -1,
    shell?.top ?? -1, shell?.height ?? -1, page?.top ?? -1, page?.height ?? -1].map(round);
  if (!force && last && values.every((v, i) => v === last![i])) return;
  const changes: string[] = [];
  if (last) {
    if (values[0] !== last[0] || values[1] !== last[1]) changes.push('布局视口 resize');
    if (values.slice(2, 5).some((v, i) => v !== last![i + 2])) changes.push('可视视口变化');
    if (values[5] !== last[5] || values[6] !== last[6]) changes.push('页面/容器滚动');
    if (values.slice(7, 11).some((v, i) => v !== last![i + 7])) changes.push('播放器布局变化');
    if (values.slice(11).some((v, i) => v !== last![i + 11])) changes.push('应用外框/当前页面变化');
  }
  last = values;
  layoutSamples.value = [{ time: new Date().toLocaleTimeString() + '.' + String(Date.now() % 1000).padStart(3, '0'), reason,
    viewport: `${values[0]} × ${values[1]}`,
    visual: vv ? `${values[2]} × ${values[3]} / top ${values[4]}` : '不支持',
    scroll: `${values[5]} / ${values[6]}`,
    player: panel ? `top ${values[7]} / h ${values[8]}` : '未打开',
    footer: footer ? `top ${values[9]} / h ${values[10]}` : '未打开',
    shell: shell ? `top ${values[11]} / h ${values[12]}` : '未打开',
    page: page ? `top ${values[13]} / h ${values[14]}` : '未打开',
    media: audio ? `paused=${audio.paused} / ended=${audio.ended} / ready=${audio.readyState} / network=${audio.networkState} / src=${audio.getAttribute('src') ? '有' : '无'}` : '无主音频节点',
    change: changes.join('；') || '尺寸未变',
  }, ...layoutSamples.value].slice(0, 80);
}
export function clearLayoutSamples() { layoutSamples.value = []; last = undefined; captureLayout('开始记录', true); }
export function startLayoutDiagnostics() {
  stop?.();
  const events = ['pause', 'play', 'playing', 'ended', 'emptied', 'abort', 'loadstart', 'loadedmetadata', 'waiting', 'stalled', 'error'];
  const media = (event: Event) => {
    if (event.target instanceof HTMLAudioElement && event.target.matches('[data-qqmusic-player]')) captureLayout('audio：' + event.type, true);
  };
  events.forEach(event => document.addEventListener(event, media, true));
  const resize = () => captureLayout('resize');
  const scroll = () => captureLayout('scroll');
  window.addEventListener('resize', resize);
  window.addEventListener('scroll', scroll, true);
  window.visualViewport?.addEventListener('resize', resize);
  window.visualViewport?.addEventListener('scroll', scroll);
  const timer = setInterval(() => { if (!document.hidden) captureLayout(); }, 150);
  stop = () => {
    events.forEach(event => document.removeEventListener(event, media, true));
    clearInterval(timer); window.removeEventListener('resize', resize); window.removeEventListener('scroll', scroll, true);
    window.visualViewport?.removeEventListener('resize', resize); window.visualViewport?.removeEventListener('scroll', scroll);
  };
  return stop;
}
export function setLayoutRecording(enabled: boolean) {
  layoutRecording.value = enabled;
  try { localStorage.setItem('tmc:layout-recording', enabled ? '1' : '0'); } catch { /* Session still works. */ }
  if (enabled) clearLayoutSamples();
}

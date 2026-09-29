import axios from 'axios';
import { parseSearchPlaces, type Place } from './amapSearch';

export async function searchWebPlaces(keywords: string, signal: AbortSignal, center?: [number, number]): Promise<Place[]> {
  const config = await axios.get('/api/config', { signal, timeout: 10000 });
  if (config.data?.status !== 'ok') throw new Error('读取地图配置失败，请确认 TMC 已登录');
  const key = config.data.data?.amap_key?.trim();
  if (!key) throw new Error('请先在调试页设置高德 Web JS API Key');
  if (signal.aborted) throw new DOMException('查询已取消', 'AbortError');
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe');
    frame.hidden = true;
    frame.title = '高德地点搜索服务';
    let settled = false;
    let timer: ReturnType<typeof setTimeout>;
    const deadline = (ms: number, message: string) => {
      clearTimeout(timer);
      timer = setTimeout(() => finish(new Error(message)), ms);
    };
    const finish = (error?: Error, places: Place[] = []) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      window.removeEventListener('message', receive);
      signal.removeEventListener('abort', abort);
      frame.remove();
      if (error) reject(error); else resolve(places);
    };
    const abort = () => finish(new DOMException('查询已取消', 'AbortError'));
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.contentWindow) return;
      if (event.data?.type === 'tmc-search-ready') {
        try {
          // Vue refs wrap coordinate arrays in a Proxy, which postMessage cannot clone.
          const point = center?.length === 2 && center.every(Number.isFinite)
            && Math.abs(center[0]) <= 180 && Math.abs(center[1]) <= 85
            ? [center[0], center[1]] : undefined;
          frame.contentWindow?.postMessage({ type: 'tmc-search', key, keywords, center: point,
            securityCode: config.data.data?.amap_security_js_code || '' }, window.location.origin);
        } catch {
          finish(new Error('搜索请求发送失败，请重新搜索'));
        }
      } else if (event.data?.type === 'tmc-search-stage') {
        if (event.data.stage === 'sdk-loading') deadline(30000, '高德搜索 SDK 加载超时，请检查车机到高德服务的网络连接');
        if (event.data.stage === 'query') deadline(12000, '高德地点查询超时，搜索服务未及时返回结果');
      } else if (event.data?.type === 'tmc-search-result') {
        try { finish(undefined, parseSearchPlaces(event.data)); }
        catch (error) { finish(error instanceof Error ? error : new Error('搜索结果解析失败')); }
      }
    };
    deadline(15000, '搜索页面加载超时，请刷新 TMC 后重试');
    window.addEventListener('message', receive);
    signal.addEventListener('abort', abort, { once: true });
    frame.onerror = () => finish(new Error('搜索服务加载失败'));
    frame.src = `${import.meta.env.BASE_URL}amap-search.html?v=4`;
    document.body.appendChild(frame);
  });
}

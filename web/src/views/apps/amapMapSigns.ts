import { cumulative, type AppRoute, type Point } from './amapNavigation';
import type { SpeedLimitCamera } from './amapSpeedLimit';
import { groundOffset, groundPoint } from './teslaMapCoordinates';

export type TrafficLightColor = 'red' | 'yellow' | 'green';
export type RouteCameraSign = { point: Point; displayPoint: Point; at: number; type: SpeedLimitCamera['type']; limit: number; direction: Point };
export type MapSign = { key: string; canvas: HTMLCanvasElement; width: number; height: number; anchorX: number };

/** Place native routeguide camera distances on the same App route geometry. */
export function routeCameraSigns(route: AppRoute | undefined, cameras = route?.speedCameras): RouteCameraSign[] {
  if (!route || route.path.length < 2 || !Array.isArray(cameras)) return [];
  const lengths = cumulative(route), total = lengths[lengths.length - 1], seen = new Set<string>();
  const signs: RouteCameraSign[] = [];
  for (const camera of cameras) {
    if (!camera || ![7, 25, 26, 27].includes(camera.type) || !Number.isFinite(camera.at)
        || camera.at < 0 || camera.at > total || !Array.isArray(camera.speed)) continue;
    const speeds = camera.speed.filter(speed => Number.isInteger(speed) && speed >= 5 && speed <= 160);
    if (!speeds.length) continue;
    const limit = Math.max(...speeds), key = `${Math.round(camera.at)}:${camera.type}:${limit}`;
    if (seen.has(key)) continue;
    seen.add(key);
    for (let i = 1; i < lengths.length; i++) {
      if (lengths[i] < camera.at || lengths[i] <= lengths[i - 1]) continue;
      const fraction = Math.max(0, Math.min(1, (camera.at - lengths[i - 1]) / (lengths[i] - lengths[i - 1])));
      const before = route.path[i - 1], after = route.path[i];
      const point: Point = [before[0] + (after[0] - before[0]) * fraction,
        before[1] + (after[1] - before[1]) * fraction];
      const direction = groundOffset(after, before), length = Math.hypot(...direction);
      // The NCP coordinate is on the route centerline. The APK renders the
      // camera as a roadside sign; offset it to the travel direction's right.
      const displayPoint = length > 0 ? groundPoint(point, -direction[1] / length * 18,
        direction[0] / length * 18) : point;
      signs.push({ point, displayPoint, at: camera.at, type: camera.type, limit, direction });
      break;
    }
  }
  return signs;
}

const signs = new Map<string, MapSign>(), urls = new Map<string, string>();
let nativeLight: HTMLImageElement | undefined;
let nativeCamera: HTMLImageElement | undefined;
/** The cropped vertical signal is from the APK's map icon atlas (icons_10000). */
export const trafficLightAssetReady: Promise<boolean> = typeof Image === 'undefined' ? Promise.resolve(false) : new Promise(resolve => {
  const image = new Image();
  image.onload = () => {
    nativeLight = image;
    for (const key of signs.keys()) if (key.startsWith('light:')) signs.delete(key);
    for (const key of urls.keys()) if (key.startsWith('light:')) urls.delete(key);
    resolve(true);
  };
  image.onerror = () => resolve(false);
  image.src = '/amap/icons/traffic-light-map.png';
});
/** CCTV silhouette extracted from the APK's icons_10001 ETC2 atlas. */
export const cameraAssetReady: Promise<boolean> = typeof Image === 'undefined' ? Promise.resolve(false) : new Promise(resolve => {
  const image = new Image();
  image.onload = () => {
    nativeCamera = image;
    for (const key of signs.keys()) if (key.startsWith('camera:')) signs.delete(key);
    for (const key of urls.keys()) if (key.startsWith('camera:')) urls.delete(key);
    resolve(true);
  };
  image.onerror = () => resolve(false);
  image.src = '/amap/icons/camera-map-glyph.png';
});
function canvas(key: string, width: number, height: number, draw: (ctx: CanvasRenderingContext2D) => void,
                cache = true, anchorX = width / 2): MapSign {
  const cached = cache && signs.get(key);
  if (cached) return cached;
  const element = document.createElement('canvas');
  element.width = width * 2; element.height = height * 2;
  const ctx = element.getContext('2d');
  if (!ctx) throw new Error('Map sign canvas unavailable');
  ctx.scale(2, 2);
  draw(ctx);
  const sign = { key, canvas: element, width, height, anchorX };
  if (cache) signs.set(key, sign);
  return sign;
}
export function mapSignUrl(sign: MapSign): string {
  let url = urls.get(sign.key);
  if (!url) {
    url = sign.canvas.toDataURL('image/png');
    if (!sign.key.startsWith('light:count:')) urls.set(sign.key, url);
  }
  return url;
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

/** Use the APK map sprite; only the optional phase countdown is drawn by TMC. */
export function trafficLightSign(color?: TrafficLightColor, seconds?: number): MapSign {
  const countdown = color && Number.isInteger(seconds) && seconds! >= 1 && seconds! <= 300 ? seconds : undefined;
  const width = countdown ? 58 : 24;
  return canvas(countdown ? `light:count:${color}:${countdown}` : `light:${color ?? 'unknown'}`, width, 38, ctx => {
    if (nativeLight) ctx.drawImage(nativeLight, 5, 1, 14, 35);
    else {
      // The map can start before its tiny local image finishes loading.
      ctx.fillStyle = '#36485b'; ctx.strokeStyle = '#edf5f3'; ctx.lineWidth = 1.1;
      roundedRect(ctx, 5, 1, 14, 35, 7); ctx.fill(); ctx.stroke();
      for (const [y, fill] of [[8, '#ef4750'], [18, '#ffca42'], [28, '#42cf73']] as const) {
        ctx.fillStyle = fill; ctx.beginPath(); ctx.arc(12, y, 3.3, 0, Math.PI * 2); ctx.fill();
      }
    }
    if (countdown) {
      ctx.fillStyle = '#14262d'; ctx.strokeStyle = color === 'green' ? '#65df9c' : color === 'yellow' ? '#f3d16b' : '#f17a70';
      ctx.lineWidth = 1.2; roundedRect(ctx, 22, 10, 34, 18, 6); ctx.fill(); ctx.stroke();
      ctx.fillStyle = color === 'green' ? '#77edb0' : color === 'yellow' ? '#ffe18a' : '#ff958a';
      ctx.textAlign = 'center'; ctx.font = `bold ${countdown >= 100 ? 11 : 13}px sans-serif`;
      ctx.fillText(String(countdown), 39, 23.5);
    }
  }, !countdown, 12);
}

/** The map uses the native CCTV pictogram; numeric limits remain in the HUD. */
export function cameraSign(type: SpeedLimitCamera['type'], limit: number): MapSign {
  return canvas(`camera:${type}:${limit}`, 36, 36, ctx => {
    ctx.shadowColor = '#18272d55'; ctx.shadowBlur = 2; ctx.shadowOffsetY = 1;
    ctx.fillStyle = '#fff'; ctx.strokeStyle = '#f03439'; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(18, 18, 15, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    if (nativeCamera) ctx.drawImage(nativeCamera, 7, 10, 22, 17);
    else {
      ctx.fillStyle = '#1e2729';
      ctx.beginPath(); ctx.moveTo(8, 15); ctx.lineTo(26, 12); ctx.lineTo(24, 20);
      ctx.lineTo(12, 21); ctx.lineTo(10, 25); ctx.lineTo(7, 25); ctx.lineTo(9, 20); ctx.closePath(); ctx.fill();
    }
  });
}

import SparkMD5 from 'spark-md5';
import CryptoJS from 'crypto-js';

// These values and the signing order come from the site's public H5 player script.
const SIGNING_SUFFIX = 'yKBm0pKLdVcGbnu4XGon13TsyBdEsjj3WVAzszpoqjn3BNmovLgzvcRTxD1Wey7QQ10kcov0b8e9oBi7jAUR';
const AES_KEY = 'j3Qpq3BWs6qUCctm';
const AES_IV = 'b2mdEEYbW1qprFsg';
const DEVICE_KEY = 'tmc.wqzb.device.v1';

interface PlayResponse { code: number; message?: string; data?: { play_url?: string; expire_ts?: number } }

function deviceId(): string {
  try {
    let value = localStorage.getItem(DEVICE_KEY);
    if (!value) {
      value = crypto.randomUUID ? crypto.randomUUID() : `tmc-${Date.now()}`;
      localStorage.setItem(DEVICE_KEY, value);
    }
    return value;
  } catch { return 'tmc-web'; }
}

function decrypt(ciphertext: string): PlayResponse {
  const content = CryptoJS.lib.CipherParams.create({ ciphertext: CryptoJS.enc.Base64.parse(ciphertext) });
  const plain = CryptoJS.AES.decrypt(content, CryptoJS.enc.Latin1.parse(AES_KEY), {
    iv: CryptoJS.enc.Latin1.parse(AES_IV), mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7,
  });
  return JSON.parse(plain.toString(CryptoJS.enc.Utf8)) as PlayResponse;
}

export async function getWqzbStream(roomId: number, signal?: AbortSignal): Promise<string> {
  if (!Number.isSafeInteger(roomId) || roomId <= 0) throw new Error('直播间编号无效');
  const params: Record<string, string> = { room_id: String(roomId), code_id: 'bqzm', time: String(Math.floor(Date.now() / 1000)) };
  params.signature = SparkMD5.hash(Object.keys(params).sort().map(key => key + params[key]).join('') + SIGNING_SUFFIX);
  const response = await fetch('https://openim-php-api.qaek4a2wjx6bt.cc/v230/play/url', {
    method: 'POST', signal,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'platform': 'wqzb', 'device': '4', 'version': '1.0.0', 'api-version': '8', 'imei': deviceId(),
    },
    body: new URLSearchParams(params),
  });
  if (!response.ok) throw new Error(`获取直播源失败 (${response.status})`);
  const raw = await response.json();
  const result = typeof raw === 'string' ? decrypt(raw) : raw as PlayResponse;
  if (result.code !== 200 || !result.data?.play_url) throw new Error(result.message || '直播源暂不可用');
  const url = new URL(result.data.play_url);
  if (url.protocol !== 'https:') throw new Error('直播地址不安全');
  return url.toString();
}

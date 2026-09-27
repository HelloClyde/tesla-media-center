// Serialize snapshots per game across component mounts; a failed upload retains a local backup.
const uploads = new Map<string, Promise<void>>();
const url = (key: string) => '/api/gam4980/saves/' + encodeURIComponent(key.replace('tmc:gam4980:save:', ''));

function localSave(key: string): Uint8Array | undefined {
  const raw = localStorage.getItem(key);
  if (!raw) return;
  const bytes = Uint8Array.from(atob(raw), c => c.charCodeAt(0));
  if (bytes.length !== 0x14000) throw Error('浏览器备份存档损坏，请导入备份');
  return bytes;
}

export function uploadSave(key: string, data: Uint8Array): Promise<void> {
  const bytes = new Uint8Array(data);
  let raw = ''; for (const byte of bytes) raw += String.fromCharCode(byte);
  try { localStorage.setItem(key, btoa(raw)); localStorage.setItem(key + ':pending', '1'); } catch { /* Server remains primary. */ }
  const previous = uploads.get(key) || Promise.resolve();
  const next = previous.catch(() => {}).then(async () => {
    const response = await fetch(url(key), { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: bytes });
    if (!response.ok) throw Error('服务端存档同步失败，请检查网络后暂停重试或导出存档');
    const result = await response.json();
    if (result.status !== 'ok') throw Error('存档未同步，请重新登录后重试或导出存档');
    if (uploads.get(key) === next) {
      try { localStorage.removeItem(key + ':pending'); } catch { /* Optional backup. */ }
    }
  });
  uploads.set(key, next);
  void next.finally(() => { if (uploads.get(key) === next) uploads.delete(key); }).catch(() => {});
  return next;
}

export async function readSave(key: string): Promise<Uint8Array | undefined> {
  await uploads.get(key)?.catch(() => {});
  let backup: Uint8Array | undefined, pending = false;
  try { backup = localSave(key); pending = localStorage.getItem(key + ':pending') === '1'; } catch { /* Read server first. */ }
  if (pending && backup) { await uploadSave(key, backup); return backup; }
  const response = await fetch(url(key), { cache: 'no-store' });
  if (response.status === 404) {
    if (backup) await uploadSave(key, backup); // Migrate old browser-only saves once.
    return backup;
  }
  if (!response.ok) throw Error('无法读取服务端存档，请检查网络后重试');
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length !== 0x14000) throw Error('服务端存档无效或登录已失效，请重新登录后重试');
  return bytes;
}

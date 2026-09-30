<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
const emit = defineEmits<{ changed: [] }>();
const visible = ref(false), loggedIn = ref(false), busy = ref(false);
const qr = ref(''), message = ref('');
let generation = 0, disposed = false, timer: ReturnType<typeof setTimeout> | undefined;
let controller: AbortController | undefined;
async function api(path = '', method = 'GET', signal?: AbortSignal) {
  const response = await fetch('/api/douyin/auth' + path, { method, credentials: 'same-origin',
    headers: { 'X-Requested-With': 'Douyin' }, signal });
  const result = await response.json();
  if (!response.ok || result.status !== 'ok') throw new Error(result.message || '登录请求失败，请重试');
  return result.data;
}
function stop() { ++generation; clearTimeout(timer); controller?.abort(); busy.value = false; }
function close() {
  stop(); visible.value = false; qr.value = '';
  void api('/qrcode', 'DELETE').catch(() => {});
}
async function poll(ticket: number) {
  try {
    const data = await api('/qrcode', 'GET', controller?.signal);
    if (disposed || ticket !== generation) return;
    if (data.state === 'confirmed') {
      loggedIn.value = true; close(); emit('changed'); return;
    }
    qr.value = data.qrcode || ''; message.value = data.message || '';
    busy.value = data.state === 'loading';
    if (['loading', 'waiting'].includes(data.state)) timer = setTimeout(() => poll(ticket), 2000);
  } catch (error: any) {
    if (!disposed && ticket === generation) { busy.value = false; qr.value = ''; message.value = error.message; }
  }
}
async function generate() {
  stop(); visible.value = true; busy.value = true; qr.value = ''; message.value = '正在打开官方登录页面…';
  controller = new AbortController(); const ticket = generation;
  try {
    const data = await api('/qrcode', 'POST', controller.signal);
    if (disposed || ticket !== generation) return;
    if (data.state === 'confirmed') { loggedIn.value = true; close(); emit('changed'); return; }
    await poll(ticket);
  } catch (error: any) {
    if (!disposed && ticket === generation) { busy.value = false; message.value = error.message; }
  }
}
async function logout() {
  stop(); busy.value = true; controller = new AbortController(); const ticket = generation;
  try {
    await api('', 'DELETE', controller.signal);
    if (!disposed && ticket === generation) { loggedIn.value = false; close(); emit('changed'); }
  } catch (error: any) { if (!disposed && ticket === generation) message.value = error.message; }
  finally { if (!disposed && ticket === generation) busy.value = false; }
}
onMounted(async () => {
  controller = new AbortController(); const ticket = generation;
  try { const data = await api('', 'GET', controller.signal); if (!disposed && ticket === generation) loggedIn.value = data.loggedIn; }
  catch { /* Public browsing remains available. */ }
});
onBeforeUnmount(() => { disposed = true; stop(); void api('/qrcode', 'DELETE').catch(() => {}); });
</script>
<template>
  <button class="account-trigger" @click="loggedIn ? (visible = true, message = '') : generate()">{{ loggedIn ? '已登录抖音' : '登录抖音' }}</button>
  <Teleport to="body">
    <div v-if="visible" class="dy-account-backdrop" @click.self="close" @keydown.esc="close">
      <section role="dialog" aria-modal="true" aria-labelledby="dy-login-title" class="dy-account-dialog">
        <header><h2 id="dy-login-title">{{ loggedIn ? '抖音账号' : '扫码登录抖音' }}</h2><button aria-label="关闭登录" @click="close">✕</button></header>
        <template v-if="loggedIn"><p>已连接抖音账号，浏览和视频解析将使用此账号。</p><button :disabled="busy" @click="logout">退出当前连接</button></template>
        <template v-else>
          <p>打开手机抖音 App，使用扫一扫，并在手机上确认登录。</p>
          <div class="qr-box"><img v-if="qr" :src="qr" alt="抖音登录二维码"/><span v-else>{{ busy ? '正在生成二维码…' : '二维码暂不可用' }}</span></div>
          <button :disabled="busy" @click="generate">刷新二维码</button>
        </template>
        <p role="status">{{ message }}</p>
        <p class="fine-print">登录凭据仅临时保存在本媒体中心服务端，当前浏览器刷新后可继续使用；退出连接、服务重启或 24 小时后清除。授权与账号验证请在抖音官方页面或 App 完成。</p>
      </section>
    </div>
  </Teleport>
</template>
<style scoped>
.account-trigger{white-space:nowrap;border:1px solid #fe2c5566;background:#fe2c5518;color:#fff;border-radius:12px;padding:10px 16px;min-height:44px;cursor:pointer}.dy-account-backdrop{position:fixed;inset:0;z-index:3000;background:#000b;display:flex;align-items:center;justify-content:center;padding:20px}.dy-account-dialog{box-sizing:border-box;width:420px;max-width:100%;max-height:90vh;overflow:auto;background:#1b1b24;color:#f3f3f5;border:1px solid #ffffff20;border-radius:20px;padding:24px;font:14px/1.7 sans-serif}.dy-account-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px}.dy-account-dialog h2{font-size:20px;margin:0}.dy-account-dialog button{min-height:44px;border:1px solid #ffffff20;background:#292934;color:#fff;padding:8px 16px;border-radius:10px;cursor:pointer}.dy-account-dialog button:disabled{opacity:.45}.dy-account-dialog button:focus-visible{outline:2px solid #25f4ee}.qr-box{width:220px;height:220px;display:grid;place-items:center;margin:20px auto;background:#fff;color:#666;border-radius:12px;padding:12px}.qr-box img{width:100%;height:100%;object-fit:contain}.fine-print{color:#9999a8;font-size:12px}
</style>

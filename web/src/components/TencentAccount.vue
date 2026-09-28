<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
const visible = ref(false), loggedIn = ref(false), nickname = ref('');
const qr = ref(''), message = ref(''), busy = ref(false);
let generation = 0, disposed = false, timer: ReturnType<typeof setTimeout> | undefined;
let controller: AbortController | undefined;
async function request(path = '', method = 'GET') {
  const response = await fetch('/api/tencent-video/auth' + path, { method,
    credentials: 'same-origin', headers: { 'X-Requested-With': 'TencentVideo' }, signal: controller?.signal });
  const result = await response.json();
  if (!response.ok || result.status !== 'ok') throw new Error(result.message || '登录状态读取失败');
  return result.data;
}
function stop() { ++generation; clearTimeout(timer); controller?.abort(); busy.value = false; }
function close() { stop(); visible.value = false; qr.value = ''; }
async function generate() {
  stop(); visible.value = true; qr.value = ''; message.value = ''; busy.value = true;
  controller = new AbortController();
  const ticket = generation;
  try {
    const data = await request('/qrcode', 'POST');
    if (disposed || ticket !== generation) return;
    qr.value = data.qrcode; message.value = '请使用腾讯视频 App 扫码';
    timer = setTimeout(() => poll(ticket), 2500);
  } catch (error: any) { if (!disposed && ticket === generation) message.value = error.message; }
  finally { if (!disposed && ticket === generation) busy.value = false; }
}
async function poll(ticket: number) {
  try {
    const data = await request('/qrcode/poll', 'POST');
    if (disposed || ticket !== generation) return;
    if (data.state === 'confirmed') {
      loggedIn.value = true; nickname.value = data.nickname; close(); return;
    }
    message.value = data.state === 'scanned' ? '已扫码，请在手机上确认授权' : '请使用腾讯视频 App 扫码';
    timer = setTimeout(() => poll(ticket), 2500);
  } catch (error: any) {
    if (!disposed && ticket === generation) { message.value = error.message; qr.value = ''; }
  }
}
async function logout() {
  stop(); controller = new AbortController(); const ticket = generation;
  try {
    await request('', 'DELETE');
    if (!disposed && ticket === generation) { loggedIn.value = false; nickname.value = ''; close(); }
  } catch (error: any) { if (!disposed && ticket === generation) { visible.value = true; message.value = error.message; } }
}
onMounted(async () => {
  controller = new AbortController(); const ticket = generation;
  try { const data = await request(); if (!disposed && ticket === generation) { loggedIn.value = data.loggedIn; nickname.value = data.nickname; } }
  catch { /* Login is optional for public videos. */ }
});
onBeforeUnmount(() => { disposed = true; stop(); });
</script>

<template>
  <button class="account-trigger" @click="loggedIn ? (visible = true) : generate()">{{ loggedIn ? nickname : '登录账号' }}</button>
  <div v-if="visible" class="account-backdrop" @click.self="close" @keydown.esc="close">
    <section role="dialog" aria-modal="true" aria-labelledby="tencent-account-title" class="account-dialog">
      <header><h2 id="tencent-account-title">{{ loggedIn ? '腾讯视频账号' : '扫码登录腾讯视频' }}</h2><button @click="close" aria-label="关闭登录">✕</button></header>
      <template v-if="loggedIn"><p>{{ nickname }}</p><p>已连接账号。会员权益及视频可播放性以腾讯接口返回为准。</p><button @click="logout">退出当前连接</button></template>
      <template v-else>
        <p>支持微信、QQ 账号：先在腾讯视频 App 登录对应的会员账号，再使用 App 扫码。</p>
        <div class="qr-box"><img v-if="qr" :src="qr" alt="腾讯视频 App 登录二维码"/><span v-else>{{ busy ? '正在生成二维码…' : '请刷新二维码' }}</span></div>
        <p role="status">{{ message }}</p><button :disabled="busy" @click="generate">刷新二维码</button>
        <p class="fine-print">授权将把登录凭据临时保存在本媒体中心服务端，退出连接或服务重启后清除。登录不保证会员加密视频可播放，当前播放器仍使用端上软解码。</p>
        <p class="fine-print">授权前请阅读腾讯视频的 <a href="https://rule.tencent.com/rule/preview/399ab3d0-4989-4f34-9d7b-99c579b4cbdf" target="_blank" rel="noopener noreferrer">用户服务协议</a> 和 <a href="https://privacy.qq.com/document/preview/3fab9c7fc1424ebda42c3ce488322c8a" target="_blank" rel="noopener noreferrer">隐私保护指引</a>，在官方 App 内确认。</p>
      </template>
    </section>
  </div>
</template>

<style scoped>
button{font:inherit;cursor:pointer;min-height:44px;padding:10px 16px;border-radius:22px;border:1px solid var(--color-border);background:var(--color-surface);color:var(--color-text)}.account-trigger{white-space:nowrap;max-width:160px;overflow:hidden;text-overflow:ellipsis}.account-backdrop{position:fixed;inset:0;background:#07172399;z-index:1000;display:grid;place-items:center;padding:18px}.account-dialog{width:min(420px,100%);max-height:85vh;overflow:auto;background:var(--color-surface,#fff);color:var(--color-text);border-radius:20px;padding:24px;box-sizing:border-box}.account-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px}.account-dialog h2{font-size:20px;margin:0}.account-dialog p{font-size:14px;line-height:1.7}.qr-box{width:220px;height:220px;margin:16px auto;display:grid;place-items:center;background:white;color:#555;border-radius:12px}.qr-box img{width:100%;height:100%;object-fit:contain}.account-dialog .fine-print{font-size:12px;color:var(--color-text-secondary,#75818a)}a{color:#087d51}
</style>

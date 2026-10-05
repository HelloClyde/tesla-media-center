<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import axios from 'axios';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; loggedIn: [] }>();
const password = ref(''), visible = ref(false), busy = ref(false), error = ref('');
const input = ref<HTMLInputElement>();
watch(() => props.open, async open => {
  if (!open) { password.value = ''; error.value = ''; visible.value = false; return; }
  await nextTick(); input.value?.focus();
});
async function submit() {
  if (busy.value) return;
  if (!password.value) { error.value = '请输入 TMC 访问密码'; return; }
  busy.value = true; error.value = '';
  try {
    const response = await axios.post('/api/login', { password: password.value }, { timeout: 15000 });
    if (response.data.status !== 'ok') { error.value = 'TMC 访问密码不正确，请重试'; return; }
    password.value = '';
    emit('loggedIn');
  } catch (cause) {
    const status = axios.isAxiosError(cause) ? cause.response?.status : undefined;
    error.value = status === 401 ? 'TMC 访问密码不正确，请重试' : status
      ? `TMC 登录服务返回 HTTP ${status}，请稍后重试` : '暂时无法连接 TMC 登录服务，请稍后重试';
  } finally { busy.value = false; }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="tmc-login-backdrop" @keydown.esc="emit('close')">
      <section class="tmc-login-dialog" role="dialog" aria-modal="true" aria-labelledby="tmc-login-title">
        <button class="tmc-login-close" type="button" aria-label="关闭登录" @click="emit('close')">×</button>
        <span class="tmc-login-mark">↗</span>
        <h2 id="tmc-login-title">登录 TMC 后继续导航</h2>
        <p>TMC 访问会话已失效。这里使用的是 TMC 访问密码，不是高德账号；登录后将继续加载地图。</p>
        <form @submit.prevent="submit">
          <label for="tmc-login-password">访问密码</label>
          <div class="tmc-login-field">
            <input id="tmc-login-password" ref="input" v-model="password" :type="visible ? 'text' : 'password'"
              autocomplete="current-password" placeholder="输入 TMC 密码" :aria-invalid="!!error" @input="error = ''" />
            <button type="button" :aria-label="visible ? '隐藏密码' : '显示密码'" @click="visible = !visible">{{ visible ? '隐藏' : '显示' }}</button>
          </div>
          <p class="tmc-login-error" role="status">{{ error }}</p>
          <button class="tmc-login-submit" type="submit" :disabled="busy">{{ busy ? '登录中…' : '登录并继续' }}</button>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.tmc-login-backdrop{position:fixed;inset:0;z-index:10000;display:grid;place-items:center;padding:16px;background:#061b20a8;backdrop-filter:blur(12px)}
.tmc-login-dialog{position:relative;width:min(400px,100%);padding:30px;border:1px solid #ffffff9c;border-radius:22px;background:#f8fbfa;color:#203e39;box-shadow:0 24px 80px #031a2055;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}
.tmc-login-close{position:absolute;right:16px;top:12px;border:0;background:transparent;color:#708581;font-size:28px;cursor:pointer}
.tmc-login-mark{display:grid;place-items:center;width:40px;height:40px;border-radius:12px;background:#08a87c;color:white;font-size:26px;font-weight:700}
h2{font-size:21px;margin:18px 0 8px}p{font-size:13px;color:#6a807a;line-height:1.5;margin:0 0 22px}label{display:block;margin-bottom:8px;font-size:12px;font-weight:600}
.tmc-login-field{display:flex;align-items:center;border:1px solid #ccdbd4;border-radius:10px;background:white}.tmc-login-field:focus-within{border-color:#0baa7e;box-shadow:0 0 0 3px #0baa7e20}
input{height:48px;padding:0 14px;flex:1;min-width:0;border:0;background:transparent;color:#203e39;outline:none;font-size:16px}.tmc-login-field button{height:48px;padding:0 13px;border:0;background:transparent;color:#427e71;cursor:pointer}
.tmc-login-error{min-height:24px;margin:5px 0 9px;color:#b83d35}.tmc-login-submit{width:100%;height:48px;border:0;border-radius:10px;background:#09a878;color:#fff;font-weight:700;cursor:pointer}.tmc-login-submit:disabled{opacity:.6;cursor:wait}
</style>

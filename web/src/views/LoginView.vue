<script setup lang="ts">
import { ref } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';
import { ArrowRight, Lock, View, Hide } from '@element-plus/icons-vue';

const router = useRouter();
const password = ref('');
const visible = ref(false);
const busy = ref(false);
const error = ref('');
async function onSubmit() {
  if (busy.value) return;
  if (!password.value) { error.value = '请输入访问密码'; return; }
  busy.value = true;
  error.value = '';
  try {
    const response = await axios.post('/api/login', { password: password.value }, { timeout: 15000 });
    if (response.data.status !== 'ok') { error.value = '密码不正确，请重新输入'; return; }
    await router.replace('/apps/home');
  } catch { error.value = '暂时无法连接服务，请稍后重试'; }
  finally { busy.value = false; }
}
</script>

<template>
  <main class="tmc-login">
    <header class="brand"><img src="/tmc-mark.svg" alt="" /><span>TMC</span><small>MEDIA CENTER</small></header>
    <div class="login-layout">
      <section class="welcome" aria-label="TMC 媒体中心">
        <span class="eyebrow">YOUR SPACE. YOUR SOUND.</span>
        <h1>好时光，<br />从这里<span>开始。</span></h1>
        <p>一首喜欢的歌，一段期待的影像。<br />让每一次停留，都有好内容相伴。</p>
        <div class="soundscape" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="orbit orbit-three"></div><div class="disc"><span class="play-symbol"></span></div><span class="signal">TMC / PLAY YOUR MOMENT</span></div>
        <div class="features"><span>音乐</span><i></i><span>影像</span><i></i><span>更多可能</span></div>
      </section>
      <section class="login-card" aria-labelledby="login-heading">
        <div class="card-top"><span class="status-dot"></span>你的专属媒体空间</div>
        <h2 id="login-heading">欢迎回来</h2>
        <p class="card-description">输入访问密码，开启 TMC。</p>
        <form @submit.prevent="onSubmit">
          <label for="tmc-password">访问密码</label>
          <div class="password-field" :class="{ invalid: error }">
            <el-icon><Lock /></el-icon>
            <input id="tmc-password" v-model="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" :aria-invalid="!!error" aria-describedby="login-error" @input="error = ''" />
            <button class="visibility" type="button" :aria-label="visible ? '隐藏密码' : '显示密码'" :aria-pressed="visible" @click="visible = !visible"><el-icon><Hide v-if="visible" /><View v-else /></el-icon></button>
          </div>
          <p id="login-error" class="error-message" role="status">{{ error }}</p>
          <button type="submit" class="enter-button" :disabled="busy"><span>{{ busy ? '正在进入…' : '进入 TMC' }}</span><el-icon><ArrowRight /></el-icon></button>
        </form>
        <div class="card-footer"><span class="footer-line"></span><span>让喜欢，随行。</span><span class="footer-line"></span></div>
      </section>
    </div>
    <footer class="page-footer"><span>TMC · 车载媒体中心</span><span>为每一段闲暇而作</span></footer>
  </main>
</template>

<style scoped>
.tmc-login{--mint:#b9f6ce;box-sizing:border-box;min-height:100vh;min-height:100dvh;width:100%;padding:clamp(22px,4vw,60px);display:flex;flex-direction:column;background:radial-gradient(ellipse at 25% 65%,#17382f 0,transparent 48%),#0d1717;color:#edf4ee;overflow:hidden;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}
.brand{display:flex;align-items:center;gap:12px;flex-shrink:0}.brand img{width:38px;height:38px}.brand>span{font-size:25px;font-weight:750;letter-spacing:3px}.brand small{font-size:9px;letter-spacing:2px;color:#93a9a2;border-left:1px solid #3a4b46;padding-left:14px}
.login-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(290px,380px);align-items:center;gap:clamp(24px,6vw,100px);width:100%;max-width:1120px;margin:auto;flex:1;padding:36px 0}.welcome{position:relative}.eyebrow{font-size:10px;letter-spacing:2.5px;color:#a0b6ac}h1{font-size:clamp(34px,4.6vw,64px);line-height:1.24;letter-spacing:-2px;margin:22px 0 20px;font-weight:600}h1 span{color:var(--mint)}.welcome>p{font-size:14px;line-height:1.9;color:#a6b9b0;margin:0}.features{display:flex;align-items:center;gap:18px;color:#b8cac1;font-size:12px;letter-spacing:2px;margin-top:18px}.features i{height:3px;width:3px;background:#6c8d7d;border-radius:50%}
.soundscape{position:relative;height:155px;max-width:390px;overflow:hidden;margin-top:20px}.orbit{position:absolute;border:1px solid #b9f6ce24;border-radius:50%;width:320px;height:115px;left:8px;top:30px;transform:rotate(-19deg)}.orbit-two{transform:rotate(-34deg);width:300px;left:20px}.orbit-three{transform:rotate(-49deg);width:280px;left:30px}.disc{position:absolute;left:125px;top:30px;width:106px;height:106px;border-radius:50%;background:repeating-radial-gradient(circle,#223f34 0 3px,#345547 4px 5px);box-shadow:0 12px 45px #0004;border:1px solid #779984;display:grid;place-items:center}.play-symbol{width:42px;height:42px;border-radius:50%;background:var(--mint);display:grid;place-items:center}.play-symbol:after{content:"";border-left:12px solid #254132;border-top:8px solid transparent;border-bottom:8px solid transparent;margin-left:4px}.signal{position:absolute;bottom:0;right:4px;font-size:8px;letter-spacing:2px;color:#809d8e}
.login-card{background:#f5f7f2;color:#20372b;border:1px solid #ffffff66;padding:clamp(24px,3vw,40px);border-radius:25px;box-shadow:0 26px 80px #0003}.card-top{font-size:11px;letter-spacing:1px;color:#68776c;display:flex;align-items:center;gap:7px}.status-dot{width:6px;height:6px;background:#659a76;border-radius:50%}h2{font-size:28px;margin:26px 0 10px;font-weight:600;letter-spacing:-1px}.card-description{font-size:13px;color:#778078;margin:0 0 30px}label{display:block;font-size:12px;font-weight:600;margin-bottom:10px}.password-field{display:flex;align-items:center;gap:10px;border:1px solid #d6ded3;border-radius:11px;background:#fff;padding-left:14px;min-height:52px;color:#80907e}.password-field:focus-within{border-color:#527e60;box-shadow:0 0 0 3px #527e6015}.password-field.invalid{border-color:#bd584a}.password-field input{width:100%;min-width:0;background:none;border:0;outline:none;font-size:16px;color:#20372b;height:50px}.password-field input::placeholder{color:#a0aa9e;font-size:13px}.visibility{background:transparent;border:0;cursor:pointer;color:#70836e;min-width:46px;height:50px;display:grid;place-items:center;font-size:19px}.error-message{min-height:26px;margin:6px 0 10px;color:#b14c3e;font-size:12px;line-height:20px}.enter-button{width:100%;height:52px;border:0;border-radius:11px;background:#214a36;color:#edfff0;display:flex;align-items:center;justify-content:space-between;padding:0 20px;font-size:14px;font-weight:600;cursor:pointer;transition:background .2s}.enter-button:hover{background:#306247}.enter-button:disabled{opacity:.65;cursor:wait}button:focus-visible{outline:3px solid #6ca67c;outline-offset:3px}.card-footer{display:flex;align-items:center;gap:12px;margin-top:32px;font-size:11px;color:#8a9589;white-space:nowrap}.footer-line{height:1px;background:#dce3d9;flex:1}.page-footer{display:flex;justify-content:space-between;gap:12px;font-size:10px;color:#7b9287;letter-spacing:1px}
@media(max-width:620px){.login-layout{grid-template-columns:1fr;max-width:380px;padding:26px 0;gap:24px}.welcome h1{font-size:34px;margin:12px 0}.welcome>p,.soundscape,.features,.eyebrow{display:none}.welcome h1 br{display:none}.login-card{padding:26px}.brand small{font-size:8px}.page-footer>span:last-child{display:none}}
@media(max-height:650px) and (min-width:621px){.tmc-login{padding:24px 30px}.login-layout{padding:24px 0;gap:28px}.soundscape{height:110px;margin-top:10px}.disc{top:6px;width:88px;height:88px}.orbit{top:6px;height:92px}.signal{display:none}h1{font-size:38px;margin:16px 0}.login-card{padding:26px}h2{margin-top:18px}.card-description{margin-bottom:24px}.card-footer{margin-top:22px}}
</style>

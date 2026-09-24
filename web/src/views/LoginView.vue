<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import axios from 'axios';
import { ElMessage } from 'element-plus'
import router from '@/router';
import { post } from '@/functions/requests'

const state = reactive({
  visable: true,
});


const form = reactive({
  pwd: '',
})

const onSubmit = () => {
  console.log('submit!');
  post(`/api/login`, {
    password: form.pwd
  }, '登陆失败').then(response => {
    router.push('/apps/home')
  });
}

onMounted(() => {
  // fetchConfig();
})
</script>


<template>
  <main class="login-page">
    <section class="login-form" aria-label="登录">
      <el-form :model="form" label-width="auto" size="large" @submit.prevent="onSubmit">
        <el-form-item label="密码">
          <el-input v-model="form.pwd" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" class="login-submit">登录</el-button>
      </el-form>
    </section>
  </main>
</template>


<style scoped>
.login-page {
  width: 100%;
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  overflow-y: auto;
  padding: clamp(16px, 3vw, 32px);
  background: url('/logo.jpg') center / cover no-repeat;
}

.login-form {
  flex: 0 0 auto;
  width: 100%;
  max-width: 360px;
  margin-block: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: 0 24px 48px var(--color-shadow);
  backdrop-filter: blur(14px);
  padding: 20px;
  border-radius: 10px;
}

.login-submit {
  width: 100%;
  min-height: 44px;
}
</style>

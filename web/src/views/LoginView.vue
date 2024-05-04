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
  <img src="/logo.jpg" style="position: fixed; top: 0; width: 100%; height: 100%;" />
  <el-row justify="center">
    <el-col :span="6"></el-col>
    <el-col :span="8" className="login-form">
      <el-form :model="form" label-width="auto" style="max-width: 600px" size="large">
        <el-form-item label="密码">
          <el-input v-model="form.pwd" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSubmit" style="width: 295px">登陆</el-button>
        </el-form-item>
      </el-form>
    </el-col>
    <el-col :span="6"></el-col>
  </el-row>
</template>


<style>
.login-form {
  background: #fff;
  padding: 20px;
  border-radius: 10px;
  position: relative;
  top: 170px;
}
</style>
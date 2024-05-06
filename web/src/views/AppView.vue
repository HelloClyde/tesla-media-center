<script setup lang="ts">
import { House, Position, Headset, VideoPlay, SwitchFilled, InfoFilled, Setting, Switch, Film, Compass, Monitor, MapLocation } from '@element-plus/icons-vue';
import { onMounted, reactive, watch } from 'vue';
import { RouterView,useRouter, useRoute } from 'vue-router';
import { tsUnknownKeyword } from '@babel/types';

console.info('origin ua:', navigator.userAgent);
Object.defineProperty(navigator, 'userAgent', {
  value: navigator.userAgent + ';Android 6.0;Linux x86_64',
  writable: true
})
console.info('amap ua:', navigator.userAgent);

const router = useRouter();

const state = reactive({
  // isTesla: navigator.userAgent.toLowerCase().indexOf('tesla') >= 0,
  isTesla: true,
  menuTopItems: [{icon: House, route:'/apps/home'}],
  menuItems: [
    {icon: MapLocation, route: '/apps/nav'},
    // {icon: Headset, route: 'music'},
    {icon: '/icon/BILIBILI_LOGO.svg', route: '/apps/bilibili'},
    {icon: VideoPlay, route: '/apps/video'},
    // {icon: SwitchFilled, route: 'game'},
    {icon: Monitor, route: '/apps/debug'},
    // {icon: Setting, route: 'setting'},
    // {icon: Compass, route: 'brower'},
  ],
  curMenu: router.currentRoute.value.path
})


function routeTo(name: string){
  router.push(name);
  state.curMenu = name;
}

onMounted(() => {
})

</script>

<template>
  <template v-if="state.isTesla">
    <div class="menu">
      <div class="menu-top">
        <div class="menu-item" v-for="item of state.menuTopItems">
          <el-icon @click="routeTo(item.route)">
            <component :is="item.icon"></component>
          </el-icon>
        </div>
      </div>
      <div class="menu-bottom">
        <div class="menu-item" :class="{ 'menu-item-active': item.route == state.curMenu }" v-for="item of state.menuItems">
          <el-icon @click="routeTo(item.route)" v-if="typeof(item.icon) === 'string'">
            <img :src="item.icon" class="icon-svg" />
          </el-icon>
          <el-icon @click="routeTo(item.route)" v-else>
            <component :is="item.icon"></component>
          </el-icon>
        </div>
      </div>
    </div>

    <div class="main-view">
      <RouterView />
    </div>
  </template>
  <template v-else>
    <HomeViewPC />
  </template>
</template>

<style scoped>
.icon-svg {
  width: 100%;
  filter: drop-shadow(1000px 0 0 rgb(80, 77, 77));
  transform: translate(-1000px);
}

.menu-item-active .icon-svg
{
  filter: drop-shadow(1000px 0 0 #10aeff);
  transform: translate(-1000px);
}


.menu {
  width: 80px;
  top: 0;
  bottom: 0;
  left: 0;
  position: fixed;
  border-right: 1px solid #eee;
}

.menu-bottom {
  position: absolute;
  bottom: 0;
  width: 100%;
}

.menu-top {
  position: absolute;
  top: 0;
  width: 100%;
}

.menu-item {
  font-size: 50px;
  width: 100%;
  height: 80px;
  line-height: 80px;
  text-align: center;
  color: #504d4d;
}

.menu-item-active {
  color: #10aeff;
}

.main-view {
  margin-left: 80px;
  width: 1100px;
  height: 899px;
  overflow: auto;
}

nav {
  width: 100%;
  font-size: 12px;
  text-align: center;
  margin-top: 2rem;
}
</style>

import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/apps/HomeView.vue'
import SystemInfoDebug from '../views/apps/SystemInfoDebug.vue'
import VideoPlayerViewVue from '@/views/apps/VideoPlayerView.vue';
import LoginViewVue from '@/views/LoginView.vue';
import AppViewVue from '@/views/AppView.vue';
import BilibiliVue from '@/views/apps/Bilibili.vue';
import TeslaView from '@/views/apps/TeslaView.vue';
import GbaView from '@/views/apps/GbaView.vue';

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/apps',
      name: 'apps',
      component: AppViewVue,
      children:[
        { path: 'gam4980', name: 'gam4980', component: () => import('../views/apps/Gam4980View.vue') },
        { path: 'amap', name: 'amap-app', component: () => import('../views/apps/AmapAppView.vue') },
        { path: 'qqmusic', name: 'qqmusic', component: () => import('../views/apps/QQMusicView.vue') },
        {
          path: 'home',
          name: 'home',
          component: HomeView
        },
        {
          path: 'nav',
          name: 'nav',
          redirect: '/apps/amap'
        },
        {
          path: 'debug',
          name: 'debug',
          component: SystemInfoDebug
        },
        {
          path: 'video',
          name: 'video',
          component: VideoPlayerViewVue
        },
        {
          path: 'bilibili',
          name: 'bilibili',
          component: BilibiliVue
        },
        {
          path: 'tesla',
          name: 'tesla',
          component: TeslaView
        },
        {
          path: 'gba',
          name: 'gba',
          component: GbaView
        },
        {
          path: 'about',
          name: 'about',
          // route level code-splitting
          // this generates a separate chunk (About.[hash].js) for this route
          // which is lazy-loaded when the route is visited.
          component: () => import('../views/AboutView.vue')
        }
      ]
    },
    {
      path: '/',
      name: 'index',
      redirect: '/apps/home'
    },
    {
      path: '/login',
      name: 'login',
      component: LoginViewVue
    },
    
  ]
})

export default router

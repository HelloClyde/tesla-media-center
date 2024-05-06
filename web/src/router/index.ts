import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/apps/HomeView.vue'
import SystemInfoDebug from '../views/apps/SystemInfoDebug.vue'
import NavMap from '@/views/apps/NavMap.vue';
import VideoPlayerViewVue from '@/views/apps/VideoPlayerView.vue';
import LoginViewVue from '@/views/LoginView.vue';
import AppViewVue from '@/views/AppView.vue';
import BilibiliVue from '@/views/apps/Bilibili.vue';

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/apps',
      name: 'apps',
      component: AppViewVue,
      children:[
        {
          path: 'home',
          name: 'home',
          component: HomeView
        },
        {
          path: 'nav',
          name: 'nav',
          component: NavMap
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

import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import SystemInfoDebug from '../views/SystemInfoDebug.vue'
import NavMap from '@/views/NavMap.vue';
import VideoPlayerViewVue from '@/views/VideoPlayerView.vue';
import LoginViewVue from '@/views/LoginView.vue';

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/login',
      name: 'login',
      component: LoginViewVue
    },
    {
      path: '/nav',
      name: 'nav',
      component: NavMap
    },
    {
      path: '/debug',
      name: 'debug',
      component: SystemInfoDebug
    },
    {
      path: '/video',
      name: 'video',
      component: VideoPlayerViewVue
    },
    {
      path: '/about',
      name: 'about',
      // route level code-splitting
      // this generates a separate chunk (About.[hash].js) for this route
      // which is lazy-loaded when the route is visited.
      component: () => import('../views/AboutView.vue')
    }
  ]
})

export default router

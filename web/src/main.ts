import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import Vconsole from 'vconsole'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import './assets/main.css'
const vConsole = new Vconsole();

const app = createApp(App)

app.use(ElementPlus)
app.use(createPinia())
app.use(router)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}
app.config.globalProperties.$ELEMENT = {
    size: 'large'
};

app.mount('#app')

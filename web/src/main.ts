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

const app = createApp(App);

(window as any).$router = router;
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


console.info('origin ua:', navigator.userAgent);
Object.defineProperty(navigator, 'userAgent', {
  value: navigator.userAgent + ';Android 6.0;Linux x86_64',
  writable: true
})
console.info('amap ua:', navigator.userAgent);
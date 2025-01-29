import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'

import compresssionBuild from "rollup-plugin-compression";
import type { ICompressionOptions } from "rollup-plugin-compression";
// const option: ICompressionOptions = {
//   sourceName: `dist`,
//   type: "zip",
//   targetName: `dist-name`
// };

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    // compresssionBuild(option)
  ],
  define:{
    'process.env': {}
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080/api/',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, '') // 不可以省略rewrite
      }
    }
  }
})


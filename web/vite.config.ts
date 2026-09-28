import { fileURLToPath, URL } from 'node:url'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

import compresssionBuild from "rollup-plugin-compression";
import type { ICompressionOptions } from "rollup-plugin-compression";
// const option: ICompressionOptions = {
//   sourceName: `dist`,
//   type: "zip",
//   targetName: `dist-name`
// };

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [
    vue(),
    {
      name: 'version-legacy-player',
      transformIndexHtml(html) {
        const hash = createHash('sha256');
        for (const file of ['common.js', 'pcm-player.js', 'webgl.js', 'player.js', 'decoder.js', 'downloader.js', 'libffmpeg.js']) {
          hash.update(readFileSync(new URL(`./public/${file}`, import.meta.url)));
        }
        const version = hash.digest('hex').slice(0, 16);
        return html.replace(/src="\/(common|pcm-player|webgl|player)\.js"/g,
          (_match, name) => `src="/${name}.js?v=${version}"`);
      },
    },
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
        target: process.env.TMC_API_PROXY || loadEnv(mode, process.cwd(), 'TMC_').TMC_API_PROXY || 'http://localhost:8080/api/',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, '') // 不可以省略rewrite
      }
    }
  }
}))

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { CopyDocument, Close } from '@element-plus/icons-vue';
import BackgroundMusic from './BackgroundMusic.vue';
import { backgroundMusic } from '@/stores/backgroundMusic';
import { backgroundApps, type BackgroundApp } from '@/stores/backgroundApps';
const router=useRouter(), emptyOpen=ref(false), selected=ref('');
const entries=computed(()=>Object.values(backgroundApps));
const current=computed(()=>backgroundApps[selected.value]);
watch(()=>router.currentRoute.value.path,()=>{emptyOpen.value=false;selected.value='';});
watch(()=>!!backgroundMusic.song||entries.value.length>0,()=>{emptyOpen.value=false;});
async function openApp(app:BackgroundApp){selected.value='';await router.push(app.route);app.open?.();}
</script>
<template>
  <section class="background-dock" aria-label="后台应用">
    <div class="background-slots">
      <BackgroundMusic v-if="backgroundMusic.song" />
      <button v-for="app in entries" :key="app.id" class="background-slot" :aria-label="app.name+'后台控制'" :title="app.name" :aria-expanded="selected===app.id" @click="selected=selected===app.id?'':app.id"><img :src="app.icon" alt=""/><i v-if="app.running"/></button>
      <button v-if="!backgroundMusic.song&&!entries.length" class="background-slot empty-slot" aria-label="后台应用" title="后台应用" :aria-expanded="emptyOpen" @click="emptyOpen=!emptyOpen"><CopyDocument /></button>
    </div>
    <Teleport to="body">
      <template v-if="emptyOpen||current">
        <button class="dock-dismiss" aria-label="关闭后台应用面板" @click="emptyOpen=false;selected=''" />
        <section class="dock-panel" aria-label="后台应用面板" @keydown.esc="emptyOpen=false;selected=''">
          <header><strong>{{ current?.name||'后台应用' }}</strong><button aria-label="收起后台应用" @click="emptyOpen=false;selected=''"><Close /></button></header>
          <template v-if="current"><p>{{ current.detail || (current.running?'正在后台运行':'已暂停') }}</p><button @click="openApp(current)">打开应用</button></template>
          <p v-else>暂无后台应用，音乐播放后会显示在这里。</p>
        </section>
      </template>
    </Teleport>
  </section>
</template>
<style scoped>
.background-dock{flex:0 0 auto;min-height:62px;width:100%;padding:6px 0;border-top:1px solid var(--color-border);background:var(--color-surface);box-sizing:border-box}
.background-slots{display:flex;flex-direction:column;align-items:center;max-height:162px;overflow-y:auto;overflow-x:hidden;scrollbar-width:none}.background-slots::-webkit-scrollbar{display:none}
.background-slot{position:relative;flex:0 0 48px;width:44px;padding:6px;display:grid;place-items:center;border:0;border-radius:13px;background:none;color:var(--color-text-soft);cursor:pointer}.background-slot img,.background-slot svg{width:32px;height:32px;object-fit:contain}.background-slot i{position:absolute;right:3px;bottom:4px;width:8px;height:8px;border-radius:50%;background:#13ac7b;border:2px solid var(--color-surface)}.empty-slot{opacity:.65}.background-slot:focus-visible{outline:2px solid var(--color-accent);outline-offset:-2px}
.dock-dismiss{position:fixed;inset:0;background:transparent;border:0;z-index:2100}.dock-panel{position:fixed;z-index:2101;left:calc(clamp(48px,6.4vw,80px) + 10px);bottom:16px;width:min(320px,calc(100vw - 100px));padding:18px;border:1px solid var(--color-border);border-radius:20px;background:var(--color-surface);color:var(--color-text);box-shadow:0 10px 32px #0002}.dock-panel header{display:flex;align-items:center;justify-content:space-between}.dock-panel button{border:0;border-radius:10px;background:var(--color-background-mute);color:inherit;padding:8px 12px;cursor:pointer;min-height:40px}.dock-panel header button{display:grid;place-items:center;width:40px}.dock-panel svg{width:18px;height:18px}.dock-panel p{font-size:13px;color:var(--color-text-soft);line-height:1.7;margin:16px 0}
</style>

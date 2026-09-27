<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { Search, Close } from '@element-plus/icons-vue';
import { applications } from '@/apps';

const query = ref('');
const visibleApps = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase();
  return applications.filter(app => `${app.label} ${app.keywords}`.toLocaleLowerCase().includes(keyword));
});
</script>

<template>
  <section class="app-launcher" aria-labelledby="apps-title">
    <header class="launcher-header">
      <div class="launcher-heading">
        <div class="launcher-brand"><img src="/tmc-mark.svg" alt="" /><span>TMC</span></div>
        <h1 id="apps-title">应用<span>{{ applications.length }}</span></h1>
      </div>
      <div class="app-search">
        <Search aria-hidden="true" />
        <input v-model="query" type="search" aria-label="搜索应用" placeholder="搜索应用" maxlength="60" />
        <button v-if="query" type="button" aria-label="清空应用搜索" @click="query = ''"><Close /></button>
      </div>
    </header>
    <nav class="app-grid" aria-label="应用列表">
      <RouterLink v-for="app in visibleApps" :key="app.route" :to="app.route" class="app-card" :style="{ '--app-color': app.color }" :aria-label="app.label">
        <div class="card-top">
          <span class="app-icon"><img v-if="typeof app.icon === 'string'" :src="app.icon" alt="" /><component v-else :is="app.icon" aria-hidden="true" /></span>
          <span v-if="app.badge" class="app-badge">{{ app.badge }}</span>
        </div>
        <strong>{{ app.label }}</strong>
        <span class="app-description">{{ app.description }}</span>
      </RouterLink>
    </nav>
    <div v-if="!visibleApps.length" class="no-apps" role="status"><p>没有找到相关应用</p><button type="button" @click="query = ''">查看全部应用</button></div>
  </section>
</template>

<style scoped>
.app-launcher{height:100%;overflow-y:auto;overflow-x:hidden;padding:clamp(18px,3vw,36px);color:var(--color-text);background:radial-gradient(ellipse at 95% 0,rgba(55,178,147,.09),transparent 55%);scrollbar-width:thin;scrollbar-color:var(--color-border-hover) transparent}
.launcher-header{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:24px}
.launcher-brand{display:flex;align-items:center;gap:7px;font-size:11px;letter-spacing:2px;color:var(--color-text-soft);margin-bottom:6px}.launcher-brand img{width:22px;height:22px}
h1{display:flex;align-items:center;gap:12px;font-size:28px;line-height:1.3;font-weight:650;margin:0}h1 span{font-size:12px;line-height:24px;min-width:24px;text-align:center;border-radius:8px;background:var(--color-accent-soft);color:var(--color-text-soft)}
.app-search{display:flex;align-items:center;gap:9px;width:clamp(160px,25vw,250px);max-width:100%;padding:0 12px;min-height:42px;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);color:var(--color-text-soft)}
.app-search:focus-within{border-color:var(--color-accent)}.app-search>svg{width:17px;height:17px;flex-shrink:0}.app-search input{min-width:0;flex:1;width:100%;border:0;outline:0;background:transparent;color:var(--color-text);font:inherit;font-size:13px}.app-search input::-webkit-search-cancel-button{display:none}.app-search button{display:grid;place-items:center;flex-shrink:0;width:28px;height:32px;border:0;background:transparent;color:inherit;cursor:pointer}.app-search button svg{width:15px;height:15px}
.app-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(185px,1fr));gap:14px}
.app-card{display:flex;flex-direction:column;min-width:0;padding:18px;border:1px solid var(--color-border);border-radius:20px;background:var(--color-card-gradient);color:var(--color-text);text-decoration:none;box-shadow:0 3px 12px var(--color-shadow);transition:transform .18s,border-color .18s,box-shadow .18s}
.card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:12px}.app-icon{display:grid;place-items:center;width:48px;height:48px;border-radius:14px;background:var(--color-background-mute);color:var(--app-color)}.app-icon img,.app-icon svg{width:34px;height:34px;object-fit:contain}.app-badge{font-size:10px;line-height:20px;padding:0 7px;border-radius:6px;background:var(--color-background-mute);color:var(--color-text-soft)}
.app-card strong{font-size:16px;font-weight:600;line-height:24px}.app-description{font-size:12px;line-height:20px;color:var(--color-text-soft);margin-top:3px}
.app-card:focus-visible{outline:3px solid var(--color-accent);outline-offset:3px}.app-card:active{transform:scale(.98)}@media(hover:hover){.app-card:hover{transform:translateY(-2px);border-color:var(--app-color);background:var(--color-surface-strong)}}
.no-apps{padding:50px 12px;text-align:center;color:var(--color-text-soft)}.no-apps button{margin-top:16px;padding:10px 18px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);color:var(--color-accent);cursor:pointer}
@media(max-width:520px){.app-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.app-card{padding:14px;border-radius:16px}.app-description{font-size:11px}.launcher-header{gap:14px}}
@media(prefers-reduced-motion:reduce){.app-card{transition:none}}
</style>

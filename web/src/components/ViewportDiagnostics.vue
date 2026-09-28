<script setup lang="ts">
import { layoutRecording, layoutSamples, setLayoutRecording, clearLayoutSamples } from '@/functions/viewportDiagnostics';
</script>
<template>
  <section class="viewport-diagnostics">
    <h2>切歌与视口诊断</h2>
    <p>开启后返回 QQ 音乐切歌，再回到这里查看。记录保留最近 80 条，刷新页面后清空。</p>
    <label><input type="checkbox" :checked="layoutRecording" @change="setLayoutRecording(($event.target as HTMLInputElement).checked)" /> 记录布局变化</label>
    <button @click="clearLayoutSamples">清空记录</button>
    <p>“布局视口 resize”表示浏览器提供的窗口尺寸变了；“可视视口变化”表示可见区域高度或偏移变了；只有播放器变化则更可能是页面内部重排。若画面移动但这些数值都不变，网页无法确认是否为车机窗口或合成层移动。</p>
    <div class="table"><table><thead><tr><th>时间 / 事件</th><th>检测结果</th><th>布局视口</th><th>可视视口 / 偏移</th><th>页面 / 容器滚动</th><th>应用外框</th><th>当前页面</th><th>播放器</th><th>底部控制区</th></tr></thead><tbody><tr v-for="(row,index) in layoutSamples" :key="index"><td>{{ row.time }}<br/>{{ row.reason }}</td><td>{{ row.change }}</td><td>{{ row.viewport }}</td><td>{{ row.visual }}</td><td>{{ row.scroll }}</td><td>{{ row.shell }}</td><td>{{ row.page }}</td><td>{{ row.player }}</td><td>{{ row.footer }}</td></tr></tbody></table></div>
  </section>
</template>
<style scoped>
.viewport-diagnostics{padding:20px;color:var(--color-text)}p{margin:12px 0;color:var(--color-text-soft);line-height:1.7}button{margin-left:16px;padding:8px 14px;border:1px solid var(--color-border);background:var(--color-surface);color:inherit;border-radius:10px}.table{overflow:auto;margin-top:20px}table{border-collapse:collapse;font-size:12px;width:100%}th,td{padding:10px;text-align:left;border-bottom:1px solid var(--color-border);min-width:110px}
</style>

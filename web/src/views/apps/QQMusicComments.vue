<script setup lang="ts">
defineProps<{
  comments: { id: string; name: string; text: string; likes: number }[];
  busy: boolean; error: string; more: boolean; title: string; immersive?: boolean;
}>();
const emit = defineEmits<{ more: [] }>();
</script>

<template>
  <section class="comments-panel" :class="{ immersive }" aria-label="歌曲热门评论" :aria-busy="busy">
    <div class="comments-heading"><small>听见共鸣</small><h2>热门评论</h2><p>{{ title }}</p></div>
    <article v-for="comment in comments" :key="comment.id" class="music-comment">
      <div class="comment-meta"><span class="comment-avatar" aria-hidden="true">{{ Array.from(comment.name || '听友')[0] }}</span><strong>{{ comment.name || '听友' }}</strong><span class="comment-likes" :aria-label="`${comment.likes} 人赞同`">♡ {{ comment.likes }}</span></div>
      <p>{{ comment.text }}</p>
    </article>
    <p v-if="busy" class="comment-status" role="status">正在加载评论…</p>
    <p v-else-if="error" class="comment-status" role="status">{{ error }}</p>
    <p v-else-if="!comments.length" class="comment-status">这里还很安静，先听听这首歌吧</p>
    <button v-if="!busy && (more || error)" class="comments-more" @click="emit('more')">{{ error ? '重试' : '继续看看' }}</button>
    <p v-else-if="!busy && !error && comments.length" class="comment-status">已看完这些热门评论</p>
  </section>
</template>

<style scoped>
.comments-panel{--comment-scroll-thumb:rgba(97,121,143,.3);--comment-scroll-hover:rgba(97,121,143,.55);scrollbar-color:var(--comment-scroll-thumb) transparent}
.comments-panel.immersive{--comment-scroll-thumb:rgba(173,207,192,.25);--comment-scroll-hover:rgba(173,207,192,.5);color-scheme:dark}
/* Chromium uses the custom track below; Firefox keeps the thin native fallback. */
@supports selector(::-webkit-scrollbar){
  .comments-panel{scrollbar-width:auto!important;scrollbar-color:auto}
  .comments-panel::-webkit-scrollbar{width:5px;height:5px}
  .comments-panel::-webkit-scrollbar-track,.comments-panel::-webkit-scrollbar-corner{background:transparent}
  .comments-panel::-webkit-scrollbar-thumb{background:var(--comment-scroll-thumb);border-radius:10px}
  .comments-panel::-webkit-scrollbar-thumb:hover,.comments-panel::-webkit-scrollbar-thumb:active{background:var(--comment-scroll-hover)}
  .comments-panel::-webkit-scrollbar-button{display:none;width:0;height:0}
}
.comments-panel{--comment-text:var(--color-text);--comment-muted:var(--color-text-soft);--comment-line:var(--color-border);--comment-accent:var(--color-accent);height:100%;min-height:0;overflow:auto;overscroll-behavior:contain;box-sizing:border-box;padding:12px 18px 28px;color:var(--comment-text);scrollbar-width:thin}
.immersive{--comment-text:#e0eee8;--comment-muted:#9bb5aa;--comment-line:#ffffff16;--comment-accent:#b9f6ce}
.comments-heading{padding:8px 0 18px}.comments-heading small{font-size:11px;letter-spacing:3px;color:var(--comment-muted)}.comments-heading h2{font-size:24px;font-weight:500;margin:8px 0}.comments-heading>p{font-size:12px;color:var(--comment-muted);margin:0;overflow-wrap:anywhere}
.music-comment{padding:20px 0;border-top:1px solid var(--comment-line)}.comment-meta{display:flex;align-items:center;gap:10px}.comment-avatar{display:grid;place-items:center;flex:0 0 30px;height:30px;border-radius:50%;background:#74ae951c;color:var(--comment-accent);font-size:12px}.comment-meta strong{font-size:13px;font-weight:500;overflow-wrap:anywhere;min-width:0}.comment-likes{margin-left:auto;white-space:nowrap;font-size:11px;color:var(--comment-muted)}.music-comment>p{font-size:15px;line-height:1.9;white-space:pre-wrap;overflow-wrap:anywhere;margin:12px 0 0}.comment-status{font-size:12px;line-height:1.7;text-align:center;color:var(--comment-muted);padding:20px 0}.comments-more{display:block;margin:12px auto;padding:10px 24px;border:1px solid var(--comment-line);border-radius:20px;background:transparent;color:var(--comment-accent);cursor:pointer}.comments-more:focus-visible{outline:2px solid var(--comment-accent);outline-offset:3px}@media(max-width:600px){.comments-panel{padding:8px 8px 20px}.music-comment>p{font-size:14px}}
</style>

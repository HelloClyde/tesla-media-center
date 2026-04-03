<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';

const state = reactive({
    streamWsUrl: '',
    ctlWs: null as any,
    player: null as any,
    curTime: 0,
    totalTime: -1,
})

interface VideoProps {
    video: any;
    onClick: (type: string, id: any) => void;
}

const props = defineProps<VideoProps>();


onMounted(() => {
    // console.log('props', props);

})

const formatTooltip = (val: number) => {
    return `${state.curTime} / ${state.totalTime}`
}


onUnmounted(() => {
})

function formatTime(seconds: number | string): string {
    // 如果输入是字符串，直接返回
    if (typeof seconds === 'string') {
        return seconds;
    }
    if (seconds < 60) {
        // 少于一分钟，直接显示秒数
        return `00:${seconds}`;
    } else if (seconds < 3600) {
        // 大于等于1分钟且少于1小时
        let minutes = Math.floor(seconds / 60);
        let remainingSeconds = seconds % 60;
        return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
    } else {
        // 大于等于1小时
        let hours = Math.floor(seconds / 3600);
        let minutes = Math.floor((seconds - (hours * 3600)) / 60);
        let remainingSeconds = seconds % 60;
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
    }
}

const coverUrl = computed(() => {
    return props.video?.pic || props.video?.cover || props.video?.upic || props.video?.face || props.video?.uface || '';
});

const titleHtml = computed(() => {
    return props.video?.title || props.video?.uname || props.video?.name || props.video?.season_name || '未命名';
});

const subtitleText = computed(() => {
    return props.video?.owner?.name
        || props.video?.author
        || props.video?.uname
        || props.video?.areas
        || props.video?.styles
        || props.video?.desc
        || props.video?.description
        || props.video?.sign
        || '';
});

const metaLabel = computed(() => {
    if (props.video?.bvid) return '视频';
    if (props.video?.season_id) return '番剧';
    if (props.video?.roomid) return '直播';
    if (props.video?.mid) return '用户';
    if (props.video?.cv_id || props.video?.id) return '内容';
    return '搜索结果';
});

const clickType = computed(() => {
    if (props.video?.bvid) return 'bv';
    if (props.video?.season_id) return 'bangumi_ss';
    if (props.video?.roomid) return 'live_room';
    if (props.video?.mid) return 'bili_user';
    if (props.video?.cv_id) return 'article';
    return 'search_item';
});

const clickId = computed(() => {
    return props.video?.bvid || props.video?.season_id || props.video?.roomid || props.video?.mid || props.video?.cv_id || props.video?.id;
});

</script>

<template>
    <el-card class="video-card" @click="props?.onClick(clickType, clickId)">
        <template #header>
            <div class="video-cover">
                <img v-if="coverUrl" :src="`${coverUrl}@350w_196h_1c_!web-home-common-cover`" />
                <div v-else class="cover-placeholder">{{ metaLabel }}</div>
                <div class="cover-float">
                    <div truncated class="video-duration">
                        {{ props.video?.duration ? formatTime(props.video?.duration) : metaLabel }}
                    </div>
                </div>
            </div>
        </template>
        <el-text line-clamp="2" class="video-title">
            <div v-html="titleHtml"></div>
        </el-text>
        <el-row>
            <el-col :span="20">
                <el-text truncated class="video-author">
                <el-icon>
                    <User />
                </el-icon>
                {{ subtitleText || metaLabel }}
                </el-text>
            </el-col>
            <el-col :span="4">
            </el-col>
            
        </el-row>
    </el-card>
</template>

<style>
.keyword{
    color: #f00;
}

.video-card {
  width: 100%;
  height: 100%;
  border: 1px solid var(--color-border) !important;
  background: var(--color-card-gradient) !important;
  box-shadow: 0 18px 34px var(--color-shadow);
}

.video-card .el-card__body {
  padding: 4px;
}

.cover-float {
    background-color: rgb(0 0 0 / 33%);
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 40px;
}

.video-title {
  height: 75px;
  width: 100%;
  font-size: 24px !important;
  color: var(--color-heading) !important;
}

.video-author {
  font-size: 20px !important;
  color: var(--color-text-soft) !important;
}

.video-duration {
    font-size: 20px !important;
    position: absolute;
    right: 10px;
    color: var(--color-text-contrast);
}

.video-card .el-card__header {
  padding: 0;
  width: 100%;
  aspect-ratio: 350 / 196;
  height: auto;
  overflow: hidden;
}

.video-cover>img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-accent-soft) 0%, var(--color-panel-muted) 100%);
  color: var(--color-heading);
  font-size: 24px;
  font-weight: 700;
}

</style>

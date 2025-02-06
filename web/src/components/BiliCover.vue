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

function formatTime(seconds: number): string {
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

</script>

<template>
    <el-card v-if="props.video?.bvid" class="video-card" @click="props?.onClick('bv', props.video.bvid)">
        <template #header>
            <div class="video-cover">
                <img :src="`${video.pic}@350w_196h_1c_!web-home-common-cover`" />
                <div class="cover-float">
                    <div truncated class="video-duration">
                        {{ formatTime(props.video?.duration) }}
                    </div>
                </div>
            </div>
        </template>
        <el-text line-clamp="2" class="video-title">
            {{ video.title }}
        </el-text>
        <el-row>
            <el-col :span="20">
                <el-text truncated class="video-author">
                <el-icon>
                    <User />
                </el-icon>
                {{ video?.owner?.name }}
                </el-text>
            </el-col>
            <el-col :span="4">
            </el-col>
            
        </el-row>
    </el-card>
    <el-card v-else-if="props.video?.season_id" class="video-card" @click="props?.onClick('bangumi_ss', props.video.season_id)">
        <template #header>
            <div class="video-cover">
                <img :src="`${video.cover}@350w_196h_1c_!web-home-common-cover`" />
            </div>
        </template>
        <el-text line-clamp="2" class="video-title">
            {{ video.title }}
        </el-text>
        <el-row>
            <el-text truncated class="video-author">
                {{ props.video?.rating }}
            </el-text>
        </el-row>
    </el-card>
    
</template>

<style>


.video-card {
  width: 350px;
  height: 322px;
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
}

.video-author {
  font-size: 20px !important;
}

.video-duration {
    font-size: 20px !important;
    position: absolute;
    right: 10px;
    color: #fff;
}

.video-card .el-card__header {
  padding: 0;
  width: 350px;
  height: 196px;
}

.video-cover>img {
  width: 350px;
  height: 196px;
  object-fit: cover;
}

</style>

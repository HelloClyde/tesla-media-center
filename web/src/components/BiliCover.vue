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


</script>

<template>
    <el-card v-if="props.video?.bvid" class="video-card" @click="props?.onClick('bv', props.video.bvid)">
        <template #header>
            <div class="video-cover">
            <img :src="`${video.pic}@350w_196h_1c_!web-home-common-cover`" />
            </div>
        </template>
        <el-text line-clamp="2" class="video-title">
            {{ video.title }}
        </el-text>
        <el-row>
            <el-text truncated class="video-author">
            <el-icon>
                <User />

            </el-icon>
            {{ video?.owner?.name }}
            </el-text>
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

.video-title {
  height: 75px;
  width: 100%;
  font-size: 24px !important;
}

.video-author {
  font-size: 20px !important;
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

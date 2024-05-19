<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import VideoPlayer from '@/components/VideoPlayer.vue';

const state = reactive({
  videoConfig: null as any,
  homeVideoList: [] as any[],
  hotVideoList: [] as any[],
  rankVideoList: [] as any[],
  curTab: "homepage"
})

const loadHot = () => {
  get('/api/bilibili/hot').then(data => {
    state.hotVideoList = data.list;
  });
}

const loadHomeVideos = () => {
  get('/api/bilibili/home').then(data => {
    state.homeVideoList = data.item;
  });
}

const loadRankVideos = () => {
  get('/api/bilibili/rank').then(data => {
    state.rankVideoList = data.list;
  });
}

const tabChange = (name: string) => {
  console.log(name);
  switch (name){
    case 'homepage':
      loadHomeVideos();
      break;
    case 'hot':
      loadHot();
      break;
    case 'rank':
      loadRankVideos();
      break;
  }
}

const videoSelect = (video: any) => {
  console.log(video);
  state.videoConfig = { 'type': 'bv', 'bvid': video?.bvid}
}


onMounted(() => {
  loadHomeVideos();
})
</script>


<template>
  <div v-if="state.videoConfig" class="video-view">
    <VideoPlayer  type="bv" :on-close="() => state.videoConfig = null"  :video-config="state.videoConfig" />
  </div>
  
  <el-tabs v-show="state.videoConfig == null" v-model="state.curTab" @tab-change="tabChange" class="tabs">
    <el-tab-pane label="首页" name="homepage">
      <el-space wrap>
        <el-card class="video-card" v-for="video of state.homeVideoList" :key="video.aid" @click="videoSelect(video)">
          <template #header>
            <div class="video-cover">
              <img :src="video.pic" />
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
              {{ video.owner.name }}
            </el-text>
          </el-row>
        </el-card>
      </el-space>
    </el-tab-pane>
    <el-tab-pane label="热门" name="hot">
      <el-space wrap>
        <el-card class="video-card" v-for="video of state.hotVideoList" :key="video.aid" @click="videoSelect(video)">
          <template #header>
            <div class="video-cover">
              <img :src="video.pic" />
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
              {{ video.owner.name }}
            </el-text>
          </el-row>
        </el-card>
      </el-space>
    </el-tab-pane>
    
    <el-tab-pane label="排行榜" name="rank">
      <el-space wrap>
        <el-card class="video-card" v-for="video of state.rankVideoList" :key="video.aid" @click="videoSelect(video)">
          <template #header>
            <div class="video-cover">
              <img :src="video.pic" />
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
              {{ video.owner.name }}
            </el-text>
          </el-row>
        </el-card>
      </el-space>
    </el-tab-pane>
    <el-tab-pane label="关注" name="关注">关注</el-tab-pane>
    <el-tab-pane label="我的" name="my">我的</el-tab-pane>
  </el-tabs>
</template>


<style>
.video-view {
  position: absolute;
  top: 0px;
  z-index: 99999;
}

.tabs {
  margin-left: 10px;
  font-weight: 600;
}

.tabs .el-tabs__item {
  font-size: 20px;
}

.video-card {
  width: 250px;
  height: 230px;
}

.video-card .el-card__body {
  padding: 4px;
}

.video-title {
  height: 45px;
  width: 100%;
}

.video-author {
}

.video-card .el-card__header {
  padding: 0;
  width: 250px;
  height: 140px;
}

.video-cover>img {
  width: 250px;
  height: 140px;
}
</style>
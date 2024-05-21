<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import VideoPlayer from '@/components/VideoPlayer.vue';
import { Search } from '@element-plus/icons-vue'

const state = reactive({
  videoConfig: null as any,
  homeVideoList: [] as any[],
  hotVideoList: [] as any[],
  rankVideoList: [] as any[],
  curTab: "homepage",
  searchText: '',
  searchVideoResult: [] as any[],
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

const searchByText = ()  => {
  get(`/api/bilibili/search?pageNo=${1}&keyword=${state.searchText}`).then(data => {
      console.log(data);
      const allReuslt = data.result;
      state.searchVideoResult = allReuslt.filter((x: any) => x.result_type == 'video')[0].data;
      console.log(state.searchVideoResult);
  })
}

const tabChange = (name: string) => {
  console.log(name);
  switch (name) {
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
  state.videoConfig = { 'type': 'bv', 'bvid': video?.bvid }
}


onMounted(() => {
  loadHomeVideos();
})
</script>


<template>
  <div v-if="state.videoConfig" class="video-view">
    <VideoPlayer type="bv" :on-close="() => state.videoConfig = null" :video-config="state.videoConfig" />
  </div>

  <div class="bv-list">
    <el-tabs v-model="state.curTab" @tab-change="tabChange" class="tabs">
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
    <el-input class="search-input" v-model="state.searchText" size="large" placeholder="请输入搜索关键词" :prefix-icon="Search">
      <template #append>
        <el-button :icon="Search" @click="searchByText"/>
      </template>
    </el-input>
  </div>
</template>


<style>
.search-input {
  width: 400px !important;
  position: absolute !important;
  top: 4px;
  right: 40px;
  font-size: 20px !important;
}

.bv-list {
  width: 100%;
  height: 100%;
  overflow-y: auto;
}

.video-view {
  position: absolute;
  top: 0px;
  z-index: 99999;
}

.tabs {
  margin-left: 10px;
  font-weight: 600;
}

.el-tabs__nav {
  height: 60px;
}

.tabs .el-tabs__item {
  font-size: 32px;
  height: 60px;
}

.video-card {
  width: 350px;
  height: 322px;
}

.video-card .el-card__body {
  padding: 4px;
}

.video-title {
  height: 63px;
  width: 100%;
  font-size: 20px !important;
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
}
</style>
<script setup lang="ts">
import { ref, onMounted, reactive, shallowRef, onUnmounted, computed } from 'vue';
import { get } from '@/functions/requests'
import VideoPlayer from '@/components/VideoPlayer.vue';
import { Search } from '@element-plus/icons-vue'
import BiliCover from '@/components/BiliCover.vue';

const state = reactive({
  videoConfig: null as any,
  homeVideoList: [] as any[],
  hotVideoList: [] as any[],
  rankVideoList: [] as any[],
  rankType: 'All',
  curTab: "homepage",
  searchText: '',
  searchVideoResult: [] as any[],
})


const rankTypes= [
  {'label': '全部', value:'All'},
  {'label': '番剧', value:'Bangumi'},
  {'label': '国产动画', value:'GuochuangAnime'},
  {'label': '纪录片', value:'Documentary'},
  {'label': '动画', value:'Douga'},
  {'label': '音乐', value:'Music'},
  {'label': '舞蹈', value:'Dance'},
  {'label': '游戏', value:'Game'},
  {'label': '知识', value:'Knowledge'},
  {'label': '科技', value:'Technology'},
  {'label': '运动', value:'Sports'},
  {'label': '汽车', value:'Car'},
  {'label': '生活', value:'Life'},
  {'label': '美食', value:'Food'},
  {'label': '动物圈', value:'Animal'},
  {'label': '鬼畜', value:'Kitchen'},
  {'label': '时尚', value:'Fashion'},
  {'label': '娱乐', value:'Ent'},
  {'label': '影视', value:'Cinephile'},
  {'label': '电影', value:'Movie'},
  {'label': '电视剧', value:'TV'},
  {'label': '综艺', value:'Variety'},
  {'label': '原创', value:'Original'},
  {'label': '新人', value:'Rookie'},
]


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
  get(`/api/bilibili/rank?type=${state.rankType}`).then(data => {
    state.rankVideoList = data.list;
  });
}

const searchByText = () => {
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
          <BiliCover v-for="video of state.homeVideoList" :video="video" :on-click="(type, id) => videoSelect(video)" />
        </el-space>
      </el-tab-pane>
      <el-tab-pane label="热门" name="hot">
        <el-space wrap>
          <BiliCover v-for="video of state.hotVideoList" :video="video" :on-click="(type, id) => videoSelect(video)" />
        </el-space>
      </el-tab-pane>

      <el-tab-pane label="排行榜" name="rank">
          <el-radio-group v-model="state.rankType" size="large"  @change="(v: string) => loadRankVideos()" class="rank-type">
            <el-radio-button v-for="item of rankTypes" :key="item.value" :label="item.label" :value="item.value" />
          </el-radio-group>
        <el-space wrap>
          <BiliCover v-for="video of state.rankVideoList" :video="video" :on-click="(type, id) => videoSelect(video)" />
        </el-space>
      </el-tab-pane>
      <el-tab-pane label="关注" name="关注">关注</el-tab-pane>
      <el-tab-pane label="我的" name="my">我的</el-tab-pane>
    </el-tabs>
    <el-input class="search-input" v-model="state.searchText" size="large" placeholder="请输入搜索关键词" :prefix-icon="Search">
      <template #append>
        <el-button :icon="Search" @click="searchByText" />
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

.rank-type{
  margin: 0 0 10px 0;
}

.rank-type span{
  font-size: 22px !important;
}
</style>
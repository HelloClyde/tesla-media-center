<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue';
import { get } from '@/functions/requests'
import { Search } from '@element-plus/icons-vue'
import BiliCover from '@/components/BiliCover.vue';
import BvPlayer from '@/components/BvPlayer.vue';

const searchInput = ref<any>(null);
const listContainer = ref<HTMLElement | null>(null);
let listResizeObserver: ResizeObserver | null = null;

const state = reactive({
  videoConfig: null as any,
  homeVideoList: [] as any[],
  hotVideoList: [] as any[],
  hotPage: 1,
  hotPageSize: 20,
  hotLoading: false,
  hotFinished: false,
  rankVideoList: [] as any[],
  rankType: 'All',
  curTab: "homepage",
  searchText: '',
  searchVideoResult: [] as any[],
  searchPage: 1,
  searchPageSize: 20,
  searchLoading: false,
  searchFinished: false,
  gridColumns: 3,
  gridContainerWidth: 0,
})

const updateGridColumns = (width: number) => {
  state.gridContainerWidth = Math.round(width);
  if (width <= 640) {
    state.gridColumns = 1;
  } else if (width <= 860) {
    state.gridColumns = 2;
  } else {
    state.gridColumns = 3;
  }
  console.log('[bilibili-grid]', {
    containerWidth: state.gridContainerWidth,
    columns: state.gridColumns,
    viewportWidth: window.innerWidth,
  });
}


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


const loadHot = (append = false) => {
  if (state.hotLoading || (append && state.hotFinished)) {
    return;
  }
  state.hotLoading = true;
  get(`/api/bilibili/hot?pn=${state.hotPage}&ps=${state.hotPageSize}`).then(data => {
    const incomingList = data.list || [];
    if (append) {
      const mergedList = [...state.hotVideoList];
      const seen = new Set(mergedList.map((video: any) => video.bvid || `${video.aid}-${video.title}`));
      incomingList.forEach((video: any) => {
        const key = video.bvid || `${video.aid}-${video.title}`;
        if (!seen.has(key)) {
          seen.add(key);
          mergedList.push(video);
        }
      });
      state.hotVideoList = mergedList;
    } else {
      state.hotVideoList = incomingList;
    }
    state.hotFinished = Boolean(data.no_more) || incomingList.length < state.hotPageSize;
  }).finally(() => {
    state.hotLoading = false;
  });
}

const resetAndLoadHot = () => {
  state.hotPage = 1;
  state.hotFinished = false;
  state.hotVideoList = [];
  loadHot(false);
}

const loadMoreHot = () => {
  if (state.hotLoading || state.hotFinished) {
    return;
  }
  state.hotPage += 1;
  loadHot(true);
}

const onListScroll = (event: Event) => {
  const target = event.target as HTMLElement;
  const reachBottomThreshold = 220;
  const remaining = target.scrollHeight - target.scrollTop - target.clientHeight;
  if (remaining <= reachBottomThreshold) {
    if (state.curTab === 'hot') {
      loadMoreHot();
    } else if (state.curTab === 'search') {
      loadMoreSearch();
    }
  }
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

const loadSearch = (append = false) => {
  if (state.searchLoading || !state.searchText.trim() || (append && state.searchFinished)) {
    return;
  }
  state.searchLoading = true;
  get(`/api/bilibili/search?pageNo=${state.searchPage}&keyword=${encodeURIComponent(state.searchText)}`).then(data => {
    const allReuslt = data.result || [];
    const videoResult = allReuslt.filter((x: any) => x.result_type == 'video')[0];
    const incomingList = videoResult?.data || [];
    if (append) {
      const mergedList = [...state.searchVideoResult];
      const seen = new Set(mergedList.map((video: any) => video.bvid || `${video.aid}-${video.title}`));
      incomingList.forEach((video: any) => {
        const key = video.bvid || `${video.aid}-${video.title}`;
        if (!seen.has(key)) {
          seen.add(key);
          mergedList.push(video);
        }
      });
      state.searchVideoResult = mergedList;
    } else {
      state.searchVideoResult = incomingList;
    }
    state.searchFinished = incomingList.length < state.searchPageSize;
  }).finally(() => {
    state.searchLoading = false;
  })
}

const searchByText = () => {
  searchInput.value?.blur?.();
  searchInput.value?.input?.blur?.();
  state.searchPage = 1;
  state.searchFinished = false;
  state.searchVideoResult = [];
  loadSearch(false);
}

const loadMoreSearch = () => {
  if (state.searchLoading || state.searchFinished || !state.searchText.trim()) {
    return;
  }
  state.searchPage += 1;
  loadSearch(true);
}

const tabChange = (name: string) => {
  console.log(name);
  switch (name) {
    case 'homepage':
      loadHomeVideos();
      break;
    case 'hot':
      if (state.hotVideoList.length === 0) {
        resetAndLoadHot();
      }
      break;
    case 'rank':
      loadRankVideos();
      break;
  }
}

const videoSelect = (type: string, id: any) => {
  console.log(`select video, type:${type}, id:${id}`);
  switch (type){
    case 'bv':
      state.videoConfig = { 'type': 'bv', 'id': id}
      break;
    case 'bangumi_ss':
      state.videoConfig = { 'type': 'bangumi_ss', 'id': id}
      break;
  }
  
}


onMounted(() => {
  loadHomeVideos();
  if (listContainer.value) {
    updateGridColumns(listContainer.value.clientWidth);
    listResizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        updateGridColumns(entry.contentRect.width);
      }
    });
    listResizeObserver.observe(listContainer.value);
  }
})

onUnmounted(() => {
  listResizeObserver?.disconnect();
  listResizeObserver = null;
})
</script>


<template>
  <div v-if="state.videoConfig" class="video-view">
      <BvPlayer :type="state.videoConfig.type" :on-close="() => state.videoConfig = null" :id="state.videoConfig.id"/>
  </div>

  <div ref="listContainer" class="bv-list" @scroll.passive="onListScroll">
    <el-tabs v-model="state.curTab" @tab-change="tabChange" class="tabs">
      <el-tab-pane label="首页" name="homepage">
        <div class="video-grid" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
          <BiliCover v-for="video of state.homeVideoList" :video="video" :on-click="(type, id) => videoSelect(type, id)" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="热门" name="hot">
        <div class="video-grid" v-loading="state.hotLoading" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
          <BiliCover v-for="video of state.hotVideoList" :video="video" :on-click="(type, id) => videoSelect(type, id)" />
        </div>
        <div v-if="state.hotLoading" class="hot-load-state">加载中...</div>
        <div v-else-if="state.hotFinished && state.hotVideoList.length > 0" class="hot-load-state">没有更多了</div>
      </el-tab-pane>

      <el-tab-pane label="排行榜" name="rank">
          <el-radio-group v-model="state.rankType" size="large"  @change="(v: string) => loadRankVideos()" class="rank-type">
            <el-radio-button v-for="item of rankTypes" :key="item.value" :label="item.label" :value="item.value" />
          </el-radio-group>
        <div class="video-grid" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
          <BiliCover v-for="video of state.rankVideoList" :video="video" :on-click="(type, id) => videoSelect(type, id)" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="搜索" name="search">
        <el-input ref="searchInput" class="search-input" v-model="state.searchText" size="large" placeholder="请输入搜索关键词" :prefix-icon="Search"  @keyup.enter="searchByText">
          <template #append>
            <el-button :icon="Search" @click="searchByText"/>
          </template>
        </el-input>
        <div class="video-grid" v-loading="state.searchLoading" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
          <BiliCover v-for="video of state.searchVideoResult" :video="video" :on-click="(type, id) => videoSelect(type, id)" />
        </div>
        <div v-if="state.searchLoading" class="hot-load-state">加载中...</div>
        <div v-else-if="state.searchFinished && state.searchVideoResult.length > 0" class="hot-load-state">没有更多了</div>
      </el-tab-pane>
      <el-tab-pane label="关注" name="关注">关注</el-tab-pane>
      <el-tab-pane label="我的" name="my">我的</el-tab-pane>
    </el-tabs>
    
  </div>
</template>


<style>
.search-input {
  font-size: 20px !important;
  margin: 20px;
  padding-right: 40px;
}

.bv-list {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  container-type: inline-size;
}

.video-view {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1000;
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

.hot-load-state {
  padding: 20px 0 28px;
  text-align: center;
  font-size: 22px;
  color: #64748b;
}

.video-grid {
  display: grid;
  gap: 18px;
  padding: 0 20px 20px 10px;
  align-items: start;
}
</style>

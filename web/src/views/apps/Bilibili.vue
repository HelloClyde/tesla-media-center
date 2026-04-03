<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue';
import { get, post } from '@/functions/requests'
import { Search } from '@element-plus/icons-vue'
import BiliCover from '@/components/BiliCover.vue';
import BvPlayer from '@/components/BvPlayer.vue';
import { ElMessage } from 'element-plus';

const searchInput = ref<any>(null);
const listContainer = ref<HTMLElement | null>(null);
let listResizeObserver: ResizeObserver | null = null;
let biliLoginPollTimer: number | null = null;

const state = reactive({
  videoConfig: null as any,
  homeVideoList: [] as any[],
  hotVideoList: [] as any[],
  hotPage: 1,
  hotPageSize: 20,
  hotLoading: false,
  hotFinished: false,
  followingList: [] as any[],
  followingLoading: false,
  favoriteFolders: [] as any[],
  favoriteFolderId: null as number | null,
  favoriteList: [] as any[],
  favoriteLoading: false,
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
  biliAuthLoading: false,
  biliLoginPolling: false,
  biliLoggedIn: false,
  biliProfile: null as any,
  biliQrCode: '',
  biliQrStatus: '',
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

const loadFollowingBangumi = () => {
  if (state.followingLoading) {
    return;
  }
  state.followingLoading = true;
  get('/api/bilibili/following/bangumi?pn=1&ps=30', '读取关注列表失败').then((data) => {
    state.followingList = data.list || [];
  }).finally(() => {
    state.followingLoading = false;
  });
}

const loadFavoriteContent = (mediaId?: number | null) => {
  const targetMediaId = mediaId ?? state.favoriteFolderId;
  if (!targetMediaId || state.favoriteLoading) {
    return;
  }
  state.favoriteLoading = true;
  get(`/api/bilibili/favorites/content?media_id=${targetMediaId}&page=1`, '读取收藏内容失败').then((data) => {
    state.favoriteFolderId = targetMediaId;
    state.favoriteList = data.list || [];
  }).finally(() => {
    state.favoriteLoading = false;
  });
}

const loadFavoriteFolders = () => {
  if (state.favoriteLoading) {
    return;
  }
  state.favoriteLoading = true;
  get('/api/bilibili/favorites/folders', '读取收藏夹失败').then((data) => {
    state.favoriteFolders = data || [];
    if (!state.favoriteFolderId && state.favoriteFolders.length > 0) {
      state.favoriteFolderId = state.favoriteFolders[0].id;
    }
  }).then(() => {
    if (state.favoriteFolderId) {
      return get(`/api/bilibili/favorites/content?media_id=${state.favoriteFolderId}&page=1`, '读取收藏内容失败').then((data) => {
        state.favoriteList = data.list || [];
      });
    }
    state.favoriteList = [];
  }).finally(() => {
    state.favoriteLoading = false;
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
    case '关注':
      loadFollowingBangumi();
      break;
    case 'favorite':
      loadFavoriteFolders();
      break;
    case 'my':
      loadBiliAuthStatus();
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

const stopBiliLoginPolling = () => {
  if (biliLoginPollTimer !== null) {
    window.clearInterval(biliLoginPollTimer);
    biliLoginPollTimer = null;
  }
  state.biliLoginPolling = false;
}

const loadBiliAuthStatus = () => {
  state.biliAuthLoading = true;
  return get('/api/bilibili/auth/status', '读取B站登录状态失败').then((data) => {
    state.biliLoggedIn = Boolean(data.loggedIn);
    state.biliProfile = data.profile || null;
    if (state.biliLoggedIn) {
      state.biliQrCode = '';
      state.biliQrStatus = '';
      stopBiliLoginPolling();
    }
  }).finally(() => {
    state.biliAuthLoading = false;
  });
}

const pollBiliLoginState = () => {
  if (state.biliLoginPolling) {
    return;
  }
  state.biliLoginPolling = true;
  biliLoginPollTimer = window.setInterval(() => {
    get('/api/bilibili/auth/qrcode/poll', '轮询扫码状态失败').then((data) => {
      state.biliQrStatus = data.status || '';
      if (data.loggedIn) {
        state.biliLoggedIn = true;
        state.biliProfile = data.profile || null;
        state.biliQrCode = '';
        ElMessage.success('B站登录成功');
        stopBiliLoginPolling();
      }
    }).catch((error) => {
      if (error?.status === 'qrcode_not_found') {
        state.biliQrCode = '';
        state.biliQrStatus = '';
      }
      stopBiliLoginPolling();
    });
  }, 2000);
}

const createBiliLoginQrCode = () => {
  state.biliAuthLoading = true;
  post('/api/bilibili/auth/qrcode', {}, '生成登录二维码失败').then((data) => {
    state.biliQrCode = data.qrcode;
    state.biliQrStatus = data.status || 'pending';
    state.biliLoggedIn = false;
    state.biliProfile = null;
    stopBiliLoginPolling();
    pollBiliLoginState();
  }).finally(() => {
    state.biliAuthLoading = false;
  });
}

const logoutBili = () => {
  state.biliAuthLoading = true;
  post('/api/bilibili/auth/logout', {}, '退出B站登录失败').then(() => {
    state.biliLoggedIn = false;
    state.biliProfile = null;
    state.biliQrCode = '';
    state.biliQrStatus = '';
    stopBiliLoginPolling();
    ElMessage.success('已退出 B 站登录');
  }).finally(() => {
    state.biliAuthLoading = false;
  });
}


onMounted(() => {
  loadHomeVideos();
  loadBiliAuthStatus();
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
  stopBiliLoginPolling();
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
      <el-tab-pane label="关注" name="关注">
        <div class="video-grid" v-loading="state.followingLoading" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
          <BiliCover v-for="video of state.followingList" :video="video" :on-click="(type, id) => videoSelect(type, id)" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="收藏" name="favorite">
        <div class="favorite-panel" v-loading="state.favoriteLoading">
          <el-radio-group v-if="state.favoriteFolders.length > 0" v-model="state.favoriteFolderId" class="favorite-folders" @change="(value: number) => loadFavoriteContent(value)">
            <el-radio-button v-for="folder of state.favoriteFolders" :key="folder.id" :label="folder.title" :value="folder.id" />
          </el-radio-group>
          <div class="video-grid favorite-grid" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
            <BiliCover v-for="video of state.favoriteList" :video="video" :on-click="(type, id) => videoSelect(type, id)" />
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="我的" name="my">
        <div class="bili-auth-panel" v-loading="state.biliAuthLoading">
          <template v-if="state.biliLoggedIn">
            <div class="bili-auth-head">
              <img v-if="state.biliProfile?.avatar" :src="state.biliProfile.avatar" class="bili-avatar" />
              <div>
                <div class="bili-auth-title">{{ state.biliProfile?.name || '已登录' }}</div>
                <div class="bili-auth-meta">UID {{ state.biliProfile?.uid || '-' }}</div>
                <div class="bili-auth-meta" v-if="state.biliProfile?.sign">{{ state.biliProfile.sign }}</div>
              </div>
            </div>
            <div class="button-row">
              <el-button type="danger" plain round @click="logoutBili">退出 B 站登录</el-button>
            </div>
          </template>
          <template v-else>
            <div class="bili-auth-title">扫码登录 B 站</div>
            <div class="bili-auth-meta">登录后可在“我的”页查看状态，并用于需要登录态的 B 站能力。</div>
            <div v-if="state.biliQrCode" class="bili-qr-wrap">
              <img :src="state.biliQrCode" class="bili-qr-image" />
              <div class="bili-auth-meta">状态：{{ state.biliQrStatus || 'pending' }}</div>
            </div>
            <div class="button-row">
              <el-button type="primary" round @click="createBiliLoginQrCode">生成二维码</el-button>
              <el-button v-if="state.biliQrCode" round @click="createBiliLoginQrCode">刷新二维码</el-button>
            </div>
          </template>
        </div>
      </el-tab-pane>
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
  display: flex;
  flex-wrap: nowrap;
  gap: 10px;
  overflow-x: auto;
  margin: 4px 20px 18px 10px;
  padding: 6px;
  scrollbar-width: none;
}

.rank-type::-webkit-scrollbar {
  display: none;
}

.rank-type :deep(.el-radio-button__inner) {
  min-width: max-content;
  padding: 10px 16px;
  border: none !important;
  border-radius: 999px !important;
  background: transparent;
  color: var(--color-text-soft);
  font-size: 18px !important;
  font-weight: 600;
  line-height: 1;
  box-shadow: none !important;
  transition: background 160ms ease, color 160ms ease, transform 160ms ease;
}

.rank-type :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, var(--color-accent-soft) 0%, color-mix(in srgb, var(--color-accent) 18%, var(--color-surface)) 100%);
  color: var(--color-accent);
  box-shadow: 0 10px 22px var(--color-shadow) !important;
}

.rank-type :deep(.el-radio-button:first-child .el-radio-button__inner),
.rank-type :deep(.el-radio-button:last-child .el-radio-button__inner) {
  border-radius: 999px !important;
}

.rank-type :deep(.el-radio-button) {
  display: inline-flex;
  border-radius: 999px;
  border: none !important;
  overflow: visible;
  background: transparent;
  box-shadow: none !important;
}

.rank-type :deep(.el-radio-button__inner::before) {
  display: none !important;
}

.rank-type :deep(.el-radio-button__original-radio) {
  appearance: none;
}

.rank-type :deep(.el-radio-button__inner:hover) {
  background: var(--color-panel-muted);
  color: var(--color-heading);
  transform: translateY(-1px);
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

.favorite-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.favorite-folders {
  margin: 0 20px 0 10px;
}

.favorite-grid {
  padding-top: 0;
}

.bili-auth-panel {
  margin: 16px 20px 24px 10px;
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
  box-shadow: 0 14px 28px var(--color-shadow);
}

.bili-auth-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.bili-avatar {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid var(--color-border);
}

.bili-auth-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-heading);
}

.bili-auth-meta {
  margin-top: 8px;
  color: var(--color-text-soft);
  font-size: 16px;
  line-height: 1.5;
}

.bili-qr-wrap {
  display: inline-flex;
  flex-direction: column;
  gap: 12px;
  margin: 20px 0;
}

.bili-qr-image {
  width: 240px;
  height: 240px;
  border-radius: 20px;
  background: #fff;
  padding: 12px;
  box-sizing: border-box;
}

.button-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
</style>

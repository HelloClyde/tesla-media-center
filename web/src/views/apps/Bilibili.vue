<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
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
  searchResultSections: [] as any[],
  searchActiveType: '',
  searchPage: 1,
  searchNextPage: null as number | null,
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
  biliCache: {
    cacheDir: '',
    maxSizeMb: 2048,
    sizeMb: 0,
    fileCount: 0,
    diskFreeMb: 0,
  },
  biliSettings: {
    maxSizeMb: 2048,
    maxQuality: '_720P',
    danmakuArea: 'top_half',
    danmakuMaxCount: 30,
    danmakuOpacity: 70,
  },
  biliSettingsLoading: false,
})

const SEARCH_SECTION_LABELS: Record<string, string> = {
  video: '视频',
  media_bangumi: '番剧',
  media_ft: '影视',
  bili_user: '用户',
  live_room: '直播间',
  article: '专栏',
  topic: '话题',
  photo: '相簿',
};

const getSearchItemKey = (item: any, fallbackIndex: number) => {
  return String(
    item?.bvid ||
    item?.season_id ||
    item?.roomid ||
    item?.mid ||
    item?.id ||
    item?.cv_id ||
    item?.article_id ||
    item?.dynamic_id ||
    `${item?.title || item?.uname || item?.author || 'item'}-${fallbackIndex}`
  );
}

const mergeSearchSections = (currentSections: any[], incomingSections: any[]) => {
  const mergedMap = new Map<string, any>();
  currentSections.forEach((section) => {
    mergedMap.set(section.result_type, {
      ...section,
      items: [...section.items],
    });
  });

  incomingSections.forEach((section) => {
    const existing = mergedMap.get(section.result_type);
    if (!existing) {
      mergedMap.set(section.result_type, {
        ...section,
        items: [...section.items],
      });
      return;
    }

    const seen = new Set(existing.items.map((item: any, index: number) => getSearchItemKey(item, index)));
    section.items.forEach((item: any, index: number) => {
      const key = getSearchItemKey(item, index);
      if (!seen.has(key)) {
        seen.add(key);
        existing.items.push(item);
      }
    });
  });

  return Array.from(mergedMap.values());
}

const normalizeSearchSections = (results: any[]) => {
  return results
    .filter((section: any) => Array.isArray(section?.data) && section.data.length > 0)
    .map((section: any) => ({
      result_type: section.result_type,
      title: SEARCH_SECTION_LABELS[section.result_type] || section.result_type,
      items: section.data,
    }));
}

const activeSearchSection = computed(() => {
  return state.searchResultSections.find((section: any) => section.result_type === state.searchActiveType) || null;
});

const biliCacheUsagePercent = computed(() => {
  const maxSizeMb = Number(state.biliCache.maxSizeMb) || 1;
  const sizeMb = Number(state.biliCache.sizeMb) || 0;
  return Math.min(100, Math.round((sizeMb / maxSizeMb) * 100));
});

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
    const normalizedSections = normalizeSearchSections(allReuslt);
    const incomingCount = normalizedSections.reduce((count: number, section: any) => count + section.items.length, 0);
    const currentPage = Number(data?.page) || state.searchPage;
    const nextPage = Number(data?.next);
    const pageSize = Number(data?.pagesize) || state.searchPageSize;
    const totalResults = Number(data?.numResults) || 0;
    const totalPages = pageSize > 0 && totalResults > 0 ? Math.ceil(totalResults / pageSize) : 0;
    if (append) {
      state.searchResultSections = mergeSearchSections(state.searchResultSections, normalizedSections);
    } else {
      state.searchResultSections = normalizedSections;
    }
    if (!state.searchActiveType || !state.searchResultSections.some((section: any) => section.result_type === state.searchActiveType)) {
      state.searchActiveType = state.searchResultSections[0]?.result_type || '';
    }
    state.searchNextPage = Number.isFinite(nextPage) && nextPage > currentPage ? nextPage : null;
    state.searchFinished = normalizedSections.length === 0
      || incomingCount === 0
      || (state.searchNextPage === null && totalPages > 0 && currentPage >= totalPages)
      || (state.searchNextPage === null && totalPages === 0);
  }).finally(() => {
    state.searchLoading = false;
  })
}

const searchByText = () => {
  searchInput.value?.blur?.();
  searchInput.value?.input?.blur?.();
  state.searchPage = 1;
  state.searchNextPage = null;
  state.searchFinished = false;
  state.searchResultSections = [];
  state.searchActiveType = '';
  loadSearch(false);
}

const loadMoreSearch = () => {
  if (state.searchLoading || state.searchFinished || !state.searchText.trim()) {
    return;
  }
  state.searchPage = state.searchNextPage ?? (state.searchPage + 1);
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
      loadBiliSettings();
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
    default:
      ElMessage.info('当前类型已支持展示，暂不支持进一步打开');
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

const loadBiliSettings = () => {
  state.biliSettingsLoading = true;
  return Promise.all([
    get('/api/bilibili/cache', '读取B站缓存信息失败'),
    get('/api/config', '读取B站配置失败'),
  ]).then(([cacheData, configData]) => {
    state.biliCache = cacheData;
    state.biliSettings.maxSizeMb = cacheData.maxSizeMb || 2048;
    state.biliSettings.maxQuality = configData.bilibili_max_quality || '_720P';
    state.biliSettings.danmakuArea = configData.bilibili_danmaku_area || 'top_half';
    state.biliSettings.danmakuMaxCount = Number(configData.bilibili_danmaku_max_count) || 30;
    state.biliSettings.danmakuOpacity = Number(configData.bilibili_danmaku_opacity) || 70;
  }).finally(() => {
    state.biliSettingsLoading = false;
  });
}

const saveBiliSettings = () => {
  state.biliSettingsLoading = true;
  post('/api/bilibili/cache/settings', {
    maxSizeMb: state.biliSettings.maxSizeMb,
  }, '保存B站缓存配置失败').then((cacheData) => {
    state.biliCache = cacheData;
    state.biliSettings.maxSizeMb = cacheData.maxSizeMb;
    return post('/api/config', {
      bilibili_max_quality: state.biliSettings.maxQuality,
      bilibili_danmaku_area: state.biliSettings.danmakuArea,
      bilibili_danmaku_max_count: state.biliSettings.danmakuMaxCount,
      bilibili_danmaku_opacity: state.biliSettings.danmakuOpacity,
    }, '保存B站播放配置失败');
  }).then(() => {
    ElMessage.success('B站设置已保存');
  }).finally(() => {
    state.biliSettingsLoading = false;
  });
}

const clearBiliCache = () => {
  state.biliSettingsLoading = true;
  post('/api/bilibili/cache/clear', {}, '清理B站缓存失败').then((cacheData) => {
    state.biliCache = cacheData;
    state.biliSettings.maxSizeMb = cacheData.maxSizeMb;
    const deletedSizeMb = cacheData.cleanup?.deletedSizeMb ?? 0;
    ElMessage.success(`缓存已清理，释放 ${deletedSizeMb} MB`);
  }).finally(() => {
    state.biliSettingsLoading = false;
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
  loadBiliSettings();
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
        <div class="search-panel" v-loading="state.searchLoading">
          <el-tabs v-if="state.searchResultSections.length > 0" v-model="state.searchActiveType" class="search-type-tabs">
            <el-tab-pane v-for="section of state.searchResultSections" :key="section.result_type" :name="section.result_type">
              <template #label>
                <span class="search-tab-label">{{ section.title }} <em>{{ section.items.length }}</em></span>
              </template>
            </el-tab-pane>
          </el-tabs>
          <section v-if="activeSearchSection" class="search-section">
            <div class="search-section-head">
              <h3>{{ activeSearchSection.title }}</h3>
              <span>{{ activeSearchSection.items.length }} 条</span>
            </div>
            <div class="video-grid search-grid" :style="{ gridTemplateColumns: `repeat(${state.gridColumns}, minmax(0, 1fr))` }">
              <BiliCover v-for="item of activeSearchSection.items" :key="item.bvid || item.season_id || item.roomid || item.mid || item.id || item.cv_id || item.title" :video="item" :on-click="(type, id) => videoSelect(type, id)" />
            </div>
          </section>
        </div>
        <div v-if="state.searchLoading" class="hot-load-state">加载中...</div>
        <div v-else-if="state.searchFinished && state.searchResultSections.length > 0" class="hot-load-state">没有更多了</div>
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
        <div class="bili-my-layout">
          <section class="bili-my-section">
            <div class="bili-section-copy">
              <p class="bili-section-kicker">Account</p>
              <h3>账号</h3>
              <p class="bili-auth-meta">管理登录状态，查看当前 B 站账户信息。</p>
            </div>
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
          </section>

          <section class="bili-my-section">
            <div class="bili-section-copy">
              <p class="bili-section-kicker">Playback</p>
              <h3>播放与缓存</h3>
              <p class="bili-auth-meta">统一管理缓存容量、取流清晰度和弹幕展示策略。</p>
            </div>
            <div class="bili-auth-panel bili-settings-panel" v-loading="state.biliSettingsLoading">
            <div class="bili-settings-head">
              <div>
                <div class="bili-auth-title">B站设置</div>
                <div class="bili-auth-meta">缓存、取流和弹幕体验统一放在这里。</div>
              </div>
              <div class="bili-usage-pill">{{ biliCacheUsagePercent }}%</div>
            </div>

            <div class="bili-metric-row">
              <div class="bili-metric-box">
                <span class="bili-metric-label">当前占用</span>
                <strong>{{ state.biliCache.sizeMb }} MB</strong>
              </div>
              <div class="bili-metric-box">
                <span class="bili-metric-label">缓存上限</span>
                <strong>{{ state.biliCache.maxSizeMb }} MB</strong>
              </div>
              <div class="bili-metric-box">
                <span class="bili-metric-label">缓存文件</span>
                <strong>{{ state.biliCache.fileCount }}</strong>
              </div>
              <div class="bili-metric-box">
                <span class="bili-metric-label">磁盘剩余</span>
                <strong>{{ state.biliCache.diskFreeMb }} MB</strong>
              </div>
            </div>

            <div class="bili-progress-track">
              <div class="bili-progress-fill" :style="{ width: `${biliCacheUsagePercent}%` }"></div>
            </div>

            <div class="bili-setting-line">
              <span class="bili-metric-label">缓存目录</span>
              <code class="bili-setting-value">{{ state.biliCache.cacheDir || '-' }}</code>
            </div>

            <div class="bili-settings-grid">
              <div class="bili-setting-input">
                <span class="bili-metric-label">缓存上限</span>
                <div class="button-row">
                  <el-input-number v-model="state.biliSettings.maxSizeMb" :min="256" :step="256" :max="102400" />
                  <span class="bili-setting-unit">MB</span>
                </div>
              </div>
              <div class="bili-setting-input">
                <span class="bili-metric-label">最高分辨率</span>
                <el-select v-model="state.biliSettings.maxQuality" placeholder="选择最高分辨率" style="width: 220px">
                  <el-option label="360P" value="_360P" />
                  <el-option label="480P" value="_480P" />
                  <el-option label="720P" value="_720P" />
                  <el-option label="1080P" value="_1080P" />
                  <el-option label="1080P 高码率" value="_1080P_PLUS" />
                  <el-option label="1080P 60帧" value="_1080P_60" />
                  <el-option label="4K" value="_4K" />
                </el-select>
              </div>
              <div class="bili-setting-input">
                <span class="bili-metric-label">弹幕位置</span>
                <el-select v-model="state.biliSettings.danmakuArea" placeholder="选择弹幕区域" style="width: 220px">
                  <el-option label="顶部 1/3" value="top_third" />
                  <el-option label="顶部 1/2" value="top_half" />
                  <el-option label="底部 1/2" value="bottom_half" />
                  <el-option label="全屏" value="full" />
                </el-select>
              </div>
              <div class="bili-setting-input">
                <span class="bili-metric-label">同屏最大弹幕数</span>
                <div class="button-row">
                  <el-input-number v-model="state.biliSettings.danmakuMaxCount" :min="5" :step="5" :max="100" />
                  <span class="bili-setting-unit">条</span>
                </div>
              </div>
              <div class="bili-setting-input bili-setting-input--wide">
                <span class="bili-metric-label">弹幕透明度</span>
                <div class="button-row">
                  <el-slider v-model="state.biliSettings.danmakuOpacity" :min="10" :max="100" :step="5" style="width: 220px" />
                  <span class="bili-setting-unit">{{ state.biliSettings.danmakuOpacity }}%</span>
                </div>
              </div>
            </div>

            <div class="button-row">
              <el-button type="primary" round @click="saveBiliSettings">保存设置</el-button>
              <el-button type="danger" plain round @click="clearBiliCache">一键清理缓存</el-button>
            </div>
            </div>
          </section>
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

.search-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.search-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.search-type-tabs {
  margin: 0 20px 0 10px;
}

.search-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.search-tab-label em {
  font-style: normal;
  color: var(--color-text-soft);
  font-size: 14px;
}

.search-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 0 20px 0 10px;
}

.search-section-head h3 {
  margin: 0;
  font-size: 24px;
  color: var(--color-heading);
}

.search-section-head span {
  color: var(--color-text-soft);
  font-size: 16px;
}

.search-grid {
  padding-top: 0;
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

.bili-my-layout {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 0;
  align-items: start;
}

.bili-my-section {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.bili-section-copy {
  margin: 16px 20px 0 10px;
  padding: 0 4px;
}

.bili-section-kicker {
  margin: 0 0 6px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-text-soft);
}

.bili-section-copy h3 {
  margin: 0;
  font-size: 24px;
  line-height: 1.2;
  color: var(--color-heading);
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

.bili-settings-panel {
  min-width: 0;
}

.bili-settings-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.bili-usage-pill {
  min-width: 64px;
  padding: 8px 14px;
  border-radius: 999px;
  background: var(--color-accent-soft);
  color: var(--color-accent);
  text-align: center;
  font-weight: 600;
}

.bili-metric-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.bili-metric-box {
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--color-panel-muted);
  border: 1px solid var(--color-border);
}

.bili-metric-label {
  display: block;
  margin-bottom: 6px;
  color: var(--color-text-soft);
  font-size: 13px;
}

.bili-metric-box strong {
  color: var(--color-heading);
  font-size: 20px;
  font-weight: 600;
}

.bili-progress-track {
  height: 10px;
  border-radius: 999px;
  background: var(--color-background-mute);
  overflow: hidden;
  margin-bottom: 16px;
}

.bili-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--color-accent) 0%, #53a8ff 100%);
}

.bili-setting-line {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--color-panel-muted);
  border: 1px solid var(--color-border);
  margin-bottom: 16px;
}

.bili-setting-value {
  color: var(--color-heading);
  word-break: break-all;
}

.bili-settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 18px;
}

.bili-setting-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bili-setting-input--wide {
  grid-column: 1 / -1;
}

.bili-setting-unit {
  color: var(--color-text-soft);
  align-self: center;
}

@media (max-width: 1120px) {
  .bili-my-layout {
    grid-template-columns: 1fr;
  }

  .bili-metric-row,
  .bili-settings-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .bili-metric-row,
  .bili-settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>

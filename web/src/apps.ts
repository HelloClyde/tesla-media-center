import { markRaw, type Component } from 'vue';
import { VideoPlay, Monitor } from '@element-plus/icons-vue';

export interface AppEntry {
  route: string;
  label: string;
  description: string;
  icon: string | Component;
  color: string;
  badge?: string;
  keywords: string;
}

// The launcher and sidebar share this catalog so new applications stay in sync.
export const applications: AppEntry[] = [
  { route: '/apps/wqzb', label: '玩球直播', description: '选择直播间观看体育直播', icon: '/icon/WQZB_LOGO.png', color: '#3b81e5', keywords: '玩球 体育 直播 足球 篮球 wqzb' },
  { route: '/apps/douyin', label: '抖音', description: '发现、搜索和播放公开短视频', icon: '/icon/DOUYIN_LOGO.svg', color: '#fe2c55', badge: '实验', keywords: '抖音 短视频 douyin' },
  { route: '/apps/amap', label: '高德导航', description: '路线规划与行程导航', icon: '/icon/AMAP_LOGO.ico', color: '#1595e7', badge: '实验', keywords: '地图 导航 amap' },
  { route: '/apps/tesla', label: '特斯拉', description: '查看车辆状态', icon: '/icon/TESLA_LOGO.svg', color: '#d24c59', keywords: '车辆 tesla' },
  { route: '/apps/qqmusic', label: 'QQ 音乐', description: '发现音乐，随心播放', icon: '/icon/QQMUSIC_LOGO.ico', color: '#13ac7b', keywords: '歌曲 音乐 qq' },
  { route: '/apps/bilibili', label: '哔哩哔哩', description: '浏览和播放喜欢的视频', icon: '/icon/BILIBILI_LOGO.svg', color: '#20a5d6', keywords: '视频 b站 bilibili' },
  { route: '/apps/tencent-video', label: '腾讯视频', description: '发现、搜索和播放视频', icon: '/icon/TENCENT_VIDEO_LOGO.png', color: '#15b86a', keywords: '腾讯 视频 qq tencent' },
  { route: '/apps/gba', label: 'GBA', description: '重温 GBA 经典游戏', icon: '/icon/GBA_LOGO.webp', color: '#8571cf', keywords: 'gba 游戏' },
  { route: '/apps/gam4980', label: 'GAM4980', description: '打开 GAM 经典掌机游戏', icon: '/icon/GAM4980_LOGO.webp', color: '#167c60', keywords: 'gam4980 bbk 文曲星 游戏 掌机' },
  { route: '/apps/video', label: '本地播放器', description: '浏览和播放本地媒体', icon: markRaw(VideoPlay), color: '#d29043', keywords: '视频 文件 播放器' },
  { route: '/apps/debug', label: '设置与调试', description: '应用设置与设备测试', icon: markRaw(Monitor), color: '#6a829d', keywords: '设置 调试 测试 debug' },
];

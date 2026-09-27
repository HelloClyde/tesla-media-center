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
  { route: '/apps/amap', label: '高德导航', description: '路线规划与行程导航', icon: '/icon/AMAP_LOGO.ico', color: '#1595e7', badge: '实验', keywords: '地图 导航 amap' },
  { route: '/apps/tesla', label: '特斯拉', description: '查看车辆状态', icon: '/icon/TESLA_LOGO.svg', color: '#d24c59', keywords: '车辆 tesla' },
  { route: '/apps/qqmusic', label: 'QQ 音乐', description: '发现音乐，随心播放', icon: '/icon/QQMUSIC_LOGO.ico', color: '#13ac7b', keywords: '歌曲 音乐 qq' },
  { route: '/apps/bilibili', label: '哔哩哔哩', description: '浏览和播放喜欢的视频', icon: '/icon/BILIBILI_LOGO.svg', color: '#20a5d6', keywords: '视频 b站 bilibili' },
  { route: '/apps/gba', label: '游戏', description: '重温 GBA 经典游戏', icon: '/icon/GBA_LOGO.svg', color: '#8571cf', keywords: 'gba 游戏' },
  { route: '/apps/video', label: '本地播放器', description: '浏览和播放本地媒体', icon: markRaw(VideoPlay), color: '#d29043', keywords: '视频 文件 播放器' },
  { route: '/apps/debug', label: '设置与调试', description: '应用设置与设备测试', icon: markRaw(Monitor), color: '#6a829d', keywords: '设置 调试 测试 debug' },
];

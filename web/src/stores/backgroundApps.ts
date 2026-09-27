import { shallowReactive } from 'vue';

export interface BackgroundApp {
  id: string;
  name: string;
  route: string;
  icon: string;
  detail?: string;
  running: boolean;
  open?: () => void;
}
// Background-capable applications register on start, update their entry when
// state changes, and remove it when their background session ends.
export const backgroundApps = shallowReactive<Record<string, BackgroundApp>>({});
export function updateBackgroundApp(app: BackgroundApp) { backgroundApps[app.id] = app; }
export function removeBackgroundApp(id: string) { delete backgroundApps[id]; }

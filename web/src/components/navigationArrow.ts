import assets from './navigationArrowAssets.json';

// APK TripNaviManeuverUtil -> CarImageUtil.DRIVE_ARROW_ICON. Route maneuvers
// have their own numbering; use their semantics, not the raw v5.1 actionCode.
export const navigationManeuvers = {
  left: {text: '左转', icon: 2}, right: {text: '右转', icon: 3},
  'bear-left': {text: '靠左行驶', icon: 4}, 'bear-right': {text: '靠右行驶', icon: 5},
  'sharp-left': {text: '向左后方转弯', icon: 6}, 'sharp-right': {text: '向右后方转弯', icon: 7},
  'uturn-left': {text: '掉头', icon: 8}, 'uturn-right': {text: '向右掉头', icon: 19},
  straight: {text: '继续直行', icon: 9},
  'fork-left': {text: '走左侧岔路', icon: 65}, 'fork-middle': {text: '走中间岔路', icon: 9},
  'fork-right': {text: '走右侧岔路', icon: 66},
  'roundabout-enter': {text: '进入环岛', icon: 11}, 'roundabout-exit': {text: '驶出环岛', icon: 12},
  destination: {text: '到达目的地附近', icon: 15},
} as const;
export type NavigationManeuver = keyof typeof navigationManeuvers;
export function isNavigationManeuver(value: string): value is NavigationManeuver {
  return Object.prototype.hasOwnProperty.call(navigationManeuvers, value);
}

// Keep old background-navigation state readable while all current instructions
// use semantic actions rather than identifying an icon by its Chinese text.
const legacyIcons: Record<string, number> = {'↰': 2, '↱': 3, '↶': 8, '↑': 9, '⚑': 15, '⟳': 11};

export function navigationArrowAsset(arrow: string): string {
  const id = isNavigationManeuver(arrow) ? navigationManeuvers[arrow].icon
    : Object.prototype.hasOwnProperty.call(legacyIcons, arrow) ? legacyIcons[arrow] : 0;
  return (assets as Record<string, string>)[id];
}

export const MAX_SIDEBAR_APPS = 7;
export function placeSidebarApp(current: string[], route: string, before: string | null = null) {
  const existing = current.includes(route);
  const routes = current.filter(item => item !== route).slice(0, MAX_SIDEBAR_APPS);
  const target = before ? routes.indexOf(before) : -1;
  if (!existing && routes.length === MAX_SIDEBAR_APPS) {
    routes.splice(target < 0 ? routes.length - 1 : target, 1, route);
  } else {
    routes.splice(target < 0 ? routes.length : target, 0, route);
  }
  return routes;
}

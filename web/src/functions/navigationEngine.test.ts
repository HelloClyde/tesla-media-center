// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest';
beforeEach(() => { localStorage.clear(); vi.resetModules(); });
it('migrates the removed native engine to route fusion and persists it', async () => {
 localStorage.setItem('tmc:navigation-engine','amap-vdr');
 const {navigationEngine}=await import('./navigationEngine');
 expect(navigationEngine.value).toBe('route-fusion');
 expect(localStorage.getItem('tmc:navigation-engine')).toBe('route-fusion');
});
it('preserves browser selection and supports switching to fusion', async () => {
 const {navigationEngine,setNavigationEngine}=await import('./navigationEngine');
 expect(navigationEngine.value).toBe('browser');
 setNavigationEngine('route-fusion');
 expect(localStorage.getItem('tmc:navigation-engine')).toBe('route-fusion');
});

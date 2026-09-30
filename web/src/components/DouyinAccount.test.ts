// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises, DOMWrapper } from '@vue/test-utils';
import DouyinAccount from './DouyinAccount.vue';
const response = (data: unknown) => ({ok:true,json:async()=>({status:'ok',data})});
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers();});
it('cancels server QR waiting and stops polls on close', async()=>{
 vi.useFakeTimers();
 const fetch=vi.fn().mockImplementation(async(url:string, options:any)=>response(url.endsWith('/qrcode') ? {state:options.method==='POST'?'loading':'waiting',qrcode:'data:image/png;base64,AA=='}:{loggedIn:false}));
 vi.stubGlobal('fetch',fetch);
 const view=mount(DouyinAccount,{attachTo:document.body});await flushPromises();
 await view.get('.account-trigger').trigger('click');await flushPromises();
 expect(new DOMWrapper(document.body).get('img').attributes('src')).toContain('data:image/png');
 await new DOMWrapper(document.body).get('[aria-label="关闭登录"]').trigger('click');await flushPromises();
 const count=fetch.mock.calls.length;
 await vi.advanceTimersByTimeAsync(10000);
 expect(fetch).toHaveBeenCalledTimes(count);
 expect(fetch.mock.calls[fetch.mock.calls.length - 1][1].method).toBe('DELETE');view.unmount();
});
it('restores login state and disconnects',async()=>{
 const fetch=vi.fn().mockResolvedValue(response({loggedIn:true}));vi.stubGlobal('fetch',fetch);
 const view=mount(DouyinAccount,{attachTo:document.body});await flushPromises();
 expect(view.get('.account-trigger').text()).toBe('已登录抖音');
 await view.get('.account-trigger').trigger('click');
 await new DOMWrapper(document.body).findAll('button').find(b=>b.text()==='退出当前连接')!.trigger('click');await flushPromises();
 expect(view.get('.account-trigger').text()).toBe('登录抖音');expect(view.emitted('changed')).toHaveLength(1);view.unmount();
});
it('updates the parent only after confirmed login',async()=>{
 const fetch=vi.fn().mockImplementation(async(url:string,options:any)=>response(url.endsWith('/qrcode')?{state:options.method==='GET'?'confirmed':'loading'}:{loggedIn:false}));
 vi.stubGlobal('fetch',fetch);const view=mount(DouyinAccount,{attachTo:document.body});await flushPromises();
 await view.get('.account-trigger').trigger('click');await flushPromises();
 expect(view.get('.account-trigger').text()).toBe('已登录抖音');expect(view.emitted('changed')).toHaveLength(1);view.unmount();
});


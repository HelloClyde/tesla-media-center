import { beforeEach, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'
import { requireTmcSession } from './auth'

const get = vi.hoisted(() => vi.fn())
vi.mock('axios', () => ({ default: { get } }))

const route = (name: string, fullPath: string) => ({ name, fullPath }) as RouteLocationNormalized

beforeEach(() => get.mockReset())

it('opens the login page without checking the session', async () => {
  expect(await requireTmcSession(route('login', '/login'))).toBe(true)
  expect(get).not.toHaveBeenCalled()
})

it('blocks protected pages until the server confirms a session', async () => {
  get.mockResolvedValue({ data: { status: 'need_login' } })
  expect(await requireTmcSession(route('home', '/apps/home'))).toEqual({
    name: 'login', query: { redirect: '/apps/home' },
  })
  expect(get).toHaveBeenCalledWith('/api/config', { timeout: 10000 })
})

it('preserves the requested app when login is required', async () => {
  get.mockResolvedValue({ data: { status: 'need_login' } })
  expect(await requireTmcSession(route('amap-app', '/apps/amap'))).toEqual({
    name: 'login', query: { redirect: '/apps/amap' },
  })
})

it('allows a protected page when the session is valid', async () => {
  get.mockResolvedValue({ data: { status: 'ok' } })
  expect(await requireTmcSession(route('home', '/apps/home'))).toBe(true)
})

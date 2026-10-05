import axios from 'axios'
import type { RouteLocationNormalized } from 'vue-router'

export async function requireTmcSession(to: RouteLocationNormalized) {
  if (to.name === 'login') return true

  try {
    const response = await axios.get('/api/config', { timeout: 10000 })
    if (response.data?.status === 'ok') return true
  } catch {
    // An unavailable session check must not render a protected app page.
  }

  return { name: 'login', query: { redirect: to.fullPath } }
}

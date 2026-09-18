import { defineStore } from 'pinia'
import type { TokenPair, UserRead } from '~/types/api'

/**
 * Auth state: JWT access/refresh tokens (persisted as cookies, SSR-safe) and
 * the current user profile. Registration always creates a buyer account
 * server-side — there is no "choose your role" field here by design.
 */
export const useAuthStore = defineStore('auth', () => {
  const accessToken = useCookie<string | null>('access_token', { default: () => null, sameSite: 'lax', maxAge: 60 * 60 * 24 * 30 })
  const refreshToken = useCookie<string | null>('refresh_token', { default: () => null, sameSite: 'lax', maxAge: 60 * 60 * 24 * 30 })
  const user = ref<UserRead | null>(null)

  const isAuthenticated = computed(() => !!accessToken.value)
  const apiBase = useApiBase()

  function setTokens(tokens: TokenPair) {
    accessToken.value = tokens.access_token
    refreshToken.value = tokens.refresh_token
  }

  function clear() {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
  }

  async function fetchMe() {
    if (!accessToken.value) return
    try {
      user.value = await $fetch<UserRead>('/users/me', {
        baseURL: apiBase,
        headers: { Authorization: `Bearer ${accessToken.value}` },
      })
    } catch {
      clear()
    }
  }

  async function login(phone: string, password: string) {
    const tokens = await $fetch<TokenPair>('/auth/login', {
      baseURL: apiBase,
      method: 'POST',
      body: { phone, password },
    })
    setTokens(tokens)
    await fetchMe()
  }

  async function register(phone: string, password: string, email: string) {
    const tokens = await $fetch<TokenPair>('/auth/register', {
      baseURL: apiBase,
      method: 'POST',
      body: { phone, password, email },
    })
    setTokens(tokens)
    await fetchMe()
  }

  async function forgotPassword(phone: string) {
    await $fetch('/auth/forgot-password', {
      baseURL: apiBase,
      method: 'POST',
      body: { phone },
    })
  }

  async function resetPassword(phone: string, code: string, newPassword: string) {
    await $fetch('/auth/reset-password', {
      baseURL: apiBase,
      method: 'POST',
      body: { phone, code, new_password: newPassword },
    })
  }

  async function acceptCourierInvitation(phone: string, code: string, newPassword: string) {
    await $fetch('/auth/accept-courier-invitation', {
      baseURL: apiBase,
      method: 'POST',
      body: { phone, code, new_password: newPassword },
    })
  }

  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const tokens = await $fetch<TokenPair>('/auth/refresh', {
        baseURL: apiBase,
        method: 'POST',
        body: { refresh_token: refreshToken.value },
      })
      setTokens(tokens)
      return true
    } catch {
      clear()
      return false
    }
  }

  function logout() {
    clear()
  }

  return {
    accessToken,
    refreshToken,
    user,
    isAuthenticated,
    login,
    register,
    logout,
    fetchMe,
    tryRefresh,
    setTokens,
    forgotPassword,
    resetPassword,
    acceptCourierInvitation,
  }
})

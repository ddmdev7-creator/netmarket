import type { FetchOptions } from 'ofetch'
import type { ApiError } from '~/types/api'

/**
 * Authenticated API client: attaches the current access token, and on a 401
 * transparently retries once after a token refresh (see stores/auth.ts).
 *
 * Any 401 that can't be resolved by that refresh — no refresh token to try,
 * or the refresh itself fails — always sends the user to /connexion. Before
 * this, a 401 with no refresh token fell straight through to `throw error`
 * with no redirect at all: the calling page's useAsyncData swallows that
 * into a silent `.error`, so the user was left looking at a blank/broken
 * page with no indication they needed to log back in.
 */
export function useApi() {
  const apiBase = useApiBase()
  const auth = useAuthStore()
  const route = useRoute()
  const nuxtApp = useNuxtApp()

  async function redirectToLogin() {
    auth.logout()
    // navigateTo() reads the current Nuxt instance — safe here only because
    // we grabbed `nuxtApp` synchronously above. Called bare, this runs after
    // the `await`s in apiFetch's catch block below, by which point that
    // implicit context is gone (NUXT_E1001), and useAsyncData quietly turns
    // that context error into the page's own error instead of redirecting.
    await nuxtApp.runWithContext(() => navigateTo({ path: '/connexion', query: { redirect: route.fullPath } }))
  }

  async function apiFetch<T>(path: string, options: FetchOptions<'json'> = {}, _retried = false): Promise<T> {
    const headers = new Headers(options.headers as HeadersInit | undefined)
    if (auth.accessToken) headers.set('Authorization', `Bearer ${auth.accessToken}`)

    try {
      return await $fetch<T>(path, {
        baseURL: apiBase,
        ...options,
        headers,
      })
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status
      if (status === 401 && !_retried) {
        const refreshed = auth.refreshToken ? await auth.tryRefresh() : false
        if (refreshed) return apiFetch<T>(path, options, true)
        await redirectToLogin()
      }
      throw error
    }
  }

  /**
   * For endpoints that return raw bytes (courier verification documents —
   * see app/couriers/router.py's GET /{courier_id}/documents/{key}, never
   * public unlike product images). A plain `<img src>` can't authenticate
   * itself (no cookie, the token lives in memory — see auth.accessToken
   * above), so the caller fetches the blob here and builds an object URL.
   * No 401-retry-on-refresh here unlike apiFetch: this is only used for a
   * handful of images during an active admin review session, not worth the
   * complexity for that edge case.
   */
  async function apiFetchBlob(path: string): Promise<Blob> {
    const headers = new Headers()
    if (auth.accessToken) headers.set('Authorization', `Bearer ${auth.accessToken}`)
    return await $fetch<Blob>(path, { baseURL: apiBase, headers, responseType: 'blob' })
  }

  return { apiFetch, apiFetchBlob }
}

/** Extracts the French error message the backend puts in {"detail": "..."}. */
export function apiErrorMessage(error: unknown, fallback = 'Une erreur est survenue. Veuillez réessayer.'): string {
  const data = (error as { data?: ApiError })?.data
  return data?.detail || fallback
}

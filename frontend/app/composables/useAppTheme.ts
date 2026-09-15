import { useTheme } from 'vuetify'

export type AppThemeName = 'light' | 'dark'

const VUETIFY_THEME_NAME: Record<AppThemeName, string> = {
  light: 'daylight',
  dark: 'nocturne',
}

const THEME_COLOR: Record<AppThemeName, string> = {
  light: '#F3F4F6',
  dark: '#121214',
}

/**
 * Drives both the Vuetify theme and the `data-theme` attribute (which our
 * hand-written CSS variables in assets/styles/main.css key off) from a
 * single cookie-backed preference. useCookie is SSR-aware, so the server
 * already renders with the visitor's stored preference — no light-then-dark
 * flash on reload like a client-only localStorage toggle would cause.
 */
export function useAppTheme() {
  const theme = useCookie<AppThemeName>('theme', {
    default: () => 'light',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  const vuetifyTheme = useTheme()

  const apply = (value: AppThemeName) => {
    vuetifyTheme.global.name.value = VUETIFY_THEME_NAME[value]
  }

  apply(theme.value)
  watch(theme, apply)

  useHead(() => ({
    htmlAttrs: { 'data-theme': theme.value },
    meta: [{ name: 'theme-color', content: THEME_COLOR[theme.value] }],
  }))

  const toggle = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, toggle }
}

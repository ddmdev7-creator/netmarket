/**
 * "Daylight" light theme — primary/gray/white palette (à la Ozon), default
 * theme of the app. Blue brand primary shared with the "nocturne" dark theme
 * (app/theme/nocturne.ts), just re-tuned for a white/light-gray surface
 * instead of a near-black one. Orange (--color-accent in main.css) is kept
 * separate and deliberately narrow — product price and star ratings only,
 * not a Vuetify theme color. Users can switch to "nocturne" at runtime (see
 * app/composables/useAppTheme.ts) — keep both files' color intent in sync
 * when retuning the brand primary.
 */
import type { ThemeDefinition } from 'vuetify'

export const daylightTheme: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#F3F4F6',
    surface: '#FFFFFF',
    'surface-bright': '#FFFFFF',
    'surface-variant': '#F0F1F3',
    'on-surface-variant': '#6E7079',
    primary: '#0A66F5',
    'primary-darken-1': '#0850C4',
    secondary: '#6E7079',
    error: '#E5484D',
    info: '#4C9FE0',
    success: '#3DA35D',
    warning: '#E3A008',
  },
  variables: {
    'border-color': '#14151A',
    'border-opacity': 0.08,
    'high-emphasis-opacity': 0.87,
    'medium-emphasis-opacity': 0.6,
  },
}

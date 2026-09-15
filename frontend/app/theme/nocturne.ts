/**
 * "Nocturne" dark theme — optional dark mode, toggled at runtime (see
 * app/composables/useAppTheme.ts). "Daylight" (app/theme/daylight.ts) is now
 * the default. Blue brand primary shared with daylight; orange
 * (--color-accent in main.css) stays outside the Vuetify theme, reserved for
 * product price/star ratings only.
 */
import type { ThemeDefinition } from 'vuetify'

export const nocturneTheme: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#121214',
    // Nettement plus clair que le fond (#1A1A1D était trop proche de #121214
    // pour qu'une ombre seule se voie) — sur fond très sombre, c'est l'écart
    // de luminosité entre carte et page qui fait "lire" l'élévation, pas
    // l'ombre à elle seule.
    surface: '#222227',
    'surface-bright': '#2C2C33',
    'surface-variant': '#2C2C33',
    'on-surface-variant': '#B4B4BD',
    primary: '#0A66F5',
    'primary-darken-1': '#0850C4',
    secondary: '#8F8F99',
    error: '#E5484D',
    info: '#4C9FE0',
    success: '#3DA35D',
    warning: '#E3A008',
  },
  variables: {
    'border-color': '#FFFFFF',
    'border-opacity': 0.08,
    'high-emphasis-opacity': 0.95,
    'medium-emphasis-opacity': 0.65,
  },
}

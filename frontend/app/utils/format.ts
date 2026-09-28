const gnfFormatter = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })

/** Formats an integer GNF amount as "250 000 GNF" (no decimals, ever). */
export function formatGnf(amount: number): string {
  return `${gnfFormatter.format(amount)} GNF`
}

/**
 * Turns a Product.images entry into something an <img> can load. Entries
 * are either a bare object key returned by POST /uploads/images (proxied
 * through the API — see backend/app/uploads/router.py) or a full external
 * URL a vendor pasted manually (see ProductForm.vue's "add a URL" option) —
 * the latter is passed through untouched. `apiBase` should come from
 * useApiBase() at the call site, since resolving it here would make this a
 * composable instead of a plain util.
 */
export function resolveImageUrl(value: string, apiBase: string, width?: number): string {
  if (value.startsWith('http')) return value
  // width : version réduite (WebP si le navigateur l'accepte) générée et mise
  // en cache par l'API — voir GET /uploads/images/{key}?w=… (160/320/480/800).
  return `${apiBase}/uploads/images/${value}${width ? `?w=${width}` : ''}`
}

/** srcset pour une photo affichée à des tailles variables (cartes produit). */
export function imageSrcset(value: string, apiBase: string, widths: number[] = [320, 480, 800]): string | undefined {
  if (value.startsWith('http')) return undefined
  return widths.map((w) => `${resolveImageUrl(value, apiBase, w)} ${w}w`).join(', ')
}

const RELATIVE_DAY_LABELS: Record<number, string> = { 0: "Aujourd'hui", 1: 'Demain', 2: 'Après-demain' }

// Construit une date locale à partir d'un "YYYY-MM-DD" plutôt que
// `new Date(iso)` (qui parse en UTC) — sinon, selon le fuseau horaire du
// visiteur, une date proche de minuit peut basculer sur le mauvais jour une
// fois reconvertie en local.
function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function relativeDayLabel(target: Date, today: Date): string {
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86_400_000)
  if (diffDays in RELATIVE_DAY_LABELS) return RELATIVE_DAY_LABELS[diffDays]
  return target.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })
}

/**
 * Formats a delivery estimate window as "Demain", "Demain – après-demain",
 * or a weekday/date for anything further out — see
 * app/common/delivery_estimate.py for how the window itself is computed
 * (rule-based, not a real carrier ETA).
 */
export function formatDeliveryEstimate(minIso: string, maxIso: string): string {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const minLabel = relativeDayLabel(parseIsoDate(minIso), today)
  const maxLabel = relativeDayLabel(parseIsoDate(maxIso), today)
  return minLabel === maxLabel ? minLabel : `${minLabel} – ${maxLabel}`
}

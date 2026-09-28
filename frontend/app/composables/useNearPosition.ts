import type { AddressRead } from '~/types/api'

const STORAGE_KEY = 'nm-near'

/**
 * Position de référence de l'acheteur (rubrique « Près de chez vous »,
 * frais de livraison de la fiche produit) : position du téléphone déjà
 * partagée, sinon adresse enregistrée. La géolocalisation n'est demandée
 * que sur action explicite (requestPosition).
 */
export function useNearPosition() {
  const near = useState<{ lat: number; lng: number } | null>('near-position', () => null)
  const resolved = useState('near-position-resolved', () => false)
  const { apiFetch } = useApi()
  const auth = useAuthStore()
  const { locate, locating } = useGeolocation()

  function save(lat: number, lng: number) {
    near.value = { lat, lng }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(near.value))
    } catch {
      // Stockage indisponible (navigation privée…) : la position reste en mémoire.
    }
  }

  /** À appeler côté client (onMounted) ; ne redemande rien si déjà connu. */
  async function resolve(): Promise<{ lat: number; lng: number } | null> {
    if (near.value || resolved.value) return near.value
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
      if (stored && typeof stored.lat === 'number' && typeof stored.lng === 'number') near.value = stored
    } catch {
      // Valeur illisible : ignorée.
    }
    if (!near.value && auth.isAuthenticated) {
      try {
        const addresses = await apiFetch<AddressRead[]>('/addresses')
        const located = addresses.filter((a) => a.latitude !== null && a.longitude !== null)
        const chosen = located.find((a) => a.is_default) ?? located[0]
        if (chosen) near.value = { lat: chosen.latitude!, lng: chosen.longitude! }
      } catch {
        // Pas d'adresse exploitable.
      }
    }
    resolved.value = true
    return near.value
  }

  /** Demande la position du téléphone ; lève une Error au message lisible en cas de refus. */
  async function requestPosition() {
    const position = await locate()
    save(position.latitude, position.longitude)
    return near.value!
  }

  return { near, locating, resolve, requestPosition }
}

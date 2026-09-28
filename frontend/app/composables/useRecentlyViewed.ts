const STORAGE_KEY = 'nm-recently-viewed'
const MAX = 20

/** Produits consultés récemment (ids, le plus récent en premier), propres à cet appareil. */
export function useRecentlyViewed() {
  function read(): string[] {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
      return Array.isArray(parsed) ? parsed.filter((v) => typeof v === 'string').slice(0, MAX) : []
    } catch {
      return []
    }
  }

  function add(id: string) {
    const ids = [id, ...read().filter((x) => x !== id)].slice(0, MAX)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
    } catch {
      // Stockage indisponible : l'historique n'est simplement pas conservé.
    }
  }

  return { read, add }
}

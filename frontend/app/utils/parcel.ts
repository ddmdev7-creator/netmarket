import type { ParcelSize } from '~/types/api'

/** Tailles de colis (backend app/common/parcel.py) : libellé et exemples pour le vendeur. */
export const PARCEL_SIZES: { value: ParcelSize; label: string; examples: string }[] = [
  { value: 'S', label: 'Petit', examples: 'Tient dans un sac : téléphone, bijou, vêtement, cosmétique' },
  { value: 'M', label: 'Moyen', examples: 'Boîte à chaussures : chaussures, petit appareil, quelques livres' },
  { value: 'L', label: 'Grand', examples: 'Valise cabine : sac de riz 25 kg, micro-ondes, carton de boissons' },
  { value: 'XL', label: 'Très grand', examples: 'Gros volume : télévision, meuble, réfrigérateur, matelas' },
]

export function parcelSizeLabel(size: ParcelSize | null | undefined): string {
  const found = PARCEL_SIZES.find((s) => s.value === size)
  return found ? `${found.value} · ${found.label}` : 'S · Petit'
}

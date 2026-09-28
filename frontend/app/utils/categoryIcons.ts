import {
  PhBaby,
  PhBarbell,
  PhBasket,
  PhBooks,
  PhCamera,
  PhCar,
  PhCookingPot,
  PhCouch,
  PhCpu,
  PhDeviceMobile,
  PhFirstAidKit,
  PhFlowerLotus,
  PhGameController,
  PhHammer,
  PhHandbag,
  PhHeadphones,
  PhLaptop,
  PhLightning,
  PhPawPrint,
  PhSneaker,
  PhTShirt,
  PhTag,
  PhTelevision,
  PhWatch,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'

export interface CategoryIconDef {
  key: string
  label: string
  icon: Component
  /** Teinte du rond de catégorie sur l'accueil (fond pâle + icône foncée). */
  hue: number
  /** Mots (sans accents, minuscules) qui font deviner cette icône à partir du nom. */
  keywords: string[]
}

/**
 * Icônes proposées à l'admin pour une catégorie (Category.icon côté API) —
 * la clé est stockée en base, le composant reste côté frontend.
 */
export const CATEGORY_ICONS: CategoryIconDef[] = [
  { key: 'phone', label: 'Téléphones', icon: PhDeviceMobile, hue: 215, keywords: ['telephone', 'phone', 'smartphone', 'mobile', 'tablette'] },
  { key: 'laptop', label: 'Ordinateurs', icon: PhLaptop, hue: 230, keywords: ['ordinateur', 'laptop', 'pc', 'informatique', 'acer', 'hp', 'lenovo', 'dell', 'mac'] },
  { key: 'tv', label: 'TV & écrans', icon: PhTelevision, hue: 250, keywords: ['tv', 'tele', 'ecran', 'television'] },
  { key: 'electronics', label: 'Électronique', icon: PhCpu, hue: 265, keywords: ['electronique', 'micro', 'composant', 'arduino'] },
  { key: 'audio', label: 'Audio', icon: PhHeadphones, hue: 280, keywords: ['audio', 'casque', 'ecouteur', 'enceinte', 'son'] },
  { key: 'camera', label: 'Photo', icon: PhCamera, hue: 300, keywords: ['photo', 'camera', 'appareil'] },
  { key: 'electricity', label: 'Électricité', icon: PhLightning, hue: 45, keywords: ['electricite', 'electrique', 'solaire', 'cable', 'lampe', 'eclairage'] },
  { key: 'grocery', label: 'Alimentation', icon: PhBasket, hue: 140, keywords: ['aliment', 'epicerie', 'nourriture', 'riz', 'boisson'] },
  { key: 'kitchen', label: 'Cuisine', icon: PhCookingPot, hue: 25, keywords: ['cuisine', 'ustensile', 'electromenager'] },
  { key: 'home', label: 'Maison', icon: PhCouch, hue: 30, keywords: ['maison', 'meuble', 'deco', 'mobilier'] },
  { key: 'fashion', label: 'Mode', icon: PhTShirt, hue: 330, keywords: ['mode', 'vetement', 'habit', 'pagne', 'tissu'] },
  { key: 'shoes', label: 'Chaussures', icon: PhSneaker, hue: 345, keywords: ['chaussure', 'basket', 'sandale'] },
  { key: 'bags', label: 'Sacs & accessoires', icon: PhHandbag, hue: 355, keywords: ['sac', 'accessoire', 'bijou'] },
  { key: 'watch', label: 'Montres', icon: PhWatch, hue: 200, keywords: ['montre'] },
  { key: 'beauty', label: 'Beauté', icon: PhFlowerLotus, hue: 320, keywords: ['beaute', 'cosmetique', 'parfum', 'soin', 'maquillage'] },
  { key: 'health', label: 'Santé', icon: PhFirstAidKit, hue: 0, keywords: ['sante', 'pharmacie', 'medical'] },
  { key: 'baby', label: 'Bébé & enfants', icon: PhBaby, hue: 190, keywords: ['bebe', 'enfant', 'jouet'] },
  { key: 'sport', label: 'Sport', icon: PhBarbell, hue: 160, keywords: ['sport', 'fitness', 'football'] },
  { key: 'games', label: 'Jeux vidéo', icon: PhGameController, hue: 270, keywords: ['jeu', 'console', 'gaming', 'playstation'] },
  { key: 'auto', label: 'Auto & moto', icon: PhCar, hue: 210, keywords: ['auto', 'voiture', 'moto', 'piece'] },
  { key: 'tools', label: 'Bricolage', icon: PhHammer, hue: 35, keywords: ['bricolage', 'outil', 'quincaillerie', 'construction'] },
  { key: 'books', label: 'Livres', icon: PhBooks, hue: 20, keywords: ['livre', 'papeterie', 'fourniture', 'scolaire'] },
  { key: 'pets', label: 'Animaux', icon: PhPawPrint, hue: 90, keywords: ['animal', 'animaux'] },
  { key: 'other', label: 'Autre', icon: PhTag, hue: 220, keywords: [] },
]

const BY_KEY = new Map(CATEGORY_ICONS.map((def) => [def.key, def]))
const FALLBACK = BY_KEY.get('other')!

function normalize(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

/** Icône choisie par l'admin, sinon devinée à partir du nom de la catégorie. */
export function categoryIcon(category: { name: string; icon?: string | null }): CategoryIconDef {
  if (category.icon && BY_KEY.has(category.icon)) return BY_KEY.get(category.icon)!
  const words = normalize(category.name).split(/[^a-z0-9]+/)
  for (const def of CATEGORY_ICONS) {
    if (def.keywords.some((k) => words.some((w) => w.startsWith(k)))) return def
  }
  return FALLBACK
}

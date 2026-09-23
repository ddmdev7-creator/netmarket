/**
 * Repères de carte de la vue d'ensemble admin (components/admin/OverviewMap.vue).
 *
 * Trois types, distincts par la couleur ET la forme de l'icône (pas la
 * couleur seule — lisible aussi pour un daltonien) :
 *  - boutique              : violet, vitrine
 *  - point de retrait      : bleu de la marque, colis
 *  - boutique + retrait    : sarcelle, vitrine avec pastille colis (une boutique
 *                            qui EST aussi un point de retrait — un seul repère
 *                            plutôt que deux empilés au même endroit)
 *  - livreur               : orange, moto (carte des livreurs uniquement)
 *  - domicile              : rose, maison — destination d'une livraison à
 *                            domicile en cours (carte des livreurs uniquement)
 *
 * Les icônes sont les composants Phosphor de l'app rendus dans le DOM du
 * repère via render() de Vue, plutôt que des chemins SVG recopiés à la main.
 * Chaque repère est un élément enveloppant (positionné par MapLibre via
 * transform) contenant un corps stylé : les effets hover/sélection portent
 * sur le corps, jamais sur l'élément enveloppant, sinon ils écraseraient le
 * positionnement de MapLibre.
 */
import { h, render, type Component } from 'vue'
import '~/assets/styles/map-pins.css'
import { PhHouse, PhMotorcycle, PhPackage, PhStorefront } from '@phosphor-icons/vue'

export type MapPinKind = 'shop' | 'pickup' | 'shop_pickup' | 'courier' | 'home'

export const MAP_PIN_META: Record<MapPinKind, { label: string; color: string; icon: Component }> = {
  shop: { label: 'Boutique', color: '#7c3aed', icon: PhStorefront },
  pickup: { label: 'Point de retrait', color: '#0a66f5', icon: PhPackage },
  shop_pickup: { label: 'Boutique + point de retrait', color: '#0d9488', icon: PhStorefront },
  courier: { label: 'Livreur', color: '#ea580c', icon: PhMotorcycle },
  home: { label: 'Livraison à domicile', color: '#db2777', icon: PhHouse },
}

const MUTED_COLOR = '#8b8d97'

export interface PinHandle {
  el: HTMLElement
  dispose: () => void
}

export interface PinOptions {
  selected: boolean
  /** Élément inactif/suspendu/rejeté : repère grisé. */
  muted: boolean
  /** Petit point d'alerte (ex. boutique en attente de validation). */
  attention: boolean
  label: string
  /** Repère réduit, pour un simple repère de contexte (voir MapPicker.vue). */
  small?: boolean
  /** Livraison en cours : halo pulsant autour du repère. */
  live?: boolean
}

function mount(host: HTMLElement, icon: Component, size: number): () => void {
  render(h(icon, { size, weight: 'fill', color: '#ffffff' }), host)
  return () => render(null, host)
}

export function createPin(kind: MapPinKind, options: PinOptions): PinHandle {
  const meta = MAP_PIN_META[kind]
  const disposers: Array<() => void> = []

  const root = document.createElement('div')
  root.className =
    'om-pin' +
    (options.selected ? ' om-pin--selected' : '') +
    (options.small ? ' om-pin--small' : '') +
    (options.live ? ' om-pin--live' : '')
  root.style.zIndex = options.selected ? '10' : '1'

  const body = document.createElement('button')
  body.type = 'button'
  body.className = 'om-pin__body'
  body.style.setProperty('--pin-color', options.muted ? MUTED_COLOR : meta.color)
  body.setAttribute('aria-label', options.label)
  if (options.live) {
    // Frère du corps, pas enfant : l'onde ne doit pas hériter du scale au survol.
    const pulse = document.createElement('span')
    pulse.className = 'om-pin__pulse'
    pulse.style.setProperty('--pin-color', meta.color)
    root.append(pulse)
  }
  root.append(body)

  const icon = document.createElement('span')
  icon.className = 'om-pin__icon'
  body.append(icon)
  disposers.push(mount(icon, meta.icon, options.small ? 12 : 17))

  if (kind === 'shop_pickup') {
    const mini = document.createElement('span')
    mini.className = 'om-pin__mini'
    mini.style.setProperty('--pin-color', options.muted ? MUTED_COLOR : MAP_PIN_META.pickup.color)
    body.append(mini)
    disposers.push(mount(mini, PhPackage, 9))
  }

  if (options.attention) {
    const dot = document.createElement('span')
    dot.className = 'om-pin__attention'
    body.append(dot)
  }

  return { el: root, dispose: () => disposers.forEach((dispose) => dispose()) }
}

export function createClusterPin(count: number, label: string, live = false): PinHandle {
  const root = document.createElement('div')
  root.className = 'om-cluster' + (live ? ' om-cluster--live' : '')
  const body = document.createElement('button')
  body.type = 'button'
  body.className = 'om-cluster__body'
  body.setAttribute('aria-label', label)
  body.textContent = count > 99 ? '99+' : String(count)
  root.append(body)
  return { el: root, dispose: () => {} }
}

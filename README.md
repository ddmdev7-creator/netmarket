# Marketplace Guinée — Backend

Marketplace e-commerce multi-vendeurs pour le marché guinéen (type Wildberries/Ozon).

État actuel : socle technique + gestion complète des vendeurs + catalogue +
panier multi-vendeurs + commandes avec split par vendeur + paiement (cash on
delivery, interface `PaymentProvider` prête pour NimbaPay) + tableaux de bord
vendeur/admin + avis produits + signalement/modération (produits et avis) +
notifications email et in-app temps réel (WebSocket) + filtres catalogue
(catégorie, prix, stock, tri) + estimation de livraison (règle simple, sans
transporteur réel). Frontend Nuxt/PWA acheteur, vendeur et admin
opérationnel. Intégration NimbaPay réelle et SMS restent à construire (voir
« Prochaines étapes »).

## Stack

- **Backend** : FastAPI (Python 3.12), SQLAlchemy 2.0 (async), PostgreSQL, Redis
- **Auth** : JWT (access + refresh), mot de passe hashé (Argon2), mot de passe
  oublié self-service par code email
- **Email** : API transactionnelle Brevo (`app/core/email.py`)
- **Migrations** : Alembic
- **Tests** : pytest + pytest-asyncio + httpx (base de données PostgreSQL réelle)
- **Conteneurisation** : Docker + docker-compose (api, db, redis)

## Prérequis

- Docker et Docker Compose
- (Optionnel, pour développer hors conteneur) Python 3.12+

## Démarrage rapide

1. Copier le fichier d'environnement et l'ajuster si besoin (notamment les
   ports si `8001`/`55432` sont déjà pris sur ta machine) :

   ```bash
   cp .env.example .env
   ```

2. Lancer les services (API + PostgreSQL + Redis) :

   ```bash
   docker compose up --build
   ```

   L'API est alors disponible sur http://localhost:8001 (ou le port choisi
   dans `.env`), avec la documentation interactive sur `/docs`.

3. Dans un autre terminal, appliquer les migrations de base de données :

   ```bash
   docker compose exec api alembic upgrade head
   ```

4. Vérifier que tout fonctionne :

   ```bash
   curl http://localhost:8001/health
   ```

## Accès depuis un autre appareil (téléphone) sur le même réseau

L'app détecte automatiquement l'adresse à utiliser — rien à reconfigurer
quand l'IP de la machine change (changement de Wi-Fi, redémarrage du
routeur, etc.) :

- **Frontend** : `nuxt.config.ts` fait écouter le serveur de dev sur
  `0.0.0.0` (pas seulement `localhost`), donc joignable depuis n'importe quel
  appareil du réseau via l'IP locale de la machine (`http://<IP>:3000`).
- **API** : `useApiBase()` (`frontend/app/composables/useApiBase.ts`) réutilise
  l'hôte qui a servi à charger la page (`useRequestURL()`, valable aussi bien
  côté rendu serveur que navigateur) pour construire l'URL de l'API — un
  téléphone qui ouvre `http://<IP>:3000` contactera automatiquement l'API sur
  `http://<IP>:8001`, sans configuration figée. `NUXT_PUBLIC_API_BASE` reste
  disponible pour forcer une adresse fixe (ex. un vrai nom de domaine en
  production).
- **Images produit** : jamais chargées directement depuis MinIO — voir
  section « Upload d'images » ci-dessous.

## Lancer les tests

Les tests utilisent une vraie base PostgreSQL dédiée, `netmarket_test`
(`TEST_DATABASE_URL`, créée automatiquement au premier démarrage du conteneur
`db` par `backend/docker/init-test-db.sql`) — **jamais** la base de dev
`netmarket` : la suite fait un `drop_all`/`create_all` du schéma à chaque
lancement, ce qui effacerait toutes tes données de dev si les deux bases se
confondaient. Chaque test s'exécute ensuite dans une transaction annulée à la
fin, donc aucune donnée ne persiste entre deux tests.

```bash
docker compose exec api pytest
```

## Générer une nouvelle migration

Après avoir modifié un modèle SQLAlchemy (`app/**/models.py`) :

```bash
docker compose exec api alembic revision --autogenerate -m "description du changement"
docker compose exec api alembic upgrade head
```

Toujours relire la migration générée avant de l'appliquer : l'autogénération
Alembic ne détecte pas tout (renommages de colonnes, certains changements de
contraintes...).

## Structure du projet

```
netmarket/
├── docker-compose.yml
├── .env.example
└── backend/
    ├── app/
    │   ├── main.py          # point d'entrée FastAPI
    │   ├── core/             # config, sécurité (JWT/hash), DB, dépendances, exceptions, pagination
    │   ├── common/           # mixins ORM et schémas partagés
    │   ├── auth/             # inscription / connexion / refresh token
    │   ├── users/            # profil utilisateur (GET/PATCH /users/me)
    │   ├── vendors/          # boutiques : inscription, profil, annuaire public, validation admin
    │   ├── couriers/         # livreurs (motards, taxis...) : inscription, annuaire, validation admin
    │   ├── catalog/          # catégories et produits (CRUD, pagination, filtres)
    │   ├── cart/              # panier multi-vendeurs (vue groupée par boutique)
    │   ├── orders/            # checkout, split en sous-commandes, suivi de statut
    │   ├── addresses/         # carnet d'adresses/points de retrait de l'acheteur, réutilisables au checkout
    │   ├── payments/          # interface PaymentProvider, cash on delivery (NimbaPay à venir)
    │   ├── uploads/           # upload d'images produit vers MinIO (vendeur) + proxy public de lecture
    │   ├── reviews/           # avis produits (note 1-5 + commentaire), après livraison uniquement
    │   ├── notifications/     # email à l'acheteur sur les changements de statut de commande
    │   └── admin/             # statistiques plateforme, vue globale des commandes
    ├── alembic/               # migrations de base de données
    ├── docker/                # scripts d'initialisation Postgres (base de test)
    └── tests/                 # tests pytest
```

## Authentification

- Inscription : `POST /auth/register` — téléphone (format `+224XXXXXXXXX`) + mot
  de passe. Crée toujours un compte **acheteur**.
- Connexion : `POST /auth/login` → paire de jetons `access_token` / `refresh_token`.
- Renouvellement : `POST /auth/refresh` avec le `refresh_token`.
- Les routes protégées attendent l'en-tête `Authorization: Bearer <access_token>`.

Il n'existe volontairement aucun endpoint pour créer un administrateur (pour
éviter toute auto-élévation de privilèges). Le tout premier compte admin doit
être créé directement en base, par exemple :

```bash
docker compose exec api python -c "
import asyncio
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.users.models import User, UserRole

async def main():
    async with AsyncSessionLocal() as db:
        db.add(User(phone='+224600000000', password_hash=hash_password('change-me'), role=UserRole.ADMIN))
        await db.commit()

asyncio.run(main())
"
```

## Vendeurs

- `POST /vendors/me` — un acheteur devient vendeur (rôle promu immédiatement,
  statut `pending` tant que non validé).
- `GET /vendors/me`, `PATCH /vendors/me` — profil de sa propre boutique.
- `GET /vendors`, `GET /vendors/{id}` — annuaire public (boutiques `approved` uniquement).
- `GET /admin/vendors?status=pending`, `PATCH /admin/vendors/{id}` — validation,
  rejet, suspension et ajustement de la commission (admin uniquement).

Un vendeur ne peut publier de produits que si sa boutique est `approved`
(vérifié à la création de produit, cf. `app/catalog/service.py`).

## Upload d'images

- `POST /uploads/images` (vendeur) — recompresse chaque image (JPEG, ≤1600px,
  qualité 82) et l'envoie sur MinIO ; répond avec la **clé objet** de chaque
  image (`{"keys": [...]}`), pas une URL.
- `GET /uploads/images/{key}` (public) — sert l'image en la lisant sur MinIO
  et en la renvoyant directement, plutôt que de rediriger vers MinIO.

Le navigateur ne parle donc jamais directement à MinIO — seulement à l'API,
et uniquement via son adresse déjà auto-détectée (voir « Accès depuis un
autre appareil » ci-dessus). `Product.images` stocke ces clés (ou une URL
externe complète si le vendeur en a collé une manuellement dans le
formulaire produit — les deux formats coexistent, distingués au moment de
l'affichage par `resolveImageUrl()` côté frontend). Avant ce changement, les
URLs étaient absolues et figées en base au moment de l'upload
(`http://<IP>:9002/...`) : une migration de données
(`3192f945049d_extract_product_image_keys_from_stale_.py`) a réextrait la
clé de toutes les images déjà uploadées pour les remettre dans ce nouveau
format.

## Carte (positionnement)

`CommonMapPicker` (`frontend/app/components/common/MapPicker.vue`) — carte
interactive pour poser un repère (tap ou glisser-déposer), utilisée dans le
formulaire d'adresse acheteur (`AddressForm.vue`, en complément du bouton
« Utiliser ma position actuelle ») et dans la création de points de retrait
admin (qui n'exigeait auparavant que la géolocalisation navigateur — l'admin
devait donc être physiquement sur place pour créer un point).

Basée sur **MapLibre GL JS** (fork open-source de Mapbox GL) avec des tuiles
raster **Esri "Light/Dark Gray Canvas"** (`services.arcgisonline.com`,
`frontend/app/utils/mapStyle.ts`) — gratuit, sans clé API, pensé pour un
usage en production (contrairement au serveur de tuiles public d'OSM, dont
la politique d'usage interdit ce type d'usage en production). Deux variantes
(claire/sombre) choisies selon le thème courant (`useAppTheme()`) et
réappliquées à la volée au changement de thème, pour que le fond de carte
reste assorti au reste de l'UI. Auparavant sur des tuiles vectorielles
OpenFreeMap, abandonnées après un rendu silencieusement vide avec
maplibre-gl@6.4.0, puis sur des tuiles raster CARTO, abandonnées à leur tour
car CARTO impose désormais un compte + clé API pour un usage hors de CARTO
Builder. Toujours chargée dynamiquement (`import()` dans `onMounted`, jamais
en import statique) : MapLibre touche `window`/WebGL au chargement, ce qui
casserait le rendu serveur (SSR) de toute page utilisant ce composant
sinon.

## Adresses

Carnet d'adresses de l'acheteur (`GET/POST /addresses`,
`PATCH/DELETE /addresses/{id}`), réutilisable au checkout. Deux modes,
validés côté serveur (`app/addresses/schemas.py` et `service.py`) et côté
frontend (`AddressForm.vue` via `utils/addressValidation.ts` —
`validateAddressForm()`, partagée par le checkout et les deux pages de
gestion d'adresses pour que la règle ne diverge plus entre elles) :

- **Livraison à domicile** : zone/description texte (≥3 caractères) ou
  position GPS — l'un des deux suffit.
- **Point de retrait** : `pickup_point_id` obligatoire — une zone/position
  seule ne suffit pas, même si le champ `zone` contient du texte. C'était un
  bug corrigé le 17/08 : basculer vers « Point de retrait » sans en
  sélectionner un dans la liste passait la validation tant que `zone`
  gardait un texte résiduel d'une saisie « domicile » précédente (rien ne
  vérifiait `pickup_point_id` lui-même) — l'adresse s'enregistrait mais
  échouait ensuite au checkout avec un 409 confus (« un point de retrait
  doit être sélectionné »).

## Panier & commandes

- `GET /cart`, `POST /cart/items`, `PATCH /cart/items/{id}`,
  `DELETE /cart/items/{id}`, `DELETE /cart` — le panier est retourné groupé
  par boutique, avec sous-totaux.
- `POST /orders/checkout` — transforme le panier en une `Order` + une
  `SubOrder` par vendeur (split automatique), décrémente le stock, calcule la
  commission de chaque sous-commande à partir de `Vendor.commission_rate`.
- `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel` (acheteur ;
  annulation possible uniquement tant qu'aucun vendeur n'a encore accepté).
- `GET /orders/sub-orders`, `PATCH /orders/sub-orders/{id}/status` — qui peut
  faire quelle transition dépend du rôle (voir
  `app/orders/service.py::update_sub_order_status`) :
  - **Vendeur** : en attente → confirmée → en préparation → expédiée, ou
    annulée avant expédition. Passer à « expédiée » exige qu'un livreur ait
    été assigné au préalable (`PATCH /orders/sub-orders/{id}/courier`) — un
    colis ne peut pas être « en route » sans personne pour le transporter
    (rejeté en `409` sinon). Le vendeur n'a plus la main ensuite : ni
    « arrivée au point de retrait » ni « remise au client » ne peuvent venir
    de lui (rejeté en `403`), il n'a physiquement plus le colis à ce stade.
  - **Livreur assigné** : confirme la remise au client pour une livraison à
    domicile (« expédiée » → « livrée »), manuellement ou en scannant le QR
    de l'acheteur (`POST /orders/sub-orders/confirm-delivery`). Pour un point
    de retrait, il n'a rien à confirmer lui-même — il montre son propre QR
    de dépôt (`pickup_dropoff_token`) que le gestionnaire du point scanne.
  - **Gestionnaire de point de retrait** : seul habilité à confirmer les deux
    étapes qui se passent chez lui — réception du colis déposé par le
    livreur (« expédiée » → « arrivée au point », en scannant le QR du
    livreur ou manuellement) puis remise finale au client (« arrivée au
    point » → « livrée », en scannant le QR de l'acheteur ou manuellement).

  Le statut global de la commande est recalculé automatiquement à partir de
  ses sous-commandes.

### Frais de livraison

Grille de **paliers de distance** éditable par l'admin (`/admin/frais-livraison`,
table `delivery_fee_tiers`) : « jusqu'à X km = tant de GNF », plus un palier
« au-delà » (`max_km` NULL) qui sert aussi de repli quand une position GPS
manque. Les frais sont calculés **par sous-commande** (un colis par vendeur),
sur la distance boutique → adresse de livraison (GPS envoyé au checkout) ou
boutique → point de retrait (position du point). Sans aucun palier, la
livraison est gratuite. `POST /orders/delivery-quote` chiffre le panier avant
commande avec exactement le même calcul que le checkout ; le résultat est
**figé** sur `SubOrder.delivery_fee`. `Order.total` = Σ(articles + frais), mais
la commission ne porte que sur les articles.

### Estimation de livraison

Pas de vraie donnée logistique (pas de transporteur, pas de réseau
d'entrepôts façon Wildberries) — l'estimation est donc calculée par une
règle simple (`app/common/delivery_estimate.py`) : délai de préparation
déclaré par le vendeur (`Vendor.preparation_days`, réglable dans ses
paramètres boutique) + un jour de trajet si la zone de livraison de
l'acheteur diffère de celle du vendeur (comparaison texte souple, les zones
étant en saisie libre — pas de liste de communes structurée). Sur la fiche
produit, la zone de l'acheteur n'est pas encore connue : l'estimation
affichée y est donc générique (hypothèse « zone différente »). Une fois la
commande passée, l'estimation réelle est calculée avec la zone choisie au
checkout et **figée** sur la sous-commande (`SubOrder.estimated_delivery_min/max`)
— elle ne bouge pas si le vendeur change son délai de préparation après
coup. Affichée sur la fiche produit, la confirmation de commande, le suivi
acheteur et la liste des commandes vendeur.

**Limitation connue** : un produit ou une boutique déjà référencé dans une
commande ne peut pas être supprimé (contrainte de clé étrangère en base) —
la suppression renverra une erreur 500 non traduite pour l'instant. Cette
protection d'intégrité est correcte en soi ; elle sera transformée en message
d'erreur français propre lors du durcissement (étape 8).

## Tableaux de bord

- `GET /vendors/me/dashboard` (vendeur) — nombre de commandes (actives,
  livrées, annulées), chiffre d'affaires et commission dus **sur les
  sous-commandes livrées uniquement** (en paiement à la livraison, l'argent
  ne change vraiment de main qu'à ce moment-là), nombre de produits actifs,
  et liste des produits en stock faible (seuil : 5 unités).
- `GET /admin/stats` (admin) — comptages vendeurs/produits/commandes par
  statut, ventes et commission totales (livrées), top 5 produits et top 5
  vendeurs par volume/chiffre d'affaires.
- `GET /admin/orders?status=...` (admin) — vue globale paginée de toutes les
  commandes, tous acheteurs confondus.

## Paiement (NimbaPay)

Le module `payments/` existe : chaque commande crée un enregistrement
`Payment` (statut `pending` / `paid` / `failed` / `cancelled`, référence
transaction externe) via une interface abstraite `PaymentProvider`
(`app/payments/provider.py`). Seule `CashOnDeliveryProvider` est branchée
pour l'instant — `Order.payment_method` n'accepte que `cash_on_delivery`
(tout autre choix est rejeté par la validation Pydantic). Le paiement passe
à `paid` dès que toutes les sous-commandes d'une commande sont livrées (c'est
le moment où l'argent change réellement de main en paiement à la livraison),
et à `cancelled` si l'acheteur annule. `NimbaPayProvider` viendra s'ajouter
au registre de `provider.py` dès que la documentation technique marchand
aura été obtenue auprès de la Guinéenne de Monétique (GuiM) / BCRG — aucun
autre module n'aura besoin de changer.

## Avis produits

Le module `reviews/` permet à un acheteur de laisser une note (1 à 5) et un
commentaire sur un produit — mais seulement s'il en a effectivement reçu un
exemplaire (une sous-commande à son nom livrée pour ce produit ; sinon
`403`), et une seule fois par produit (`409` en cas de doublon). La moyenne
(`average_rating`, `None` tant qu'il n'y a aucun avis) et le nombre d'avis
(`review_count`) sont exposés directement sur `GET /products/{id}` et dans
les listes du catalogue. Liste publique : `GET /products/{id}/reviews`.

## Signalements & modération

Le module `reports/` permet à tout utilisateur connecté de signaler un
produit (`POST /products/{id}/reports`) ou un avis
(`POST /reviews/{id}/reports`) avec un motif. L'admin consulte la file par
statut (`GET /admin/reports?status=pending|dismissed|actioned`) et résout un
signalement (`PATCH /admin/reports/{id}`) : rejet (`dismissed`) ou action
(`actioned`, qui désactive le produit ou supprime l'avis signalé — action
irréversible). Interface admin : `/admin/signalements` (frontend). La gestion
des litiges entre acheteur/vendeur reste à construire.

## Notifications

Le module `notifications/` a deux canaux, déclenchés aux deux mêmes endroits
(`orders/service.py::checkout_cart` et `::update_sub_order_status`) :

- **In-app temps réel** : chaque commande reçue par un vendeur, et chaque
  changement de statut d'une sous-commande pour l'acheteur, crée une ligne
  `Notification` persistée (`GET /notifications`, `PATCH
  /notifications/{id}/read`, `POST /notifications/read-all`) et poussée en
  direct via WebSocket (`/notifications/ws/notifications?token=<access_token>`,
  le token passe en query param car un WebSocket ne permet pas d'en-tête
  `Authorization` custom). Registre de connexions en mémoire
  (`app/notifications/ws_manager.py`) — un seul processus API aujourd'hui, à
  remplacer par du pub/sub Redis si l'API est un jour répliquée. Côté
  frontend : icône cloche dans `LayoutTopBar` (badge non-lu), page
  `/notifications`, connexion gérée globalement par
  `plugins/notifications.client.ts`. Un clic redirige vers le suivi de la
  commande (`/commandes/{id}` acheteur, `/vendeur/commandes?highlight={id}`
  vendeur).
- **Email** à l'acheteur, mais seulement sur les deux transitions où le colis
  arrive physiquement quelque part et où il doit agir : arrivée à son point
  de retrait (`arrived_at_pickup_point`), ou livraison à domicile
  (`delivered` en `home_delivery` — pas de mail sur le `delivered` d'un point
  de retrait, l'acheteur est déjà sur place à ce moment-là). Les autres
  transitions (confirmée, en préparation, expédiée, annulée) ne passent que
  par le canal in-app/WebSocket, pour limiter le volume de mails envoyés.
  Via l'API Brevo (`app/core/email.py` — sans clé configurée, l'email est
  juste loggé, pratique en dev/CI).
  Silencieusement ignoré si l'acheteur n'a pas renseigné d'email (champ
  optionnel à l'inscription).

Le même module Brevo envoie aussi : le code de confirmation d'email à la
création de compte (acheteur si un email est fourni, vendeur à
l'onboarding — `app/users/service.py::send_verification_code`) et le code de
réinitialisation de mot de passe (`POST /auth/forgot-password` puis
`/auth/reset-password`, sans révéler si un compte existe pour le numéro
donné).

Les deux canaux (email + in-app) sont best-effort : un échec (Brevo ou push WebSocket) est
journalisé mais n'annule jamais la mise à jour de statut qui l'a déclenché —
la notification in-app reste de toute façon consultable via `GET
/notifications` même si le push en direct a échoué (socket fermée, etc.).

**SMS non implémenté** : aucun fournisseur SMS n'est intégré à ce stade — il
n'existe pas encore de compte marchand chez un opérateur/passerelle SMS
guinéen. Le module est structuré pour qu'ajouter un canal SMS plus tard
n'impacte que `notifications/service.py`.

## Prochaines étapes (plan de développement, cahier des charges §8)

1. ~~Socle technique~~ (itération 1)
2. ~~Catalogue & vendeurs~~ (itération 1 + 2)
3. ~~Panier & commande~~ (itération 2)
4. ~~Paiement~~ : interface `PaymentProvider` en place (itération 4 — cash on
   delivery ; NimbaPay branché dès la doc marchand obtenue auprès de GuiM/BCRG)
5. ~~Tableaux de bord vendeur puis admin~~ (itération 3 — statistiques, vue
   globale des commandes)
5bis. ~~Avis produits~~ (note + commentaire après livraison, moyenne exposée
   sur la fiche produit)
5ter. ~~Signalement & modération~~ (produits et avis, file admin
   `/admin/signalements`) — gestion des litiges acheteur/vendeur reste à construire
6. ~~Frontend acheteur, vendeur et admin (Nuxt / PWA)~~ — les trois espaces
   ont une interface fonctionnelle
7. ~~Notifications~~ : email + in-app temps réel (WebSocket, icône cloche) sur
   changement de statut de commande et nouvelle commande reçue ; SMS reste à
   faire (pas de fournisseur intégré)
7bis. ~~Filtres catalogue~~ : catégorie/prix/stock/tri côté acheteur,
   catégorie/statut/niveau de stock/tri côté "Mes produits" vendeur
7ter. ~~Estimation de livraison~~ : délai de préparation vendeur + heuristique
   de zone, figée par sous-commande au checkout — voir « Estimation de
   livraison » ci-dessus. Amélioration possible plus tard avec de vraies
   données de trajet une fois assez d'historique de livraisons accumulé.
8. Tests (159 tests backend passent), durcissement sécurité, préparation
   déploiement (litiges acheteur/vendeur, intégration NimbaPay réelle, SMS)

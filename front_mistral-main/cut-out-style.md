# 📐 Guide UI — Style « Cut-out Collage »

> Chaque image est un élément découpé : contour blanc irrégulier, bords imparfaits, superpositions, rotations légères. Le site doit ressembler à un zine ou un collage fait main, pas à une grille de cartes parfaites.

---

## 1. L'esprit du style

- **Référence** : collage magazine/zine des années 90, feuille d'autocollants, scrapbook.
- **Sensation** : tactile, imprimé, artisanal — l'inverse du « glassmorphism » lisse et digital.
- **Règle d'or** : chaque image, icône ou groupe de contenu est traité comme un **papier découpé au ciseau** : bord blanc irrégulier + légère ombre portée.

---

## 2. Palette de couleurs

| Rôle | Couleur | Usage |
|---|---|---|
| Fond principal | Gris papier clair `#E8E6E1` (ou blanc cassé `#F5F2EC`) | Pages, sections |
| Fond secondaire | Gris moyen `#9B9B9B` | Blocs alternés, aplats |
| Découpages | Noir & blanc / halftone | Photos et illustrations |
| Accent 1 | Rouge collage `#D94A2B` | CTA, éléments « scotchés » |
| Accent 2 | Bleu encre `#2B4C7E` | Liens, tags, tampons |
| Contours | Noir pur `#111111` | Traits, typo, bordures dessinées |

- Rester majoritairement en **noir / blanc / gris** avec 1 à 2 accents vifs seulement.
- Les photos sont traitées en **noir et blanc halftone** (points de trame visibles).

---

## 3. Traitement des images — « l'effet découpage » ✂️

C'est le cœur du style. Recette pour chaque image :

1. **Détourage** du sujet (arrière-plan supprimé).
2. **Contour blanc** de 8 à 16 px qui suit la forme du sujet — pas un rectangle.
3. **Irrégularité** : le contour ondule et varie (±3-4 px), comme une coupe au ciseau rapide. Jamais un bord parfaitement lisse.
4. **Ombre portée papier** : décalée (ex. `4px 6px`), douce, avec légère rotation de l'élément.
5. **Option halftone** : appliquer une trame de points + contraste N&B fort.

**Épaisseur du contour** :
- Fine (6-8 px) → découpe magazine soignée.
- Épaisse (14-18 px) → effet sticker / autocollant, meilleur sur fond chargé.

**Dans Figma / Illustrator** : détourer → `Offset Path` (offset ~10 px) → effet *Roughen / Tweak* (taille 3 px, 8-12 par pouce) → union avec le sujet → remplissage blanc derrière.

**En CSS** (l'image porte son propre bord blanc) :

```css
.cutout {
  filter: drop-shadow(4px 6px 4px rgba(0, 0, 0, 0.18));
}
.cutout--rotated { rotate: -2.5deg; }
```

Astuce production : exporter chaque visuel en **PNG transparent avec son bord blanc irrégulier déjà intégré**, puis ne gérer en CSS que rotation + ombre. C'est plus fiable qu'un masque dynamique.

---

## 4. Typographie

- **Titres** : fonte à fort caractère, imprimé — condensée, serif grinçante ou punk. Ex. *Anton, Archivo Black, Fraunces*.
- **Corps** : sans-serif lisible mais pas trop propre. Ex. *Space Grotesk, IBM Plex Sans*.
- **Détails** : écriture manuscrite pour annotations et flèches. Ex. *Caveat, Permanent Marker*.
- Titres possibles **découpés eux aussi** : lettres avec contour blanc irrégulier, chaque mot légèrement pivoté.
- Mélanger les échelles de manière expressive (un mot énorme, une annotation minuscule).

---

## 5. Layout & composition

- **Pas de grille rigide visible.** Composition « éclatée » : éléments dispersés, superposés, qui débordent des sections.
- **Rotations légères** aléatoires entre −4° et +4° sur les images et cartes.
- **Chevauchements assumés** : une photo passe devant un titre, un sticker recouvre un coin de carte.
- Beaucoup d'**espace** autour des découpes : le style respire, l'œil suit les formes.
- Marges irrégulières : éviter les alignements parfaits de plus de 2 éléments consécutifs.
- Sections séparées par des **bords déchirés** (torn edge) plutôt que des lignes droites.

---

## 6. Textures

- **Halftone** (trame de points) sur les images N&B.
- **Grain papier** très léger en overlay global du site (`opacity` 4-6 %).
- Éléments scrapbook en accent : morceaux de **scotch adhésif**, trombones, tampons, gommettes, annotations manuscrites fléchées.
- À utiliser avec parcimonie : 2-3 éléments « physiques » par écran maximum.

---

## 7. Composants UI

**Boutons**
- Fond blanc, bordure noire dessinée à la main (légèrement ondulée), ombre offset dure `2px 3px 0 #111`.
- Au survol : le bouton « saute » (translate) et son ombre s'allonge — comme un autocollant qu'on soulève.
- Variante : bouton en forme de découpe irrégulière (blob), pas un rectangle.

**Cartes**
- Fond blanc, ombre papier douce, rotation ±2°.
- Contenu : une image découpée qui **déborde du cadre** de la carte (le sujet sort des limites).

**Navigation**
- Logo façon sticker/tampon. Liens soulignés au marqueur (trait ondulé SVG).

**Badges & tags**
- Petites formes découpées (cercles, étoiles, blobs) avec contour blanc, posées en coin, en rotation.

**Hero**
- Grande composition éclatée de 5-8 découpes superposées au lieu d'une seule image bannière.

---

## 8. Motion & interactions

- **Hover image** : elle se soulève (translate −4 px, ombre qui grandit) + rotation qui s'accentue de 1°. Effet « je décolle le papier ».
- **Transitions** : apparitions par petits sauts irréguliers (step easing, 2-3 frames), façon **stop-motion** — jamais de fade fluide et linéaire.
- **Scroll** : parallaxe légère entre les découpes (elles glissent à des vitesses différentes, comme des papiers posés).
- Durées courtes : 150-250 ms, `cubic-bezier(0.34, 1.56, 0.64, 1)` (petit rebond).

---

## 9. À faire / à éviter

**✅ À faire**
- Contour blanc irrégulier sur CHAQUE image et illustration.
- Rotations et superpositions légères partout.
- N&B halftone + 1-2 accents de couleur.
- Typographie expressive, annotations manuscrites.
- Ombres « papier », jamais de néon ni de glassmorphism.

**❌ À éviter**
- Border-radius réguliers, coins arrondis parfaits partout.
- Grille de cartes identiques et alignées.
- Photos couleur pleine page non traitées.
- Ombres floues « material design » uniformes.
- Contours lisses : si le bord blanc est régulier, l'effet « ciseau » disparaît.

---

## 10. Checklist rapide par écran

- Fond papier/gris + grain léger
- 1 grande composition éclatée en hero
- Toutes les images ont un bord blanc irrégulier + ombre
- Rotations entre −4° et +4°, superpositions visibles
- Boutons dessinés main, ombre offset dure
- 1-2 accents scrapbook (scotch, annotation manuscrite)
- Animations en petits sauts stop-motion
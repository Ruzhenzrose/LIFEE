# LIFEE — Brand Spec

> Single source of truth for LIFEE's visual identity. Any agent or design tool
> (Claude Design, huashu-design, Figma, etc.) should read this file first before
> generating UI — never invent colors, fonts, or tokens that contradict it.

Last extracted from: `web/void/index.html` · `web/void/components/ChatArena.js`

---

## 1. Brand

**Name** — LIFEE
**Tagline (en)** — "Your life coach and friend."
**Tagline (zh)** — "你的人生导师与挚友。"

**Product in one sentence** — A council-style AI companion: pick one or more
historical / custom personas (Krishnamurti, Buffett, Lacan, ...) and talk to
them together about something going on in your life.

**Voice & tone**
- Editorial, mystical, slightly literary — not a productivity app, not a chatbot
- Warm, attentive, never chirpy or salesy
- Small typography, high information density, lots of uppercase labels with
  wide letter-spacing for section headings
- Microcopy avoids exclamation marks; prefers en-dashes and understatement

---

## 2. Color palette

All hex values grep'd from the actual Tailwind config. Do not round or substitute.

### Core brand

| Token | Hex | Role |
|---|---|---|
| `primary` | `#e8a84c` | Warm amber — brand color, wordmark, hover accents, active states |
| `on-primary` | `#1a0e00` | Text on solid primary (e.g. button label) |
| `on-primary-fixed` | `#0f0800` | Text on gradient buttons |
| `primary-container` | `#7a4e1a` | Deeper amber — filled chips |
| `on-primary-container` | `#fde8c0` | Cream text on primary-container |

### Accent colors

| Token | Hex | Role |
|---|---|---|
| `tertiary` | `#c47a6c` | Terracotta — destructive actions, warning, gradient companion to primary |
| `on-tertiary` | `#2a1010` | — |
| `tertiary-container` | `#6a2e28` | — |
| `on-tertiary-container` | `#f4d0c8` | — |
| `secondary` | `#8a9a6c` | Muted olive — Voice Map accent, calm/neutral |
| `secondary-dim` | `#7a8a5e` | — |
| `on-secondary` | `#1a2008` | — |
| `secondary-container` | `#3a4a20` | — |
| `on-secondary-container` | `#d4e4b0` | — |

### Surfaces (dark)

> **Never pure black.** Every dark surface is warm-tinted brown-black. Ordered
> lightest to darkest top layer.

| Token | Hex |
|---|---|
| `surface` | `#121008` |
| `surface-dim` | `#0e0c08` |
| `surface-container-low` | `#161410` |
| `surface-container` | `#1c1a16` |
| `surface-container-high` | `#232018` |
| `surface-container-highest` | `#2a2720` |
| `surface-variant` | `#1e1b16` |

### Text

| Token | Hex | Role |
|---|---|---|
| `on-surface` | `#ede8e0` | Cream — primary text |
| `on-surface-variant` | `#a09484` | Warm gray — secondary text, labels |

### Borders

| Token | Hex |
|---|---|
| `outline` | `#6b5e4e` |
| `outline-variant` | `#3a3028` |

### Signature gradient

`linear-gradient(135deg, #e8a84c, #c47a6c)` — used on primary buttons and
the iridescent border (with `#8a9a6c` as a third stop for shift animation).

---

## 3. Typography

### Families

| Role | Family | Weights used |
|---|---|---|
| Headlines / wordmark | **Space Grotesk** | 300, 400, 500, 600, 700 (primarily 600/700) |
| Body / labels | **Manrope** | 300–800 (primarily 400/500/600) |
| Monospace | system `font-mono` | — |
| Icons | **Material Symbols Outlined** | variable axes |

Loaded via Google Fonts. `Space+Grotesk:wght@300..700` + `Manrope:wght@300..800` + `Material+Symbols+Outlined`.

### Tailwind aliases

```js
'headline' → Space Grotesk
'body'     → Manrope
'label'    → Manrope
```

### Type scale (actual uses from codebase)

| Usage | Class | Notes |
|---|---|---|
| Wordmark (sidebar) | `text-3xl font-headline font-bold tracking-tight` | `letter-spacing: -0.02em`, breathing opacity animation |
| Page title | `text-xl font-headline font-bold` | |
| Hot / Home hero | `text-5xl` to `text-7xl` | editorial scale |
| Uppercase section label | `text-[10px] font-label uppercase tracking-[0.25em] text-on-surface-variant/60` | the signature label style |
| Body | `text-sm` / `text-xs` | most UI content |
| Fine print / meta | `text-[10px]` or `text-[11px] text-on-surface-variant/50` | |

### Rules

- **Uppercase labels always get wide tracking** — never `uppercase` without `tracking-[0.2em]` or wider
- **Headlines often use `tracking-tight`** (`-0.02em` negative) — Space Grotesk reads slightly loose by default
- **Line-height** — leading-relaxed for body, leading-tight for headlines
- **No italics for emphasis** — use weight (`font-semibold`) or color (`text-primary`) instead

---

## 4. Spacing & radius

### Spacing scale
Tailwind default (`0.25rem` = 4px base). Preferred gaps: `gap-2 / gap-3 / gap-4 / gap-6 / gap-8`. Section padding: `p-6` to `p-10` for modals, `px-8 py-10` for content shells.

### Radii
| Usage | Class |
|---|---|
| Pills / tabs / chips | `rounded-full` |
| Buttons | `rounded-xl` (12px) |
| Inputs / small cards | `rounded-xl` or `rounded-2xl` (16px) |
| Modals / glass cards | `rounded-2xl` or `rounded-3xl` (24px) |
| Avatars | `rounded-full` |

### Borders
Almost always **1px**, usually `border-white/5` or `border-outline/30` or `border-primary/20`. Never solid bright borders — hairline + low opacity.

---

## 5. Signature components

These are the recurring patterns that make LIFEE feel like LIFEE. Reuse them
— do not invent parallel ones.

### `.glass-card`
```css
background: rgba(28, 26, 22, 0.7);
backdrop-filter: blur(20px);
border: 1px solid rgba(232, 168, 76, 0.08);
```
Primary container for modals, featured cards, persona cards.

### `.iridescent-border`
Animated gradient hairline around a card:
```
linear-gradient(135deg, #e8a84c, #c47a6c, #8a9a6c, #e8a84c)
```
`background-size: 300% 300%`, 4s linear shift loop. Applied to hero cards,
premium modals. Uses CSS `mask-composite: exclude` to only render the border.

### `.btn-gradient` (primary CTA)
```css
background: linear-gradient(135deg, #e8a84c, #c47a6c);
color: #0f0800;
font-weight: 700;
```
Hover: lifts `translateY(-1px)` + amber glow `0 8px 24px rgba(232, 168, 76, 0.3)`.

### `.btn-ghost` (secondary)
```css
background: transparent;
border: 1px solid rgba(232, 168, 76, 0.2);
color: #e8a84c;
```
Hover: fills to `rgba(232, 168, 76, 0.08)` + border to 0.4.

### `.warm-shine-active` — the signature motion
A fixed-width sunset band (terracotta → amber → cream → amber → terracotta)
that sweeps across text/icons on hover. Uses `@property --shine-pos` (registered
CSS custom property as `<percentage>`) so it can be animated. Cursor-tracked:
entering parks the band under the pointer; leaving continues the sweep off
right. 1.1s ease-out per transition. Text stays legible via a `currentColor`
background-color fallback under the gradient.

Apply by toggling the class via JS on hover (see `web/void/index.html` bottom
script). Opt out individual elements with `no-shine`. For multi-line text the
JS splits leaf text into per-line `<span>` elements via Pretext so the band
aligns with the actual visual line, not the full paragraph width.

### `.wordmark`
LIFEE wordmark:
```css
color: #e8a84c;
letter-spacing: -0.02em;
animation: wordmark-breath 4s ease-in-out infinite;  /* opacity 0.92 → 1 */
```

### `.void-tab` and `.void-opt`
Capsule-shaped uppercase chips for tabs and landing options. 10px bold,
`tracking-[0.15em]`, rounded-full. Active state = soft amber gradient +
amber border + amber text.

### Persona card (`.persona-card`)
`transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1)`.
Hover: lifts 4px + amber shadow `0 20px 48px rgba(0,0,0,0.5), 0 0 32px rgba(232,168,76,0.12)`.

### Textarea / input (`.void-textarea`)
On focus: amber border + double amber glow:
`0 0 0 3px rgba(232,168,76,0.1), 0 0 24px rgba(232,168,76,0.08)`.

---

## 6. Motion

### Timing
- Micro-interactions (hover, focus): **200–250ms ease**
- State transitions (menu open, card fade): **250–400ms ease-out**
- Warm-shine sweep: **1.1s `cubic-bezier(0.22, 1, 0.36, 1)`** (ease-out-quint-ish)
- Iridescent border shift: **4s linear infinite**
- Wordmark breathing: **4s ease-in-out infinite**

### Rules
- **Never bounce or elastic** — all easing is smooth deceleration
- **Only animate `transform` and `opacity`** (60fps budget)
- **Respect `prefers-reduced-motion`** — warm-shine and breathing should halt

### Named animations (Tailwind)
```js
'shimmer':    2.5s linear infinite    // loading shimmer
'fade-in':    0.4s ease-out forwards  // mount transition
'slide-in':   0.35s cubic-bezier(0.4,0,0.2,1) forwards
'pulse-glow': 2s ease-in-out infinite
```

---

## 7. Iconography

- **Material Symbols Outlined** for all UI icons (chat bubble, map, more_vert,
  star, ios_share, expand_more, etc.)
- Size 14–18px in the chrome, 20–24px in featured spots
- Color matches surrounding text; hover flips to `#f0b860` (via `.hover-warm-icon`)
- Avatars are emoji by default (☁️, 💬, 🧭, etc.) with per-persona override;
  HSL-generated unique ring + tinted background per persona id — no two
  personas ever share a color, even the custom ones

---

## 8. Layout

- **Max content width** — `max-w-[1400px]` for shells, `max-w-5xl` for chat,
  `max-w-2xl` for modals
- **Sidebar** — `w-72` expanded (288px), `w-14` collapsed (56px rail)
- **Chat header** — fixed `h-20`
- **Grid** — `grid-cols-2 sm:grid-cols-3 md:grid-cols-4` for persona/card grids
- **Mobile-first not a goal** — product is desktop-primary (Windows / Mac)

### Ambient background
Three radial gradients fixed behind all content:
```
top-left:     #e8a84c at 5% opacity
bottom-right: #8a9a6c at 3% opacity
mid-right:    #c47a6c at 3% opacity
```
Adds subtle warm depth without being noticeable as a gradient.

---

## 9. Brand asset protocol (when extending LIFEE)

Following the huashu-design / Claude Design 5-step protocol:

1. **Ask** — is there already a `brand-spec.md` or style source? (Yes: this file.)
2. **Fetch** — read this file + `web/void/index.html` Tailwind config block
3. **Extract** — hex values come from `Tailwind config`; CSS class shapes from
   the `<style>` block at the top of `index.html`
4. **Parse** — sort hex values by frequency in HTML; validate with visual
   screenshots; distinguish brand color from incidental screenshot colors
5. **Spec** — always update this file when a new token or component ships.
   Every CSS variable and Tailwind token in new code must trace back here.

---

## 10. Anti-patterns — do not do

- ❌ Pure black (`#000`) — always warm-tinted
- ❌ Pure gray text on colored backgrounds — use a shade of that color
- ❌ Bright saturated blues, greens, reds — the palette is strictly warm
- ❌ Bouncy / elastic / spring animations
- ❌ Drop shadows without amber glow — plain black shadows feel cold
- ❌ Sentence-case labels with wide tracking — only uppercase labels get tracking
- ❌ New button variants — use `btn-gradient` or `btn-ghost`, combine with
  `warm-shine` if you need emphasis
- ❌ New card surfaces — use `glass-card` (+ `iridescent-border` for hero cards)
- ❌ Disabling `warm-shine` globally — its no-shine opt-out (`.no-shine`) exists
  for icon-only buttons and fixed brand marks; elsewhere let it run

---

## 11. File references

| Token source | Path |
|---|---|
| Tailwind theme + keyframes | `web/void/index.html` (lines ~12–78) |
| CSS signature classes | `web/void/index.html` (lines ~180–400) |
| I18N dictionary | `web/void/index.html` (~`const I18N = {...}`) |
| Chat visual patterns | `web/void/components/ChatArena.js` |
| Persona color generator (HSL per id) | `web/void/components/ChatArena.js` (`PERSONA_COLORS` Proxy) |

When in doubt about a pattern, grep the file. When inventing something new,
add its token to the Tailwind config and document it here.

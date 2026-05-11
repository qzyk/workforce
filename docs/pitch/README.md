# Edifico — Pitch Presentation

Prezentare premium **20 slide-uri** pentru promovarea platformei.

| | |
|---|---|
| **Fișier** | [`Edifico-Pitch.pptx`](Edifico-Pitch.pptx) (~96 KB) |
| **Format** | PowerPoint 16:9 |
| **Slide-uri** | 20 |
| **Durată video** | ~2 min 15 sec (animații auto-advance) |
| **Identitate** | Gold #C9A961 · Navy #0B1426 · Cream #F5F1E8 · Cinzel/Inter |

---

## Cuprins slide-uri

| # | Titlu | Conținut |
|---|---|---|
| 1 | **Cover** | Logo Edifico mare + tagline + frame gold |
| 2 | The Problem | 3 stats (65% buget depasit, 30% timp pierdut, 0 platforme accesibile) |
| 3 | The Solution | Value prop + 4 pillars (self-hosted, open, modular, predictabil) |
| 4 | Platform Overview | Grid 4×2 cu cele 8 module |
| 5 | Modul 01 — Workforce | Pontaje, angajati, proiecte + KPI panel |
| 6 | Modul 02 — BIM Core | Hierarchy santier→element + IFC/Federation/QA |
| 7 | Modul 03 — 3D Viewer | APS + xeokit + web-ifc + federation discipline |
| 8 | Modul 04 — CDE Workflow | ISO 19650: WIP→SHARED→PUBLISHED |
| 9 | Modul 05 — Rules + Clash | Cod JSON DSL + 3 tipuri reguli + clash AABB |
| 10 | Modul 06 — 4D + 5D | Schedule (left) + Cost (right) split-view |
| 11 | Modul 07 — Digital Twin | 9 tipuri senzori + ingest API + alerts |
| 12 | Modul 08 — Real-time | SSE + Kanban + presence + comments |
| 13 | Modul 09 — Governance | RBAC + Tokens + COBie + BCF (4 cols) |
| 14 | Standards | ISO 19650 · IFC 4 · BCF 2.1 · COBie 2.4 (4 badges) |
| 15 | Tech Stack | 6 categorii (Backend, DB, Frontend, BIM, Infra, QA) |
| 16 | Security | 6 features 2×3 grid |
| 17 | Mobile PWA | "0 App Store fees" + 4 features |
| 18 | By the Numbers | 8 module · 8 migrations · 401 tests · 16+ services |
| 19 | Why Edifico | Tabel comparativ vs Autodesk vs Solibri |
| 20 | CTA — Hai sa incepi | Big text + URL + decorative E |

---

## Export ca video

### Opțiunea A — PowerPoint Desktop (Windows / macOS)

1. Deschide `Edifico-Pitch.pptx` în Microsoft PowerPoint
2. Meniu **File → Export → Create a Video**
3. Setări recomandate:
   - **Quality**: `Full HD (1080p)` (sau `Ultra HD 4K` dacă vrei premium absolut)
   - **Use Recorded Timings and Narrations**: ✅ activat (fiecare slide are timing inclus)
   - **Seconds spent on each slide**: ignorat (e setat per-slide în XML — 4-8 sec)
4. **Create Video** → alege locație + format `.mp4`
5. PowerPoint randează ~2-5 minute → primești `Edifico-Pitch.mp4` (~10-30 MB)

**Animațiile fade-in + transitions push/wipe/morph/fade vor fi renderate corect.**

### Opțiunea B — Keynote (macOS)

1. Deschide `Edifico-Pitch.pptx` în Keynote → Keynote convertește automat
2. **File → Export To → Movie**
3. Selectează rezoluție 1920×1080 + "Self-playing"
4. Export → `.mov` sau `.mp4`

### Opțiunea C — Google Slides

1. Upload în Google Drive → deschide cu Google Slides
2. ⚠️ Google Slides **nu suportă export video direct**. Folosește Opțiunea A.

### Opțiunea D — Online conversion (fallback)

Servicii ca https://www.aspose.app/slides/conversion/pptx-to-mp4/ sau Cloudconvert primesc `.pptx` și returnează `.mp4`. ⚠️ Verifică privacy policy — fișierul tău include brand-ul tău.

---

## Animații incluse (auto-applied)

### Per slide — Transitions
Alternate ciclic între 4 tipuri pentru variație vizuală:
- **Fade** — slides 1, 5, 9, 13, 17
- **Push** (left→right) — slides 2, 6, 10, 14, 18
- **Wipe** — slides 3, 7, 11, 15, 19
- **Morph** (PowerPoint 2016+, fallback fade) — slides 4, 8, 12, 16, 20

### Per element — Fade-in build
- Fiecare shape/text apare cu **fade 0.5s**
- Delay 0.3s între elemente consecutive
- Pe slide-uri cu multe elemente, primele 12 sunt animate (limit pentru a evita supraîncărcare)
- Resultat: titlul apare primul, apoi bullets se construiesc unul câte unul

### Auto-advance timings
| Slide | Durată | Tip |
|---|---|---|
| 1 (Cover) | 4.0s | Splash rapid |
| 2-3 (Problem/Solution) | 6.5s | Time pentru a citi |
| 4 (Modules grid) | 8.0s | 8 cards de absorbit |
| 5-13 (Module deep-dive) | 7.0s | Standard module |
| 14, 17 | 6.5s | Visual-heavy |
| 15-16, 18 | 7.0s | Stats + stack |
| 19 (Comparison) | 8.0s | Tabel mai dens |
| 20 (CTA) | 5.0s | Finalizare |

**Total**: ~135 secunde = **2 min 15 sec** video.

---

## Editare prezentare

### Modificare conținut (text, culori, layout)
Editează direct în PowerPoint / Keynote — toate elementele sunt **shape-uri nativ**e (nu imagini), deci poți schimba culori/dimensiuni/text fără să pierzi calitatea.

### Regenerare de la zero
```bash
cd docs/pitch
node build_pitch.js                          # 1. Genereaza .pptx clean
python3 add_video_timings.py                 # 2. Adauga transitions + timings
python3 add_per_element_animations.py        # 3. Adauga fade-in per element
# Output: edifico_pitch_final.pptx
```

Pentru a modifica timings: editează `SLIDE_TIMINGS` dict în `add_video_timings.py`.
Pentru a modifica tipuri transition: editează `TRANSITIONS` list.

### Dependențe pentru regenerare
```bash
npm install -g pptxgenjs react react-dom react-icons sharp
```

Python: `python-pptx` nu e necesar — scripturile folosesc doar manipulare XML + zipfile (stdlib).

---

## Distribuție recomandată

- **LinkedIn post**: încarcă MP4-ul direct, descrip cu link
- **Email investitori / clienți**: atașează `.pptx` (96 KB, mic) sau MP4 hostat
- **Website Edifico**: integrează MP4 ca hero video pe homepage
- **YouTube**: setează ca "Edifico — Platform overview" public + descriere cu link `edifico.space`

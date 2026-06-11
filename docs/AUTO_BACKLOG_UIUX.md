# Backlog UI/UX — loop continuu de imbunatatire

> Pentru agentul automat `edifico-uiux` (si oricine lucreaza pe interfata).
> Reguli: UN item per rulare; bifeaza `[x]` cand termini; strict aditiv (nu rescrie
> pagini intregi); doar template-uri / static/css / i18n — fara logica, fara DB,
> fara dependinte noi. Brand: gold #C9A961, navy #0B1426, cream #F5F1E8,
> Cinzel + Inter. Verificare obligatorie: suita de teste verde + render pe
> template-urile atinse.
> Sursa: audit UI/UX cu 6 agenti (39 constatari), 2026-06-11.

## Critice

- [ ] **Defineste variabilele CSS fantoma** (static/css/style.css, critic/S): 9 variabile folosite masiv in template-uri dar nedefinite in `:root` (`--text-muted`, `--primary` etc. — vezi grep `var(--` in templates/ vs definitiile din style.css). Adauga-le in `:root` mapate pe paleta brand. Repara stiluri picate silentios in 10+ pagini.
- [ ] **Banca de preturi in navigare + submenu Gantt** (templates/base.html, critic/S): /banca-preturi e pagina orfana (zero intrari in meniu; gated pe flag `banca-preturi` — afiseaza intrarea cu `feature_enabled('banca-preturi')`). Adauga si submenu la Planificare Gantt: Planificare, Planuri salvate, Obiective (F1-F3), Configurare.
- [ ] **Tabelul banca de preturi utilizabil pe mobil** (templates/banca_preturi/lista.html, critic/S): tabelul cu 8 coloane e taiat (clipat) pe telefon. Inveleste-l in `.table-responsive` (overflow-x:auto) si redu coloanele vizibile pe ecran mic (ex. ascunde Sursa/Furnizor cu o clasa `@media`).

## Majore (efort mic)

- [ ] **Empty-states fara comenzi CLI** (templates/gantt/obiective_lista.html + banca_preturi/lista.html, maj/S): empty-state-urile trimit utilizatori non-tehnici la `flask ...`. Inlocuieste cu indicatie spre actiunea din UI (formularul de upload de mai sus / butonul "Adauga pret").
- [ ] **Upload obiectiv: loading state + anti dublu-submit** (templates/gantt/obiective_lista.html, maj/S): la submit, disable pe buton + text "Se incarca..." (vanilla JS, 5 linii) — ingestia dureaza la fisiere mari.
- [ ] **Contrast text informativ** (static/css/style.css + template-uri, maj/S): gray-400/gray-500 pe fundal deschis are ~2.4:1 (sub WCAG 4.5:1). Defineste `--text-muted` cu un gri >= gray-600 si foloseste-l in locul gri-urilor deschise pe text.
- [ ] **Label-uri pe inputuri + aria pe butoane icon-only** (obiective_lista.html, banca_preturi/lista.html, base.html, maj/S): file-upload si filtrele au doar placeholder; flash-close/sidebar-toggle/actiunile din tabele n-au nume accesibil. Adauga `<label>` (vizibil sau sr-only) + `aria-label`.
- [ ] **Focus states vizibile** (static/css/style.css, maj/S): adauga `:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }` pe butoane/linkuri/inputuri.
- [ ] **Touch targets 44px in tabele** (static/css/style.css, maj/S): `.btn-action` are ~30px; ridica la min 44x44 (padding) pe ecrane touch (`@media (pointer: coarse)`).
- [ ] **PWA pentru teren** (static/manifest.webmanifest + templates/base.html, maj/S): shortcuts duc la BIM/Activitati — schimba-le in "Pontaj rapid" (/teren/pontaj) si "Raport teren" (/teren). Adauga `viewport-fit=cover` + `env(safe-area-inset-*)` pt iPhone instalat ca PWA.
- [ ] **Header mobil descongestionat** (templates/base.html + style.css, maj/S): pe <480px cautarea + pastilele de limba se inghesuie; cautarea devine iconita care expandeaza.
- [ ] **Clasa .badge-pill reutilizabila** (static/css/style.css, maj/S): pill-badge-urile sunt construite inline in 26 de locuri. Creeaza `.badge-pill` (+ variante `.badge-gold`, `.badge-muted`) si aplic-o intai in banca_preturi/lista.html si gantt/obiective_lista.html (restul gradual).
- [ ] **Clasa .gradient-gold / .btn-gold** (static/css/style.css, maj/S): gradientul de brand e copiat inline in 24 de locuri. O clasa unica; inlocuieste intai in templates/gantt/*.html.
- [ ] **Feature-flag coerent pe dashboard** (templates/dashboard.html, maj/S): meniul ascunde Gantt/Contracte pe flag, dar dashboard-ul afiseaza link-urile oricum → 404-uri aparente. Gate-uieste aceleasi link-uri cu `feature_enabled(...)`.

## Majore (efort mediu)

- [ ] **Quick actions pe dashboard** (templates/dashboard.html, maj/M): actiunile frecvente (Pontaj azi, Raport nou, Incarca deviz, Plan Gantt) sunt la 3-4 click-uri. Adauga un rand de 4 butoane mari sub header-ul dashboard-ului.
- [ ] **i18n pe paginile noi** (templates/banca_preturi/*, templates/gantt/obiective_*.html + i18n.py, maj/M): zero `_()` — switcher-ul EN nu are efect. Inveleste textele si adauga cheile EN in TRANSLATIONS.
- [ ] **Legatura Obiectiv ↔ Proiect vizibila** (templates/gantt/obiectiv_detalii.html + obiective_lista.html, maj/M): exista in model (proiect_id) dar nu se vede si nu se seteaza din UI. Afiseaza proiectul (link) + dropdown de asociere la upload.
- [ ] **Card-statistica unificat** (static/css/style.css + contracte/gantt/banca_preturi, maj/M): 3 implementari paralele de card-stat. O clasa `.card-stat` (label + valoare + sub-text); aplic-o in cele 3 module.
- [ ] **planuri.html aliniat vizual** (templates/gantt/planuri.html, maj/M): are limbaj vizual propriu diferit de paginile noi; aliniaza la data-table + card-panel + badge-pill.

## Minore

- [ ] **O singura conventie de breadcrumb** (template-uri diverse, min/S): doua formate incompatibile in acelasi `<ol>`; standardizeaza pe `<li class="breadcrumb-item">` peste tot (incepe cu gantt/* si banca_preturi/*).
- [ ] **Stepper Gantt navigabil** (templates/gantt/_stepper.html, min/M): pasii finalizati devin linkuri catre pasul respectiv.

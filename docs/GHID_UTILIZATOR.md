# Ghid de utilizator — Edifico Workforce

*One platform, all your sites.*

Acest ghid e scris simplu, pas cu pas, pentru oricine — nu ai nevoie de cunostinte tehnice.
Edifico este locul unde tii la un loc tot ce tine de santierele si proiectele tale:
oameni, pontaje, devize, planificare, costuri, utilaje, documente.

---

## 1. Primii pasi

1. **Intra in cont** la `www.edifico.space` cu emailul si parola primite.
2. Ajungi pe **Tabloul de bord** (Dashboard) — o privire de ansamblu: cati angajati activi ai,
   cate proiecte, orele lunii, alerte.
3. **Meniul** din stanga e impartit pe sectiuni, ca sa gasesti usor:
   - **Operational** — Proiecte, Pontaje, Teren, Activitati
   - **Planificare & cost** — Planificare Gantt, BIM, Contracte
   - **Resurse** — Angajati, Masini
   - **Documente & rapoarte**
   - **Administrare** (doar pentru administrator) — Setari, Module, etc.

> **Sfat — cautare rapida:** apasa **Ctrl + K** (sau Cmd + K pe Mac) din orice pagina si scrie
> ce cauti (un proiect, un plan, un santier, un angajat). Sari direct acolo, fara sa cauti prin meniu.

> **Limba:** sus, in dreapta, poti comuta intre Romana si Engleza (🇷🇴 / 🇬🇧).

---

## 2. Cum incepi un proiect (fluxul de baza)

Gandeste-te la un proiect ca la o calatorie cu pasi clari. Le poti vedea pe toate intr-un singur loc:

1. **Adaugi proiectul** — meniul *Proiecte* → buton *Adauga proiect* (cod, nume, beneficiar, data de start).
2. **Deschizi "Hub 360"** al proiectului (din lista de proiecte sau de pe pagina lui).
   Acolo vezi **Parcursul proiectului** — o banda cu pasii, fiecare marcat ca *facut* sau *de facut*,
   cu pasul urmator evidentiat:

   > Deviz → Planificare (Gantt) → Structura lucrarilor (WBS) → Cost → Utilaje → Avans (EVM)

3. Apesi pe pasul urmator si te duce direct unde trebuie.

Pe scurt: **adaugi proiectul → incarci devizul → planifici → urmaresti executia → vezi avansul.**

---

## 3. Planificarea lucrarilor din deviz (cea mai folosita unealta)

Aici transformi **lista de cantitati (devizul, formularul F3)** intr-un **plan de lucru** automat.

### Pas cu pas
1. Meniul *Planificare Gantt*.
2. **Incarci fisierul** cu lista de cantitati (Excel sau CSV) — il tragi cu mouse-ul sau il alegi.
3. Lasi bifat **"Clasificare automata"** daca vrei ca aplicatia sa recunoasca singura tipul
   lucrarilor (sapatura, cofraj, armare, turnare beton, termosistem...). Daca fisierul tau are
   deja o coloana cu categoria si vrei sa o pastrezi, debifezi.
4. Apesi **Genereaza planificarea**. Aplicatia citeste fiecare articol, calculeaza **durata** si
   **costul real** (impartit pe **materiale / manopera / utilaje**), si construieste planul.

### Ce vezi dupa generare
- **Lista de activitati** cu cantitati, durate si costuri.
- **Centralizatorul F2** — costul grupat pe categorii de lucrari (material, manopera, utilaje, total).
- **Resurse in timp & cash-flow** — un grafic care arata *cati bani pe luna* iti trebuie si *varful*
  de cheltuieli (poti comuta intre Lunar si Saptamanal).
- **Diagrama Gantt** — barele in timp, cu drumul critic (lucrarile care nu pot intarzia) marcate.
- Butoane de **export** catre MS Project, Primavera P6 sau CSV.

### Salvare si structura lucrarilor (WBS)
- Ca sa pastrezi planul si sa-l poti modifica, apasa **"Salveaza si editeaza WBS"**.
- Se deschide **editorul de structura**: aici poti **redenumi** capitole/activitati (scrii si apesi Enter),
  le poti **reordona** (sagetile sus/jos), le poti **muta** in alt grup, **adauga** grupuri noi, sau
  **reseta** la structura automata. Modificarile tale apar si in plan, si in export.

> **De retinut:** editorul de structura functioneaza doar pe un plan **salvat**. Daca esti inca in
> previzualizare (imediat dupa incarcare), foloseste butonul **"Salveaza si editeaza WBS"**.

> **Daca duratele par prea mari:** vin din *randamentele* (cat se face pe zi la fiecare categorie).
> Le reglezi din *Planificare Gantt → Configurare → Randamente*.

---

## 4. Resursele din deviz (C6 materiale, C7 manopera, C8 utilaje)

Pe langa lista de cantitati (F3), devizul standard are si **extrasele de resurse**:
- **C6** = lista materialelor (cu cantitati si furnizori),
- **C7** = manopera (orele pe meserii),
- **C8** = utilajele (orele de functionare).

### Cum le incarci
1. Deschizi proiectul → **Resurse** (sau din Hub 360, cardul *Resurse C6/C7/C8*).
2. **Incarci fisierele pe rand** — aplicatia recunoaste singura ce tip e fiecare (C6/C7/C8).
3. Vezi 3 liste, fiecare cu total si numar de resurse. Daca reincarci acelasi tip, il inlocuieste.

### Ce poti face cu ele
- **Necesar materiale (CSV)** — descarci lista de comanda, grupata pe furnizor, gata de trimis.
- **Reconciliere F3 ↔ extrase** — un tabel iti arata daca sumele din plan se potrivesc cu extrasele
  (verde = concorda, galben = verifica, rosu = diferenta mare). Prinde greselile de deviz inainte de ofertare.

### Conexiunea reala F3 ↔ resurse
Apesi pe **"Conexiune F3 ↔ resurse"**. Aici aplicatia leaga fiecare resursa de lucrarile care o folosesc:
- **Reconciliere pe fiecare articol** (nu doar pe total) — vezi exact ce resursa nu se potriveste.
- **Necesar pe luni, per resursa** — cand si cat din fiecare material/manopera/utilaj iti trebuie.
- **Drill-down** — pentru fiecare resursa, in ce activitati e folosita si in ce perioade.

---

## 5. Pontaje si lucru din teren

### Pontaje (de la birou)
- Meniul *Pontaje* → *Adauga pontaj* (angajat, proiect, ore, ziua). Poti adauga si pontaje in masa.
- Vezi calendarul, situatia zilnica, si poti trimite pontajele spre aprobare.

### Teren (de pe telefon)
Cea mai rapida cale, direct de pe santier:
1. Meniul *Teren*.
2. **Pontaj rapid** — alegi proiectul, apesi un buton de ore (4/6/8/10/12), salvezi. Gata in 3 atingeri.
3. **Raporteaza problema** — scrii ce ai observat, alegi gravitatea, optional santierul. Ajunge in lista de probleme.

> **Sfat:** poti instala aplicatia pe telefon (ca o aplicatie obisnuita) din meniul *Instaleaza app*.

---

## 6. Urmarirea executiei: utilaje si avans (EVM)

### Utilaje
- Proiect → **Utilaje**: inregistrezi consumul real (ce utilaj, ore, tarif). Costul se calculeaza singur.
- Sus vezi **planificat vs real** si diferenta.

### Avans (EVM = planificat vs realizat)
- Proiect → **EVM**: compara *cat ar fi trebuit facut* (din plan) cu *cat s-a facut* (din situatii).
- Indicatorii:
  - **Avans %** — cat e gata.
  - **SPI** — esti inaintea sau in urma graficului (peste 1 = bine).
  - **CPI** — esti sub sau peste buget (peste 1 = bine).
- Daca un proiect e in risc (SPI/CPI sub prag), managerul primeste o notificare automata.

---

## 7. Contracte, oferte si situatii (modul optional)

Daca e activat, modulul *Contracte* tine:
- **Contractele** si valorile lor,
- **Ofertele / devizele** pretuite,
- **Situatiile lunare** de lucrari (avansul facturat),
- **Procesele verbale** si **termenele** (cu alerte cand se apropie scadenta).

Aceste date alimenteaza automat **avansul (EVM)** al proiectului.

---

## 8. BIM — modelul 3D al cladirii (pentru proiecte modelate)

Daca lucrezi cu modele 3D (IFC), modulul *BIM* iti da:
- **Arborele** santierelor → cladiri → niveluri → spatii → elemente.
- **Modele 3D** pe care le vizualizezi in browser, cu o animatie **4D** (cum se construieste in timp).
- **Antemasuratoarea (QTO)** — cantitatile extrase direct din model, pe care le poti trimite in planificare.
- **Probleme (Issues)** si verificari de calitate.

> Multe functii BIM sunt **optionale** si pornite separat (vezi *Module*). Daca nu lucrezi cu modele
> 3D, poti ignora linistit acest modul.

---

## 9. Restul: masini, documente, rapoarte

- **Masini** — parcul auto: documente (ITP, RCA, CASCO) cu alerte de expirare, foi de parcurs, defectiuni.
- **Documente** — fisiere pe proiecte (contracte, planse, poze), cu alerte de expirare.
- **Rapoarte** — situatii si exporturi pentru management.

---

## 10. Setari (pentru administrator)

- **Firma** — datele companiei.
- **Utilizatori** — cine are acces si ce rol are (administrator / manager / operator).
- **Sarbatori** — calendarul de sarbatori legale (folosit la pontaje).
- **Backup** — copii de siguranta ale datelor:
  - *Backup complet* (baza de date + fisiere),
  - *Snapshot DB* (rapid, doar datele),
  - **backup automat zilnic** (se face singur si pastreaza ultimele copii).
  Poti descarca oricare copie.
- **Module si functii** — activezi/dezactivezi functii optionale (ex. modulul BIM, contracte).

> **Datele tale sunt la tine** — totul sta pe serverul tau, fara servicii externe.

---

## 11. Intrebari frecvente

**Nu gasesc un buton / o functie.**
Foloseste cautarea rapida (**Ctrl + K**). Daca tine de o functie optionala, verifica in
*Administrare → Module si functii* daca e pornita.

**Am incarcat un deviz si costurile par estimate, nu reale.**
Asigura-te ca fisierul are coloanele de pret (Pretul unitar / Total) si, daca e deviz cu extrase,
randurile *material: / manopera: / utilaj:* sub fiecare articol. Aplicatia le citeste automat.

**Nu pot edita structura (WBS).**
Editorul merge doar pe un plan **salvat**. Din previzualizare, apasa *"Salveaza si editeaza WBS"*.

**Planul iese pe prea multe luni.**
Regleaza *randamentele* (cat se executa pe zi) din *Planificare Gantt → Configurare*.

**Vreau lista de materiale pentru comanda.**
Proiect → *Resurse* → *Necesar materiale (CSV)*. E grupata pe furnizor.

---

## 12. Glosar simplu

- **Deviz / F3 (lista de cantitati)** — tabelul cu ce lucrari se fac si in ce cantitati.
- **C6 / C7 / C8** — extrasele de resurse din deviz: materiale / manopera / utilaje.
- **WBS (structura lucrarilor)** — felul in care sunt organizate lucrarile: capitole → activitati.
- **Gantt** — graficul cu lucrarile asezate in timp (bare).
- **Drum critic** — lantul de lucrari care nu pot intarzia fara sa intarzie tot proiectul.
- **Cash-flow** — banii de care ai nevoie, esalonati pe perioade.
- **EVM (avans)** — compararea a ceea ce ar fi trebuit facut cu ce s-a facut (SPI, CPI).
- **QTO (antemasuratoare)** — cantitatile scoase automat din modelul 3D.

---

*Pentru orice nelamurire, intreaba administratorul aplicatiei.*

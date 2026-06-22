"""
Serviciu pentru generarea + exportul situatiilor lunare (Faza 12).

3 functii publice:
  - genereaza_situatie(contract_id, an, luna, user_id) -> SituatieLunara
    Agrega cantitatile EXECUTATE+VALIDATE ale lunii X pentru toate pozitiile
    BoQ din contract. Creeaza/actualizeaza SituatieLunara cu valoare totala
    + cumulat la zi + procent avans.

  - export_situatie_xlsx(situatie_id) -> str (path absolut)
    Export Excel format romanesc (Antet + tabel pozitii + recapitulatie).

  - export_situatie_pdf(situatie_id) -> str (path absolut)
    Export PDF cu acelasi continut (reportlab).

Atentie: NU sterge situatii existente. Daca exista deja o situatie pentru
(proiect, an, luna), o reutilizeaza si actualizeaza valorile.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from flask import current_app

from models import (
    db, Contract, OfertaContract, PozitieBoQ, CantitateExecutataLunara,
    SituatieLunara,
)


LUNI_RO = {
    1: 'Ianuarie', 2: 'Februarie', 3: 'Martie', 4: 'Aprilie',
    5: 'Mai', 6: 'Iunie', 7: 'Iulie', 8: 'August',
    9: 'Septembrie', 10: 'Octombrie', 11: 'Noiembrie', 12: 'Decembrie',
}


def genereaza_situatie(contract_id: int, an: int, luna: int,
                       user_id: Optional[int] = None,
                       doar_validate: bool = True) -> SituatieLunara:
    """
    Genereaza (sau regenereaza) o SituatieLunara pentru (contract, an, luna).

    Algoritm:
      1. Verifica existenta SituatieLunara pentru (proiect_id, an, luna).
         Daca exista, o reutilizeaza (update); altfel creeaza una noua.
      2. Pentru fiecare PozitieBoQ asociata contractului (via oferte),
         agreaga cantitatile executate ale lunii X (filtru validat=True
         daca doar_validate=True; altfel toate).
      3. Calculeaza valoare_totala_luna = sum(cant_luna * pret_unitar).
      4. Calculeaza valoare_cumulat_la_zi = sum din toate lunile <= (an, luna).
      5. Procent avans = cumulat / valoare_totala_oferta_aprobata * 100.
      6. Status default: draft (poate fi schimbat ulterior).

    Returneaza SituatieLunara (commit-uit).
    """
    contract = Contract.query.get(contract_id)
    if contract is None:
        raise ValueError(f'Contract id={contract_id} nu exista.')

    # 1. Caut situatia existenta sau creez una noua
    situatie = SituatieLunara.query.filter_by(
        proiect_id=contract.proiect_id, an=an, luna=luna,
    ).first()
    if situatie is None:
        situatie = SituatieLunara(
            proiect_id=contract.proiect_id,
            contract_id=contract.id,
            an=an, luna=luna,
            data_emitere=date.today(),
            status='draft',
            creat_de_id=user_id,
        )
        db.session.add(situatie)
        db.session.flush()

    # 2. Identific TOATE pozitiile BoQ asociate contractului
    pozitie_ids_query = db.session.query(PozitieBoQ.id).join(
        OfertaContract, PozitieBoQ.oferta_id == OfertaContract.id
    ).filter(OfertaContract.contract_id == contract.id)
    pozitie_ids = [pid for (pid,) in pozitie_ids_query.all()]

    if not pozitie_ids:
        situatie.valoare_totala_luna = Decimal('0')
        situatie.valoare_cumulat_la_zi = Decimal('0')
        situatie.procent_avans_total = Decimal('0')
        db.session.commit()
        return situatie

    # 3. Cantitati lunare pentru luna X
    q_luna = CantitateExecutataLunara.query.filter(
        CantitateExecutataLunara.pozitie_boq_id.in_(pozitie_ids),
        CantitateExecutataLunara.an == an,
        CantitateExecutataLunara.luna == luna,
    )
    if doar_validate:
        q_luna = q_luna.filter(CantitateExecutataLunara.validat == True)
    cantitati_luna = q_luna.all()

    valoare_luna = Decimal('0')
    for c in cantitati_luna:
        # Calc + persist valoare_calculata pe cantitate daca lipseste
        pret = c.pozitie_boq.pret_unitar or Decimal('0')
        val = (c.cantitate_executata or Decimal('0')) * pret
        c.valoare_calculata = val
        valoare_luna += val

    # 4. Cumulat la zi: toate cantitatile (an, luna) <= (curentul)
    q_cumul = CantitateExecutataLunara.query.filter(
        CantitateExecutataLunara.pozitie_boq_id.in_(pozitie_ids),
        db.or_(
            CantitateExecutataLunara.an < an,
            db.and_(
                CantitateExecutataLunara.an == an,
                CantitateExecutataLunara.luna <= luna,
            ),
        ),
    )
    if doar_validate:
        q_cumul = q_cumul.filter(CantitateExecutataLunara.validat == True)
    cumul = Decimal('0')
    for c in q_cumul.all():
        pret = c.pozitie_boq.pret_unitar or Decimal('0')
        cumul += (c.cantitate_executata or Decimal('0')) * pret

    # 5. Valoare oferta aprobata (totala contract)
    valoare_oferta = db.session.query(
        db.func.sum(OfertaContract.valoare_totala)
    ).filter(
        OfertaContract.contract_id == contract.id,
        OfertaContract.aprobata == True,
    ).scalar()
    if not valoare_oferta or valoare_oferta == 0:
        # Fallback: cea mai recenta versiune oferta (aprobata sau nu)
        cea_recenta = OfertaContract.query.filter_by(
            contract_id=contract.id
        ).order_by(OfertaContract.versiune.desc()).first()
        valoare_oferta = (cea_recenta.valoare_totala
                          if cea_recenta and cea_recenta.valoare_totala
                          else Decimal('0'))

    procent = Decimal('0')
    if valoare_oferta and valoare_oferta > 0:
        procent = (cumul / valoare_oferta * 100).quantize(Decimal('0.01'))

    situatie.valoare_totala_luna = valoare_luna
    situatie.valoare_cumulat_la_zi = cumul
    situatie.procent_avans_total = procent

    # Deviz Faza 3 - retentii + garantii pe situatie (gated pe flag).
    # Cu OFF: nu atingem coloanele noi (raman NULL), situatia ramane ca azi.
    _aplica_retentii_garantii(situatie, contract, valoare_luna)

    db.session.commit()
    return situatie


def _aplica_retentii_garantii(situatie: SituatieLunara, contract: Contract,
                              valoare_luna: Decimal) -> None:
    """
    Calculeaza retentia, garantia de buna executie si plata neta a lunii.

    Gated pe flag 'situatii-retentii' (default OFF). Cu OFF, coloanele noi raman
    NULL si situatia ramane identica cu cea istorica (zero regresie).

    Formula RO (situatie de lucrari):
        retentie_suma    = valoare_totala_luna * retentie_procent / 100
        garantie_bex_suma= valoare_totala_luna * garantie_bex_procent / 100
        plata_neta       = valoare_totala_luna - retentie_suma
                                               - garantie_bex_suma
                                               - avans_recuperat

    Procentele implicite vin de pe contract (retentie_procent_default,
    garantie_bex_procent). avans_recuperat se pastreaza ca atare daca a fost
    introdus manual (altfel 0) - recuperarea avansului e o decizie comerciala,
    nu o derivam automat.

    Discriminator de editare manuala: coloana explicita
    SituatieLunara.retentii_editate_manual, setata DOAR de ruta
    situatie_retentii. Cand e False/NULL (inclusiv la auto-generarea anterioara),
    recalculam INTOTDEAUNA retentie_suma + garantie_bex_suma din
    valoare_luna * procent, ca sumele sa urmareasca valoarea lunii la fiecare
    regenerare (ex. cand se valideaza cantitati noi). Cand e True, pastram sumele
    introduse manual si recalculam doar plata neta. NU folosim 'sumele sunt
    non-NULL' ca discriminator: prima auto-populare le face non-NULL si s-ar
    masca drept editare manuala (sume inghetate, plata neta desincronizata).
    """
    try:
        from services.feature_flags import is_enabled
        activ = is_enabled('situatii-retentii')
    except Exception:
        activ = False
    if not activ:
        return

    editat_manual = bool(situatie.retentii_editate_manual)

    if editat_manual:
        # Editare manuala reala (via ruta): pastram procentul + sumele introduse,
        # recalculam doar plata neta din valoarea lunii curente.
        retentie_procent = Decimal(situatie.retentie_procent or 0)
        retentie_suma = Decimal(situatie.retentie_suma or 0)
        garantie_bex = Decimal(situatie.garantie_bex_suma or 0)
    else:
        # Auto-generare: recalculam mereu sumele din procent * valoare_luna.
        # Procent retentie: valoarea persistata pe situatie are prioritate (ex.
        # mostenita la o generare anterioara), altfel din contract; fallback 0.
        if situatie.retentie_procent is not None:
            retentie_procent = Decimal(situatie.retentie_procent)
        else:
            retentie_procent = Decimal(contract.retentie_procent_default or 0)
        garantie_bex_procent = Decimal(contract.garantie_bex_procent or 0)
        retentie_suma = (valoare_luna * retentie_procent / 100).quantize(Decimal('0.01'))
        garantie_bex = (valoare_luna * garantie_bex_procent / 100).quantize(Decimal('0.01'))

    avans_recuperat = Decimal(situatie.avans_recuperat or 0)
    plata_neta = (valoare_luna - retentie_suma - garantie_bex - avans_recuperat)

    situatie.retentie_procent = retentie_procent
    situatie.retentie_suma = retentie_suma
    situatie.garantie_bex_suma = garantie_bex
    situatie.avans_recuperat = avans_recuperat
    situatie.plata_neta = plata_neta.quantize(Decimal('0.01'))


def _get_upload_dir(subdir: str) -> str:
    """Returneaza calea catre uploads/<subdir>/ si o creeaza daca lipseste."""
    base = current_app.config.get(
        'UPLOAD_FOLDER',
        os.path.join(current_app.root_path, 'uploads')
    )
    path = os.path.join(base, subdir)
    os.makedirs(path, exist_ok=True)
    return path


def _get_situatie_data(situatie: SituatieLunara) -> dict:
    """Construieste structura de date completa pentru exporturi."""
    contract = situatie.contract
    proiect = situatie.proiect
    # Toate pozitiile BoQ pentru contract via oferte
    pozitii = PozitieBoQ.query.join(
        OfertaContract, PozitieBoQ.oferta_id == OfertaContract.id
    ).filter(OfertaContract.contract_id == contract.id).order_by(
        PozitieBoQ.cod_capitol, PozitieBoQ.ordine
    ).all()

    # Cantitati pentru luna situatiei (filtrare incluziva cu validat)
    cantitati_luna_map = {}
    for cant in CantitateExecutataLunara.query.filter(
        CantitateExecutataLunara.pozitie_boq_id.in_([p.id for p in pozitii]),
        CantitateExecutataLunara.an == situatie.an,
        CantitateExecutataLunara.luna == situatie.luna,
    ).all():
        cantitati_luna_map[cant.pozitie_boq_id] = cant

    # Cumul la zi: sum cantitati <= (an, luna) per pozitie
    cumul_map: dict[int, Decimal] = {}
    for cant in CantitateExecutataLunara.query.filter(
        CantitateExecutataLunara.pozitie_boq_id.in_([p.id for p in pozitii]),
        db.or_(
            CantitateExecutataLunara.an < situatie.an,
            db.and_(
                CantitateExecutataLunara.an == situatie.an,
                CantitateExecutataLunara.luna <= situatie.luna,
            ),
        ),
    ).all():
        cumul_map[cant.pozitie_boq_id] = (
            cumul_map.get(cant.pozitie_boq_id, Decimal('0'))
            + (cant.cantitate_executata or Decimal('0'))
        )

    rows = []
    for p in pozitii:
        cant_luna = cantitati_luna_map.get(p.id)
        cant_cumul = cumul_map.get(p.id, Decimal('0'))
        val_luna = ((cant_luna.cantitate_executata or Decimal('0'))
                    * (p.pret_unitar or Decimal('0'))) if cant_luna else Decimal('0')
        val_cumul = cant_cumul * (p.pret_unitar or Decimal('0'))
        val_oferta = (p.cantitate_oferta or Decimal('0')) * (p.pret_unitar or Decimal('0'))
        rows.append({
            'cod_articol': p.cod_articol,
            'cod_capitol': p.cod_capitol or '',
            'denumire': p.denumire,
            'um': p.um,
            'cant_oferta': p.cantitate_oferta or Decimal('0'),
            'pret_unitar': p.pret_unitar or Decimal('0'),
            'val_oferta': val_oferta,
            'cant_luna': cant_luna.cantitate_executata if cant_luna else Decimal('0'),
            'val_luna': val_luna,
            'cant_cumul': cant_cumul,
            'val_cumul': val_cumul,
            'categorie': p.categorie,
        })

    return {
        'situatie': situatie,
        'contract': contract,
        'proiect': proiect,
        'rows': rows,
        'luna_text': LUNI_RO.get(situatie.luna, str(situatie.luna)),
    }


def export_situatie_xlsx(situatie_id: int) -> str:
    """Export Excel pentru SituatieLunara. Returneaza path-ul fisierului."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    situatie = SituatieLunara.query.get(situatie_id)
    if situatie is None:
        raise ValueError(f'Situatie id={situatie_id} nu exista.')

    data = _get_situatie_data(situatie)
    rows = data['rows']
    contract = data['contract']
    proiect = data['proiect']

    wb = Workbook()
    ws = wb.active
    ws.title = f'Situatie {situatie.an}-{situatie.luna:02d}'

    bold = Font(bold=True)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    gold_fill = PatternFill('solid', fgColor='C9A961')
    thin = Side(border_style='thin', color='888888')
    bord = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ---- Antet ----
    ws['A1'] = 'SITUATIE DE LUCRARI'
    ws['A1'].font = Font(bold=True, size=14, color='0B1426')
    ws.merge_cells('A1:K1')
    ws['A1'].alignment = center
    ws.row_dimensions[1].height = 26

    ws['A2'] = f'Luna: {data["luna_text"]} {situatie.an}'
    ws['A2'].font = bold
    ws.merge_cells('A2:E2')
    ws['F2'] = f'Numar situatie: {situatie.numar_situatie or "-"}'
    ws.merge_cells('F2:K2')
    ws['A3'] = f'Proiect: {proiect.cod_proiect} - {proiect.nume}'
    ws.merge_cells('A3:K3')
    ws['A4'] = f'Contract: {contract.nr_contract}'
    ws['F4'] = f'Beneficiar: {contract.beneficiar or "-"}'
    ws.merge_cells('A4:E4')
    ws.merge_cells('F4:K4')

    # ---- Header tabel ----
    hdr_row = 6
    headers = [
        'Cod articol', 'Capitol', 'Denumire', 'UM',
        'Cant. ofertă', 'Preț unitar', 'Val. ofertă',
        'Cant. lună', 'Val. lună', 'Cant. cumul.', 'Val. cumul.',
    ]
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(row=hdr_row, column=i, value=h)
        cell.font = bold
        cell.fill = gold_fill
        cell.alignment = center
        cell.border = bord
    ws.row_dimensions[hdr_row].height = 30

    # ---- Pozitii ----
    r = hdr_row + 1
    total_luna = Decimal('0')
    total_cumul = Decimal('0')
    total_oferta = Decimal('0')
    for row in rows:
        # Skip pozitiile care nu au activitate lunara SI nu au cumul
        # (filtru optional, pastram pentru transparenta - aici lasam toate)
        ws.cell(row=r, column=1, value=row['cod_articol']).border = bord
        ws.cell(row=r, column=2, value=row['cod_capitol']).border = bord
        ws.cell(row=r, column=3, value=row['denumire']).border = bord
        ws.cell(row=r, column=4, value=row['um']).alignment = center
        ws.cell(row=r, column=4).border = bord
        ws.cell(row=r, column=5, value=float(row['cant_oferta'])).border = bord
        ws.cell(row=r, column=6, value=float(row['pret_unitar'])).border = bord
        ws.cell(row=r, column=7, value=float(row['val_oferta'])).border = bord
        ws.cell(row=r, column=8, value=float(row['cant_luna'])).border = bord
        ws.cell(row=r, column=9, value=float(row['val_luna'])).border = bord
        ws.cell(row=r, column=10, value=float(row['cant_cumul'])).border = bord
        ws.cell(row=r, column=11, value=float(row['val_cumul'])).border = bord
        total_luna += row['val_luna']
        total_cumul += row['val_cumul']
        total_oferta += row['val_oferta']
        r += 1

    # ---- Totaluri ----
    ws.cell(row=r, column=1, value='TOTAL').font = bold
    ws.cell(row=r, column=7, value=float(total_oferta)).font = bold
    ws.cell(row=r, column=9, value=float(total_luna)).font = bold
    ws.cell(row=r, column=11, value=float(total_cumul)).font = bold
    for col in range(1, 12):
        ws.cell(row=r, column=col).fill = gold_fill
        ws.cell(row=r, column=col).border = bord

    # ---- Recapitulatie ----
    r += 2
    ws.cell(row=r, column=1, value='Procent avans total:').font = bold
    ws.cell(row=r, column=2,
            value=f'{situatie.procent_avans_total}%' if situatie.procent_avans_total else '-')
    ws.cell(row=r + 1, column=1, value='Status:').font = bold
    ws.cell(row=r + 1, column=2, value=situatie.status)

    # Latimi coloane
    widths = [16, 16, 40, 6, 12, 12, 14, 12, 14, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    # ---- Salvez ----
    upload_dir = _get_upload_dir('situatii')
    filename = f'situatie_{situatie.proiect_id}_{situatie.an}_{situatie.luna:02d}_{datetime.utcnow():%Y%m%d%H%M%S}.xlsx'
    path = os.path.join(upload_dir, filename)
    wb.save(path)
    situatie.fisier_export_xlsx_path = path
    db.session.commit()
    return path


def export_situatie_pdf(situatie_id: int) -> str:
    """Export PDF pentru SituatieLunara. Returneaza path-ul fisierului."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.lib.units import mm

    situatie = SituatieLunara.query.get(situatie_id)
    if situatie is None:
        raise ValueError(f'Situatie id={situatie_id} nu exista.')

    data = _get_situatie_data(situatie)
    rows = data['rows']
    contract = data['contract']
    proiect = data['proiect']

    upload_dir = _get_upload_dir('situatii')
    filename = f'situatie_{situatie.proiect_id}_{situatie.an}_{situatie.luna:02d}_{datetime.utcnow():%Y%m%d%H%M%S}.pdf'
    path = os.path.join(upload_dir, filename)

    # Rapoarte Faza 2: branding Cinzel/header gated pe flag. Cu OFF, PDF-ul
    # ramane identic cu cel istoric (Helvetica, fara header brandat).
    try:
        from services.feature_flags import is_enabled
        branding_on = is_enabled('rapoarte-pdf-cinzel')
    except Exception:
        branding_on = False

    # Fontul header-ului tabelului: serif brandat cu ON, Helvetica-Bold cu OFF.
    header_font = 'Helvetica-Bold'
    if branding_on:
        try:
            from rapoarte import brand
            _serif, header_font = brand.get_pdf_fonts()
        except Exception:
            header_font = 'Helvetica-Bold'

    doc = SimpleDocTemplate(
        path, pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    elems = []
    styles = getSampleStyleSheet()
    if branding_on:
        # Header brandat Edifico (logo daca exista + wordmark Cinzel + titlu).
        from rapoarte import brand
        elems += brand.pdf_header_elements('SITUATIE DE LUCRARI', cu_logo=True)
    else:
        title_style = ParagraphStyle(
            'title', parent=styles['Title'],
            fontSize=14, textColor=colors.HexColor('#0B1426'),
            alignment=1,
        )
        elems.append(Paragraph('SITUATIE DE LUCRARI', title_style))
        elems.append(Spacer(1, 4 * mm))
    elems.append(Paragraph(
        f'<b>Luna:</b> {data["luna_text"]} {situatie.an} &nbsp;&nbsp; '
        f'<b>Nr. situatie:</b> {situatie.numar_situatie or "-"}',
        styles['Normal']))
    elems.append(Paragraph(
        f'<b>Proiect:</b> {proiect.cod_proiect} - {proiect.nume}',
        styles['Normal']))
    elems.append(Paragraph(
        f'<b>Contract:</b> {contract.nr_contract} &nbsp;&nbsp; '
        f'<b>Beneficiar:</b> {contract.beneficiar or "-"}',
        styles['Normal']))
    elems.append(Spacer(1, 4 * mm))

    # Tabel pozitii (compact)
    table_data = [[
        'Cod', 'Capitol', 'Denumire', 'UM',
        'Cant.of.', 'P.unit.', 'Val.of.',
        'Cant.luna', 'Val.luna', 'Cant.cum.', 'Val.cum.',
    ]]
    total_luna = Decimal('0')
    total_cumul = Decimal('0')
    total_oferta = Decimal('0')
    for row in rows:
        table_data.append([
            row['cod_articol'],
            row['cod_capitol'][:14] if row['cod_capitol'] else '',
            row['denumire'][:55] + ('...' if len(row['denumire']) > 55 else ''),
            row['um'],
            f'{row["cant_oferta"]:.2f}',
            f'{row["pret_unitar"]:.2f}',
            f'{row["val_oferta"]:.2f}',
            f'{row["cant_luna"]:.2f}',
            f'{row["val_luna"]:.2f}',
            f'{row["cant_cumul"]:.2f}',
            f'{row["val_cumul"]:.2f}',
        ])
        total_luna += row['val_luna']
        total_cumul += row['val_cumul']
        total_oferta += row['val_oferta']
    table_data.append([
        'TOTAL', '', '', '', '', '',
        f'{total_oferta:.2f}', '', f'{total_luna:.2f}', '', f'{total_cumul:.2f}',
    ])
    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C9A961')),
        ('TEXTCOLOR', (0, 0), (-1, 0),
         colors.HexColor('#0B1426') if branding_on else colors.white),
        ('FONTNAME', (0, 0), (-1, 0), header_font),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#888888')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F5F1E8')),
        ('FONTNAME', (0, -1), (-1, -1), header_font),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 6 * mm))

    elems.append(Paragraph(
        f'<b>Procent avans total:</b> '
        f'{situatie.procent_avans_total or 0}% &nbsp;&nbsp; '
        f'<b>Status:</b> {situatie.status}',
        styles['Normal']))

    doc.build(elems)

    situatie.fisier_export_pdf_path = path
    db.session.commit()
    return path

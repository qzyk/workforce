"""
INNOVA WORKFORCE - Generator Rapoarte PDF
Rapoarte PDF cu ReportLab: foaie prezenta, stat plata, pontaj individual.
Fallback: daca ReportLab nu e instalat, genereaza Excel in loc.
"""

import os
import calendar
from datetime import date, datetime, timedelta

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, A3, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='TitleCustom', fontSize=16, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1A237E'), alignment=TA_CENTER, spaceAfter=12
    ))
    styles.add(ParagraphStyle(
        name='SubtitleCustom', fontSize=11, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#424242'), alignment=TA_CENTER, spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name='InfoLabel', fontSize=9, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1A237E')
    ))
    styles.add(ParagraphStyle(
        name='Footer', fontSize=7, fontName='Helvetica-Oblique',
        textColor=colors.gray, alignment=TA_CENTER
    ))
    return styles


TABLE_STYLE_BASE = TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A237E')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 8),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 1), (-1, -1), 7),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ('TOPPADDING', (0, 0), (-1, -1), 3),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
])


# ============================================================
# 1. PDF FOAIE PREZENTA
# ============================================================

def generate_pdf_foaie_prezenta(proiect_id, luna, an):
    """Genereaza PDF Foaie Colectiva de Prezenta - A3 landscape."""
    if not REPORTLAB_AVAILABLE:
        raise ImportError('ReportLab nu este instalat. Folositi formatul Excel.')

    from models import db, Proiect, Angajat, AngajatProiect, Pontaj, SarbatoareLegala

    proiect = Proiect.query.get(proiect_id)
    if not proiect:
        raise ValueError('Proiectul nu a fost gasit.')

    nr_zile = calendar.monthrange(an, luna)[1]
    month_names = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
                   'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

    # Sarbatori si weekenduri
    sarbatori = set()
    for s in SarbatoareLegala.query.filter_by(an=an).all():
        if s.data.month == luna:
            sarbatori.add(s.data.day)
    weekends = set()
    for zi in range(1, nr_zile + 1):
        if date(an, luna, zi).weekday() >= 5:
            weekends.add(zi)

    asocieri = AngajatProiect.query.filter_by(proiect_id=proiect_id).all()
    angajati = [a.angajat for a in asocieri]

    from flask import current_app
    export_dir = current_app.config.get('EXPORT_FOLDER', 'exports')
    os.makedirs(export_dir, exist_ok=True)
    filename = f'foaie_prezenta_{proiect.cod_proiect}_{luna:02d}_{an}.pdf'
    filepath = os.path.join(export_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=landscape(A3),
                            leftMargin=10*mm, rightMargin=10*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = _get_styles()
    elements = []

    # Header
    elements.append(Paragraph('INNOVA WORKFORCE SRL', styles['TitleCustom']))
    elements.append(Paragraph('FOAIE COLECTIVA DE PREZENTA', styles['SubtitleCustom']))
    elements.append(Paragraph(
        f'Proiect: {proiect.cod_proiect} - {proiect.nume} | Locatie: {proiect.locatie or "-"} | '
        f'Luna: {month_names[luna]} {an}', styles['SubtitleCustom']
    ))
    elements.append(Spacer(1, 8*mm))

    # Build table data
    header_row = ['Nr.', 'Nume si Prenume', 'Functie']
    for zi in range(1, nr_zile + 1):
        d = date(an, luna, zi)
        day_name = ['Lu', 'Ma', 'Mi', 'Jo', 'Vi', 'Sa', 'Du'][d.weekday()]
        header_row.append(f'{zi}\n{day_name}')
    header_row.append('TOTAL')

    table_data = [header_row]

    for i, ang in enumerate(angajati):
        pontaje = Pontaj.query.filter(
            Pontaj.angajat_id == ang.id,
            Pontaj.proiect_id == proiect_id,
            db.extract('month', Pontaj.data) == luna,
            db.extract('year', Pontaj.data) == an
        ).all()
        pontaje_dict = {p.data.day: p for p in pontaje}

        data_row = [str(i + 1), ang.nume_complet, ang.functie]
        total = 0
        for zi in range(1, nr_zile + 1):
            if zi in pontaje_dict:
                p = pontaje_dict[zi]
                if p.tip_zi == 'co':
                    data_row.append('CO')
                elif p.tip_zi == 'cm':
                    data_row.append('CM')
                else:
                    ore = float(p.ore_lucrate or 0)
                    total += ore
                    data_row.append(str(int(ore)) if ore == int(ore) else str(ore))
            elif zi in sarbatori:
                data_row.append('SL')
            else:
                data_row.append('')
        data_row.append(str(total))
        table_data.append(data_row)

    # Coloane width
    col_widths = [8*mm, 35*mm, 20*mm] + [8*mm] * nr_zile + [12*mm]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = list(TABLE_STYLE_BASE.getCommands())

    # Weekend columns coloring
    for zi in range(1, nr_zile + 1):
        col_idx = zi + 2
        if zi in sarbatori:
            style_cmds.append(('BACKGROUND', (col_idx, 0), (col_idx, 0), colors.HexColor('#C62828')))
        elif zi in weekends:
            style_cmds.append(('BACKGROUND', (col_idx, 0), (col_idx, 0), colors.HexColor('#455A64')))
            for r_idx in range(1, len(table_data)):
                style_cmds.append(('BACKGROUND', (col_idx, r_idx), (col_idx, r_idx), colors.HexColor('#EEEEEE')))

    table.setStyle(TableStyle(style_cmds))
    elements.append(table)

    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(
        f'Data generare: {datetime.now().strftime("%d.%m.%Y %H:%M")} | '
        f'Semnatura Maistru: _________________ | '
        f'Semnatura Manager: _________________',
        styles['Footer']
    ))

    doc.build(elements)
    return filepath, filename


# ============================================================
# 2. PDF STAT DE PLATA
# ============================================================

def generate_pdf_stat_plata(proiect_id, luna, an):
    """Genereaza PDF Stat de Plata - A4 landscape."""
    if not REPORTLAB_AVAILABLE:
        raise ImportError('ReportLab nu este instalat.')

    from models import db, Proiect, Angajat, AngajatProiect, Pontaj

    month_names = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
                   'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

    from flask import current_app
    export_dir = current_app.config.get('EXPORT_FOLDER', 'exports')
    os.makedirs(export_dir, exist_ok=True)

    proiect_label = 'Toti'
    if proiect_id:
        proiect = Proiect.query.get(proiect_id)
        proiect_label = proiect.cod_proiect if proiect else 'Toti'

    filename = f'stat_plata_{proiect_label}_{luna:02d}_{an}.pdf'
    filepath = os.path.join(export_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=landscape(A4),
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = _get_styles()
    elements = []

    elements.append(Paragraph('INNOVA WORKFORCE SRL', styles['TitleCustom']))
    elements.append(Paragraph(f'STAT DE PLATA - {month_names[luna]} {an}', styles['SubtitleCustom']))
    elements.append(Spacer(1, 6*mm))

    # Query
    if proiect_id:
        asocieri = AngajatProiect.query.filter_by(proiect_id=proiect_id).all()
        angajati = [a.angajat for a in asocieri]
    else:
        angajati = Angajat.query.filter_by(status='activ').order_by(Angajat.nume).all()

    header_row = ['Nr.', 'Nume', 'Functie', 'Ore\nNorm.', 'Ore\n50%', 'Ore\n100%',
                  'Tarif/h', 'Sal. Baza', 'Spor 50%', 'Spor 100%', 'BRUT', 'Semn.']
    table_data = [header_row]

    totals = {'sal': 0, 's50': 0, 's100': 0, 'brut': 0}

    for i, ang in enumerate(angajati):
        query = Pontaj.query.filter(
            Pontaj.angajat_id == ang.id,
            db.extract('month', Pontaj.data) == luna,
            db.extract('year', Pontaj.data) == an,
            Pontaj.status == 'aprobat'
        )
        if proiect_id:
            query = query.filter(Pontaj.proiect_id == proiect_id)
        pontaje = query.all()

        ore_n = sum(float(p.ore_normale or 0) for p in pontaje)
        ore_50 = sum(float(p.ore_suplimentare_50 or 0) for p in pontaje)
        ore_100 = sum(float(p.ore_suplimentare_100 or 0) for p in pontaje)
        tarif = ang.tarif_orar
        sal = round(ore_n * tarif, 2)
        s50 = round(ore_50 * tarif * 1.5, 2)
        s100 = round(ore_100 * tarif * 2.0, 2)
        brut = sal + s50 + s100

        totals['sal'] += sal
        totals['s50'] += s50
        totals['s100'] += s100
        totals['brut'] += brut

        table_data.append([
            str(i + 1), ang.nume_complet, ang.functie,
            f'{ore_n:.0f}', f'{ore_50:.1f}', f'{ore_100:.1f}',
            f'{tarif:.2f}', f'{sal:,.2f}', f'{s50:,.2f}', f'{s100:,.2f}',
            f'{brut:,.2f}', ''
        ])

    # Total row
    table_data.append([
        '', 'TOTAL', '', '', '', '', '',
        f"{totals['sal']:,.2f}", f"{totals['s50']:,.2f}",
        f"{totals['s100']:,.2f}", f"{totals['brut']:,.2f}", ''
    ])

    col_widths = [8*mm, 35*mm, 20*mm, 12*mm, 12*mm, 12*mm, 14*mm,
                  20*mm, 18*mm, 18*mm, 22*mm, 18*mm]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = list(TABLE_STYLE_BASE.getCommands())
    last_row = len(table_data) - 1
    style_cmds.append(('BACKGROUND', (0, last_row), (-1, last_row), colors.HexColor('#E8EAF6')))
    style_cmds.append(('FONTNAME', (0, last_row), (-1, last_row), 'Helvetica-Bold'))
    table.setStyle(TableStyle(style_cmds))

    elements.append(table)
    elements.append(Spacer(1, 15*mm))

    # Semnaturi
    elements.append(Paragraph(
        'Intocmit: ___________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; '
        'Verificat: ___________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; '
        'Aprobat: ___________________',
        styles['Normal']
    ))
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(
        f'Data generare: {datetime.now().strftime("%d.%m.%Y %H:%M")}', styles['Footer']
    ))

    doc.build(elements)
    return filepath, filename


# ============================================================
# 3. PDF PONTAJ INDIVIDUAL
# ============================================================

def generate_pdf_pontaj_individual(angajat_id, data_start, data_sfarsit):
    """Genereaza PDF fisa pontaj individual."""
    if not REPORTLAB_AVAILABLE:
        raise ImportError('ReportLab nu este instalat.')

    from models import db, Angajat, Pontaj

    angajat = Angajat.query.get(angajat_id)
    if not angajat:
        raise ValueError('Angajatul nu a fost gasit.')

    from flask import current_app
    export_dir = current_app.config.get('EXPORT_FOLDER', 'exports')
    os.makedirs(export_dir, exist_ok=True)

    filename = f'pontaj_{angajat.nume}_{angajat.prenume}_{data_start.strftime("%Y%m%d")}.pdf'
    filepath = os.path.join(export_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = _get_styles()
    elements = []

    elements.append(Paragraph('INNOVA WORKFORCE SRL', styles['TitleCustom']))
    elements.append(Paragraph('FISA PONTAJ INDIVIDUAL', styles['SubtitleCustom']))
    elements.append(Spacer(1, 4*mm))

    elements.append(Paragraph(f'<b>Angajat:</b> {angajat.nume_complet}', styles['Normal']))
    elements.append(Paragraph(f'<b>Functie:</b> {angajat.functie}', styles['Normal']))
    elements.append(Paragraph(
        f'<b>Perioada:</b> {data_start.strftime("%d.%m.%Y")} - {data_sfarsit.strftime("%d.%m.%Y")}',
        styles['Normal']
    ))
    elements.append(Spacer(1, 6*mm))

    pontaje = Pontaj.query.filter(
        Pontaj.angajat_id == angajat_id,
        Pontaj.data >= data_start,
        Pontaj.data <= data_sfarsit
    ).order_by(Pontaj.data).all()

    header_row = ['Nr.', 'Data', 'Proiect', 'Start', 'Sfarsit', 'Ore', 'Supl.50%', 'Supl.100%', 'Tip']
    table_data = [header_row]

    totals = {'ore': 0, 'o50': 0, 'o100': 0}

    for i, p in enumerate(pontaje):
        ore = float(p.ore_lucrate or 0)
        o50 = float(p.ore_suplimentare_50 or 0)
        o100 = float(p.ore_suplimentare_100 or 0)
        totals['ore'] += ore
        totals['o50'] += o50
        totals['o100'] += o100

        table_data.append([
            str(i + 1),
            p.data.strftime('%d.%m.%Y') if p.data else '-',
            p.proiect.cod_proiect if p.proiect else '-',
            p.ora_start or '-',
            p.ora_sfarsit or '-',
            f'{ore:.1f}',
            f'{o50:.1f}',
            f'{o100:.1f}',
            p.tip_zi or '-',
        ])

    table_data.append([
        '', 'TOTAL', '', '', '',
        f'{totals["ore"]:.1f}', f'{totals["o50"]:.1f}', f'{totals["o100"]:.1f}', ''
    ])

    col_widths = [8*mm, 22*mm, 22*mm, 15*mm, 15*mm, 14*mm, 16*mm, 16*mm, 18*mm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = list(TABLE_STYLE_BASE.getCommands())
    last_row = len(table_data) - 1
    style_cmds.append(('BACKGROUND', (0, last_row), (-1, last_row), colors.HexColor('#E8EAF6')))
    style_cmds.append(('FONTNAME', (0, last_row), (-1, last_row), 'Helvetica-Bold'))
    table.setStyle(TableStyle(style_cmds))

    elements.append(table)
    elements.append(Spacer(1, 10*mm))

    # Stats summary
    elements.append(Paragraph('<b>Sumar:</b>', styles['Normal']))
    elements.append(Paragraph(
        f'Total zile lucrate: {len(pontaje)} | '
        f'Total ore: {totals["ore"]:.1f} | '
        f'Ore supl. 50%: {totals["o50"]:.1f} | '
        f'Ore supl. 100%: {totals["o100"]:.1f}',
        styles['Normal']
    ))
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(
        f'Data generare: {datetime.now().strftime("%d.%m.%Y %H:%M")} | '
        f'Semnatura angajat: _________________ | '
        f'Semnatura manager: _________________',
        styles['Footer']
    ))

    doc.build(elements)
    return filepath, filename

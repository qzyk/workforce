"""
Adauga slide timings + transitions in .pptx pentru export video automat.

Pentru fiecare slide:
- adauga <p:transition> cu tip "fade" si duration ~500ms
- adauga advance after X secunde (default 6s, dar mai mult pe primele 2)

Resultat: cand utilizatorul face File → Export → Create a Video in PowerPoint,
slide-urile avanseaza automat cu animatii smooth fade intre ele.
"""

import os
import shutil
import zipfile
import re
from xml.etree import ElementTree as ET


SRC = "/tmp/edifico-pitch/edifico_pitch.pptx"
DST = "/tmp/edifico-pitch/edifico_pitch_video.pptx"
WORK = "/tmp/edifico-pitch/unpacked"

# Timings per slide (in secunde). Slide-urile complexe primesc mai mult.
SLIDE_TIMINGS = {
    1:  4.0,   # Cover - se "instaleaza"
    2:  6.5,   # Problem - 3 stats de citit
    3:  6.5,   # Solution
    4:  8.0,   # Platform overview - 8 module
    5:  7.0,   # Workforce
    6:  7.0,   # BIM Core - hierarchy
    7:  7.0,   # 3D Viewer + Federation
    8:  7.0,   # CDE Workflow
    9:  7.0,   # Rule engine + Clash
    10: 7.0,   # 4D + 5D
    11: 7.0,   # Digital Twin / IoT
    12: 7.0,   # Real-time + Kanban
    13: 7.0,   # Governance
    14: 6.5,   # Standards
    15: 7.0,   # Tech stack
    16: 7.0,   # Security
    17: 6.5,   # Mobile PWA
    18: 7.0,   # Statistics
    19: 8.0,   # Why Edifico - comparison
    20: 5.0,   # CTA
}

# Transition: alternez intre "fade" si "push" pentru variation
TRANSITIONS = ['fade', 'push', 'wipe', 'morph']

NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def unzip_pptx(src, dest_dir):
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(src, 'r') as z:
        z.extractall(dest_dir)


def rezip_pptx(src_dir, dest_file):
    if os.path.exists(dest_file):
        os.remove(dest_file)
    with zipfile.ZipFile(dest_file, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(src_dir):
            for f in files:
                fpath = os.path.join(root, f)
                arcname = os.path.relpath(fpath, src_dir)
                z.write(fpath, arcname)


def add_transition_to_slide(slide_xml_path, slide_index, duration_seconds):
    """
    Modifica slide XML adaugand <p:transition> cu advance auto.
    Folosesc text manipulation simpla in loc de XML parser ca sa pastrez
    namespaces si formatting exact.
    """
    with open(slide_xml_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Eliminam orice transitions existente
    content = re.sub(r'<p:transition[^>]*?(?:/>|>.*?</p:transition>)', '', content, flags=re.DOTALL)

    transition_type = TRANSITIONS[(slide_index - 1) % len(TRANSITIONS)]
    advance_ms = int(duration_seconds * 1000)

    # Transition XML in functie de tip
    if transition_type == 'fade':
        trans_xml = (
            '<p:transition spd="med" advClick="1" advTm="{advance}">'
            '<p:fade/>'
            '</p:transition>'
        )
    elif transition_type == 'push':
        trans_xml = (
            '<p:transition spd="med" advClick="1" advTm="{advance}">'
            '<p:push dir="l"/>'
            '</p:transition>'
        )
    elif transition_type == 'wipe':
        trans_xml = (
            '<p:transition spd="med" advClick="1" advTm="{advance}">'
            '<p:wipe dir="l"/>'
            '</p:transition>'
        )
    else:  # morph (PowerPoint 2016+, fallback to fade)
        trans_xml = (
            '<p:transition spd="med" advClick="1" advTm="{advance}">'
            '<p:fade/>'
            '</p:transition>'
        )

    trans_xml = trans_xml.format(advance=advance_ms)

    # Insert transition inainte de </p:sld>
    # <p:transition> trebuie sa vina dupa <p:cSld> si inainte de <p:clrMapOvr> (daca exista)
    # Format mai sigur: il punem ca ultim element inainte de </p:sld>
    if '</p:sld>' in content:
        # Eliminam orice timing element pentru a evita conflicte
        content = re.sub(r'<p:timing[^>]*?(?:/>|>.*?</p:timing>)', '', content, flags=re.DOTALL)
        # Adaug transition
        content = content.replace('</p:sld>', trans_xml + '</p:sld>')

    with open(slide_xml_path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    print(f'Unpacking {SRC}...')
    unzip_pptx(SRC, WORK)

    slides_dir = os.path.join(WORK, 'ppt', 'slides')
    slide_files = sorted(
        [f for f in os.listdir(slides_dir) if f.startswith('slide') and f.endswith('.xml')],
        key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
    )

    for slide_idx, slide_file in enumerate(slide_files, start=1):
        duration = SLIDE_TIMINGS.get(slide_idx, 7.0)
        slide_path = os.path.join(slides_dir, slide_file)
        add_transition_to_slide(slide_path, slide_idx, duration)
        print(f'  [OK] {slide_file}: {duration}s · {TRANSITIONS[(slide_idx - 1) % len(TRANSITIONS)]}')

    print(f'Repacking to {DST}...')
    rezip_pptx(WORK, DST)

    out_size = os.path.getsize(DST) / 1024
    print(f'Done. Output: {DST} ({out_size:.0f} KB)')
    print()
    total_duration = sum(SLIDE_TIMINGS.values())
    print(f'Durata estimata video: ~{total_duration:.0f} secunde ({total_duration/60:.1f} minute)')


if __name__ == '__main__':
    main()

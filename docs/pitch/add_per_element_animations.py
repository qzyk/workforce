"""
Adauga animatii in-slide (entrance fade + fly-in) la text elements.

Modifica slideN.xml cu <p:timing> block care contine:
- mainSeq cu effect "fade" pentru toate text elementele
- delay 0.3s intre fiecare (build effect)
- duration 0.6s pentru fiecare fade

Resultat: cand redai prezentarea (sau export video), titlurile apar
unul cate unul cu fade smooth, nu tot deodata.
"""

import os
import re
import zipfile
import shutil


SRC = "/tmp/edifico-pitch/edifico_pitch_video.pptx"
DST = "/tmp/edifico-pitch/edifico_pitch_final.pptx"
WORK = "/tmp/edifico-pitch/unpacked_v2"


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


def extract_shape_ids(slide_xml):
    """Returneaza lista shape id-urilor (sp + pic) in ordinea aparitiei."""
    ids = []
    # Pattern pentru <p:sp> si <p:pic> cu nvSpPr/cNvPr id="N"
    for match in re.finditer(r'<p:(?:sp|pic|graphicFrame)>.*?<p:cNvPr id="(\d+)"', slide_xml, re.DOTALL):
        ids.append(int(match.group(1)))
    return ids


def build_timing_block(shape_ids):
    """
    Construieste <p:timing> XML cu fade-in pentru fiecare shape.
    Folosesc PowerPoint OpenXML schema standard pentru fade entrance.
    """
    if not shape_ids:
        return ''

    # Group de animatii cu fade pentru fiecare shape
    childTnLst_entries = []
    delay_ms = 0
    duration_ms = 500

    for idx, sid in enumerate(shape_ids):
        # Effect: par (parallel) with sequence inside
        entry = f'''
<p:par><p:cTn id="{10 + idx*5}" fill="hold">
  <p:stCondLst><p:cond delay="{delay_ms}"/></p:stCondLst>
  <p:childTnLst>
    <p:par><p:cTn id="{11 + idx*5}" fill="hold">
      <p:stCondLst><p:cond delay="0"/></p:stCondLst>
      <p:childTnLst>
        <p:par><p:cTn id="{12 + idx*5}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" nodeType="afterEffect">
          <p:stCondLst><p:cond delay="0"/></p:stCondLst>
          <p:childTnLst>
            <p:set>
              <p:cBhvr>
                <p:cTn id="{13 + idx*5}" dur="1" fill="hold">
                  <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                </p:cTn>
                <p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>
                <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
              </p:cBhvr>
              <p:to><p:strVal val="visible"/></p:to>
            </p:set>
            <p:anim calcmode="lin" valueType="num">
              <p:cBhvr additive="base">
                <p:cTn id="{14 + idx*5}" dur="{duration_ms}" fill="hold"/>
                <p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>
                <p:attrNameLst><p:attrName>style.opacity</p:attrName></p:attrNameLst>
              </p:cBhvr>
              <p:tavLst>
                <p:tav tm="0"><p:val><p:fltVal val="0"/></p:val></p:tav>
                <p:tav tm="100000"><p:val><p:fltVal val="1"/></p:val></p:tav>
              </p:tavLst>
            </p:anim>
          </p:childTnLst>
        </p:cTn></p:par>
      </p:childTnLst>
    </p:cTn></p:par>
  </p:childTnLst>
</p:cTn></p:par>'''.strip()
        childTnLst_entries.append(entry)
        delay_ms += 300  # 0.3s intre elemente

    seq = f'''<p:timing>
<p:tnLst>
<p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
  <p:childTnLst>
    <p:seq concurrent="1" nextAc="seek">
      <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
        <p:childTnLst>
          {chr(10).join(childTnLst_entries)}
        </p:childTnLst>
      </p:cTn>
      <p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>
      <p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>
    </p:seq>
  </p:childTnLst>
</p:cTn></p:par>
</p:tnLst>
</p:timing>'''
    return seq


def process_slide(slide_path):
    with open(slide_path, 'r', encoding='utf-8') as f:
        xml = f.read()

    # Sterg orice timing existent
    xml = re.sub(r'<p:timing>.*?</p:timing>', '', xml, flags=re.DOTALL)

    shape_ids = extract_shape_ids(xml)
    if not shape_ids:
        return False

    # Limit: nu animez mai mult de 12 shapes per slide (overload PowerPoint)
    shape_ids = shape_ids[:12]

    timing = build_timing_block(shape_ids)
    if not timing:
        return False

    # Insert <p:timing> inainte de </p:sld> (dar dupa <p:transition>)
    xml = xml.replace('</p:sld>', timing + '</p:sld>')

    with open(slide_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return True


def main():
    print(f'Unpacking {SRC}...')
    unzip_pptx(SRC, WORK)

    slides_dir = os.path.join(WORK, 'ppt', 'slides')
    slide_files = sorted(
        [f for f in os.listdir(slides_dir) if f.startswith('slide') and f.endswith('.xml')],
        key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
    )

    for slide_file in slide_files:
        slide_path = os.path.join(slides_dir, slide_file)
        ok = process_slide(slide_path)
        marker = '[OK]' if ok else '[SKIP]'
        print(f'  {marker} {slide_file}')

    print(f'Repacking to {DST}...')
    rezip_pptx(WORK, DST)
    out_size = os.path.getsize(DST) / 1024
    print(f'Done. Output: {DST} ({out_size:.0f} KB)')


if __name__ == '__main__':
    main()

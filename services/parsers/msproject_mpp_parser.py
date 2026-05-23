"""
Parser MS Project .mpp (format binar nativ Project) - Faza 11 extensie.

Spre deosebire de XML, formatul .mpp e binar proprietar Microsoft si NU poate
fi citit nativ in Python. Folosim biblioteca Java MPXJ (via jpype1) pentru a:

    1. citi .mpp cu org.mpxj.reader.UniversalProjectReader
    2. scrie un MSPDI XML temporar cu org.mpxj.mspdi.MSPDIWriter
       (acelasi format pe care il citeste deja MSProjectXMLParser)
    3. reutiliza parserul XML existent (tested) pe XML-ul temporar

Astfel toata logica de mapare task -> dict ramane intr-un singur loc
(MSProjectXMLParser), iar .mpp devine doar un "front-end" de conversie.

DEPENDINTE (vezi requirements.txt):
    - jpype1   (bridge Python <-> JVM)
    - mpxj     (jar-urile Java, ~32 fisiere in mpxj/lib/)
    - un JDK/JVM disponibil (Java 8+). Ordine de cautare:
        1. $JAVA_HOME (override explicit; pe PA seteaza-l in WSGI daca e cazul)
        2. JDK instalat cu pip `install-jdk` in ~/.jdk/jdk-*
        3. jpype.getDefaultJVMPath() (Java de sistem - PA il are)
      NB: NU folosi `jdk4py` - JDK-ul lui minimal nu include modulul
      `jdk.charsets`, iar MPXJ are nevoie de el (MacRoman etc).

IMPORTANT despre JVM:
    - jpype porneste UN SINGUR JVM per proces (singleton lazy, mai jos).
    - Sub Flask/PA cererile pot rula pe thread-uri worker; fiecare thread care
      apeleaza Java trebuie atasat la JVM (jpype.attachThreadToJVM()).
    - Importul jpype e LAZY (in interiorul functiilor) ca modulul sa fie
      importabil chiar daca jpype/JDK lipsesc - parse() va da ParseError curat.
"""

from __future__ import annotations

import glob
import os
import tempfile

from .base import Parser, ParseResult, ParseError
from .msproject_xml_parser import MSProjectXMLParser


# Numele claselor Java in MPXJ 16.x. ATENTIE: in versiunile vechi (<= 12)
# namespace-ul era `net.sf.mpxj`; in 16.x e `org.mpxj`.
_READER_CLASS = 'org.mpxj.reader.UniversalProjectReader'
_WRITER_CLASS = 'org.mpxj.mspdi.MSPDIWriter'


def _find_libjvm_in_home(home: str) -> str | None:
    """
    Cauta biblioteca libjvm intr-un JAVA_HOME dat.

    Acopera layout-urile:
      - macOS / Linux JDK modern: <home>/lib/server/libjvm.{dylib,so}
      - JDK 8 Linux:              <home>/jre/lib/*/server/libjvm.so
    Returneaza calea absoluta sau None.
    """
    if not home or not os.path.isdir(home):
        return None
    patterns = [
        os.path.join(home, 'lib', 'server', 'libjvm.*'),
        os.path.join(home, 'jre', 'lib', 'server', 'libjvm.*'),
        os.path.join(home, 'jre', 'lib', '*', 'server', 'libjvm.*'),
    ]
    for pat in patterns:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def _candidate_java_homes() -> list[str]:
    """Lista de candidati JAVA_HOME, in ordinea prioritatii."""
    cands: list[str] = []
    # 1. Override explicit (PA: poate fi setat in WSGI)
    jh = os.environ.get('JAVA_HOME')
    if jh:
        cands.append(jh)
    # 2. JDK instalat cu pip `install-jdk` (~/.jdk/jdk-*)
    for d in sorted(glob.glob(os.path.expanduser('~/.jdk/jdk-*')), reverse=True):
        cands.append(d)
        # layout macOS: <d>/Contents/Home
        cands.append(os.path.join(d, 'Contents', 'Home'))
    return cands


def _resolve_jvm_path() -> tuple[str | None, str | None]:
    """
    Rezolva (cale_libjvm, java_home).

    Intoarce (None, None) daca nu exista niciun JVM utilizabil.
    """
    for home in _candidate_java_homes():
        lib = _find_libjvm_in_home(home)
        if lib:
            return lib, home
    # 3. Fallback: lasa jpype sa gaseasca Java de sistem (PA il are)
    try:
        import jpype
        default = jpype.getDefaultJVMPath()
        if default and os.path.exists(default):
            return default, os.environ.get('JAVA_HOME')
    except Exception:
        pass
    return None, None


def _mpxj_jars() -> list[str]:
    """Calea catre jar-urile MPXJ (portabil, relativ la pachetul mpxj)."""
    try:
        import mpxj
    except ImportError:
        return []
    lib_dir = os.path.join(os.path.dirname(mpxj.__file__), 'lib')
    return glob.glob(os.path.join(lib_dir, '*.jar'))


def _ensure_jvm() -> None:
    """
    Porneste JVM o singura data (idempotent). Arunca ParseError daca mediul
    nu permite (jpype lipsa, niciun JDK, jar-uri MPXJ lipsa).
    """
    try:
        import jpype
    except ImportError as e:
        raise ParseError(
            'Suport .mpp indisponibil: biblioteca "jpype1" nu e instalata. '
            'Ruleaza: pip install jpype1 mpxj'
        ) from e

    if jpype.isJVMStarted():
        return

    jars = _mpxj_jars()
    if not jars:
        raise ParseError(
            'Suport .mpp indisponibil: jar-urile MPXJ lipsesc. '
            'Ruleaza: pip install mpxj'
        )

    libjvm, java_home = _resolve_jvm_path()
    if not libjvm:
        raise ParseError(
            'Suport .mpp indisponibil: niciun JDK/JVM gasit. '
            'Seteaza $JAVA_HOME, sau ruleaza: pip install install-jdk si '
            'python -c "import jdk; jdk.install(\'17\')". '
            '(NU folosi jdk4py - nu include charsets.)'
        )

    # Unele cai Java cauta module relativ la java.home; il setam explicit.
    if java_home:
        os.environ.setdefault('JAVA_HOME', java_home)
    jpype.startJVM(libjvm, classpath=jars)


def _attach_thread() -> None:
    """Ataseaza thread-ul curent la JVM daca e nevoie (Flask worker threads)."""
    import jpype
    if jpype.isJVMStarted() and not jpype.isThreadAttachedToJVM():
        jpype.attachThreadToJVM()


class MSProjectMPPParser(Parser):
    """
    Parser MS Project .mpp (binar) -> reutilizeaza MSProjectXMLParser.

    Strategie: .mpp --MPXJ--> MSPDI XML temporar --MSProjectXMLParser--> entities.
    Astfel maparea task->dict ramane intr-un singur loc, testat.
    """

    SURSA_COD = 'msproject_mpp'

    def parse(self, file_path: str) -> ParseResult:
        if not os.path.exists(file_path):
            raise ParseError(f'Fisierul nu exista: {file_path}')

        _ensure_jvm()
        _attach_thread()

        import jpype

        try:
            Reader = jpype.JClass(_READER_CLASS)
            Writer = jpype.JClass(_WRITER_CLASS)
        except Exception as e:
            raise ParseError(
                f'Clasele MPXJ nu au putut fi incarcate ({_READER_CLASS}). '
                f'Verifica versiunea mpxj (>=16). Detaliu: {e}'
            ) from e

        # 1. Citeste .mpp
        try:
            project = Reader().read(file_path)
        except Exception as e:
            raise ParseError(f'Nu pot citi fisierul .mpp: {e}') from e
        if project is None:
            raise ParseError(
                'Fisierul .mpp nu a putut fi interpretat (gol sau format '
                'necunoscut).'
            )

        # Numele real al planului (MPXJ). MSPDI writer pune filename-ul ca Name,
        # asa ca extragem aici numele autentic; daca lipseste, ramane gol si
        # call-site-ul cade pe nr. contract.
        real_name = ''
        try:
            props = project.getProjectProperties()
            nm = props.getName()
            if nm is not None and str(nm).strip():
                real_name = str(nm).strip()
        except Exception:
            pass

        # 2. Scrie MSPDI XML temporar
        fd, tmp_xml = tempfile.mkstemp(suffix='.xml', prefix='mpp_mspdi_')
        os.close(fd)
        try:
            try:
                Writer().write(project, tmp_xml)
            except Exception as e:
                raise ParseError(
                    f'Conversia .mpp -> MSPDI XML a esuat: {e}'
                ) from e

            # 3. Reutilizeaza parserul XML existent (tested)
            result = MSProjectXMLParser().parse(tmp_xml)
        finally:
            try:
                os.remove(tmp_xml)
            except OSError:
                pass

        # Marcam sursa reala (.mpp), nu 'msproject_xml'
        result.sursa = self.SURSA_COD
        result.stats['via'] = 'mpxj -> mspdi-xml -> MSProjectXMLParser'
        result.stats['format_sursa'] = 'mpp'
        # Suprascriem artefactul 'project.xml' din MSPDI cu numele real (sau gol)
        result.stats['project_name'] = real_name
        return result

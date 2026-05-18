"""
Layer de parsere pentru importuri externe (Faza 11).

Permite importul a 3 formate, cu posibilitate de extensie viitoare:
  - MS Project XML  (msproject_xml_parser)
  - eDevize XML     (edevize_xml_parser)
  - Excel BoQ XLSX  (excel_boq_parser)

Toate parserele implementeaza interfata `Parser` (vezi base.py) si intorc
`ParseResult` cu lista de entitati + warnings + errors + stats.

Folosire tipica:

    from services.parsers import MSProjectXMLParser, ParseResult

    parser = MSProjectXMLParser()
    result: ParseResult = parser.parse('/path/to/project.xml')
    if result.errors:
        # afiseaza errors si oprire
        ...
    for task_data in result.entities:
        task = TaskProgram(**task_data, program_id=..., proiect_id=...)
        db.session.add(task)
"""

from .base import Parser, ParseResult, ParseError
from .msproject_xml_parser import MSProjectXMLParser
from .edevize_xml_parser import EDevizeXMLParser
from .edevize_pdf_parser import EDevizePDFParser
from .excel_boq_parser import ExcelBoQParser


__all__ = [
    'Parser', 'ParseResult', 'ParseError',
    'MSProjectXMLParser', 'EDevizeXMLParser', 'EDevizePDFParser',
    'ExcelBoQParser',
]

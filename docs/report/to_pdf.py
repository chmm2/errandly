"""Convert a .docx in this folder to PDF using the installed Word.

    python docs/report/to_pdf.py [filename.docx ...]

Word rather than a converter library so pagination, table breaks and figure
placement match exactly what Word shows on screen — a PDF that disagrees with
the document it came from is worse than no PDF.

Defaults to every .docx in the folder when no filename is given.
"""

from __future__ import annotations

import pathlib
import sys

import win32com.client as win32

HERE = pathlib.Path(__file__).parent.resolve()

WD_FORMAT_PDF = 17
WD_EXPORT_DOC_CONTENT = 0
WD_OPTIMIZE_FOR_PRINT = 0
WD_STAT_PAGES = 2


def convert(paths: list[pathlib.Path]) -> None:
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        for src in paths:
            dst = src.with_suffix(".pdf")
            doc = word.Documents.Open(str(src), ReadOnly=True)
            try:
                doc.Repaginate()
                doc.ExportAsFixedFormat(
                    OutputFileName=str(dst),
                    ExportFormat=WD_FORMAT_PDF,
                    OpenAfterExport=False,
                    OptimizeFor=WD_OPTIMIZE_FOR_PRINT,
                    Item=WD_EXPORT_DOC_CONTENT,
                    IncludeDocProps=True,
                    CreateBookmarks=1,      # headings become PDF bookmarks
                )
                pages = doc.ComputeStatistics(WD_STAT_PAGES)
            finally:
                doc.Close(SaveChanges=False)
            size_kb = dst.stat().st_size / 1024
            print(f"  {dst.name}   {pages} pages, {size_kb:.0f} KB")
    finally:
        word.Quit()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        targets = [HERE / a for a in sys.argv[1:]]
    else:
        targets = sorted(p for p in HERE.glob("*.docx") if not p.name.startswith("~$"))
    missing = [p for p in targets if not p.exists()]
    if missing:
        sys.exit("missing: " + ", ".join(str(m) for m in missing))
    print(f"converting {len(targets)} file(s) with Word:")
    convert(targets)

#!/usr/bin/env python3
"""docx-js serializes <w:pBdr> children as top, bottom, left, right.

The OOXML schema (CT_PBdr) enforces top, left, bottom, right, between, bar.
Word tolerates the wrong order; strict validators and LibreOffice do not —
soffice refuses to open the file at all. Reorder in place, touching nothing else.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ORDER = ["top", "left", "bottom", "right", "between", "bar"]


def reorder(match):
    block = match.group(0)
    inner = match.group(1)
    parts = dict()
    for el in re.finditer(r"<w:(top|left|bottom|right|between|bar)\b[^>]*/>", inner):
        parts[el.group(1)] = el.group(0)
    if not parts:
        return block
    return "<w:pBdr>" + "".join(parts[k] for k in ORDER if k in parts) + "</w:pBdr>"


def main(path):
    path = Path(path)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            z.extractall(td)

        doc = td / "word" / "document.xml"
        xml = doc.read_text(encoding="utf-8")
        fixed, n = re.subn(r"<w:pBdr>(.*?)</w:pBdr>", reorder, xml, flags=re.S)
        doc.write_text(fixed, encoding="utf-8")
        print(f"reordered {n} pBdr blocks")

        # Rezip with [Content_Types].xml first and no directory entries. docx-js
        # emits neither, which Word tolerates but LibreOffice refuses to open.
        files = [n for n in names if (td / n).is_file()]
        ordered = [n for n in files if n == "[Content_Types].xml"] + [
            n for n in files if n != "[Content_Types].xml"
        ]
        out = td / "_out.docx"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name in ordered:
                z.write(td / name, name)
        shutil.move(str(out), str(path))


if __name__ == "__main__":
    main(sys.argv[1])

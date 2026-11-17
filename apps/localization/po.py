"""Minimal gettext .po reader / .mo writer, so catalogs can be compiled and measured on hosts
without GNU gettext (Windows dev machines, shared hosting)."""

import ast
import struct
from pathlib import Path

from django.conf import settings


def parse_po(text):
    """Yield (msgid, msgstr, fuzzy) for every entry, header included (msgid "")."""
    for block in text.replace("\r\n", "\n").split("\n\n"):
        msgid, msgstr, current, fuzzy = [], [], None, False
        for line in block.strip().splitlines():
            line = line.strip()
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            elif line.startswith("#"):
                continue
            elif line.startswith("msgid "):
                current, line = msgid, line[6:]
            elif line.startswith("msgstr "):
                current, line = msgstr, line[7:]
            elif not line.startswith('"'):
                current = None  # plural forms etc. are not used in this project
                continue
            if current is not None:
                current.append(ast.literal_eval(line))
        if current is not None or msgid:
            yield "".join(msgid), "".join(msgstr), fuzzy


def po_path(language):
    return Path(settings.LOCALE_PATHS[0]) / language / "LC_MESSAGES" / "django.po"


def completion(language):
    """(translated, total) message counts for a language's catalog."""
    if language == settings.LANGUAGE_CODE:
        return 1, 1
    path = po_path(language)
    if not path.exists():
        return 0, 0
    entries = [e for e in parse_po(path.read_text(encoding="utf-8")) if e[0]]
    return sum(1 for _id, text, fuzzy in entries if text and not fuzzy), len(entries)


def write_mo(po_file, mo_file):
    catalog = {
        msgid: msgstr
        for msgid, msgstr, fuzzy in parse_po(Path(po_file).read_text(encoding="utf-8"))
        if msgstr and (not fuzzy or not msgid)
    }
    keys = sorted(catalog)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(catalog[k].encode() + b"\0" for k in keys)
    count = len(keys)
    ids_start = 7 * 4 + count * 16
    strs_start = ids_start + len(ids)
    offsets, id_pos, str_pos = [], 0, 0
    for k in keys:
        key, value = k.encode(), catalog[k].encode()
        offsets.append((len(key), ids_start + id_pos, len(value), strs_start + str_pos))
        id_pos += len(key) + 1
        str_pos += len(value) + 1
    header = struct.pack("Iiiiiii", 0x950412DE, 0, count, 28, 28 + count * 8, 0, 0)
    table = b"".join(struct.pack("ii", n, o) for n, o, _n, _o in offsets)
    table += b"".join(struct.pack("ii", n, o) for _n, _o, n, o in offsets)
    Path(mo_file).write_bytes(header + table + ids + strs)

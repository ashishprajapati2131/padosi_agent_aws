"""Neutralise spreadsheet formulas in exported text (CSV / Google Sheets).

A cell such as ``=HYPERLINK(...)`` or ``@SUM(...)`` coming from an agent name,
email, address or review runs as a formula when an admin opens the export.
Prefixing it with an apostrophe makes the spreadsheet treat it as text.
Phone numbers and plain numbers that start with + or - stay unchanged.
"""
import re

_PLAIN_NUMBER_OR_PHONE = re.compile(r'^[+-][\d\s().,-]*$')


def safe_cell(value):
    if not isinstance(value, str) or not value:
        return value
    first = value[0]
    if first in ('=', '@', '\t', '\r'):
        return "'" + value
    if first in ('+', '-') and not _PLAIN_NUMBER_OR_PHONE.match(value):
        return "'" + value
    return value


def safe_row(row):
    return [safe_cell(v) for v in row]


class _SafeWriter:
    def __init__(self, writer):
        self._writer = writer

    def writerow(self, row):
        return self._writer.writerow(safe_row(row))

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def safe_csv_writer(fileobj, *args, **kwargs):
    """csv.writer whose rows are formula-neutralised."""
    import csv
    return _SafeWriter(csv.writer(fileobj, *args, **kwargs))

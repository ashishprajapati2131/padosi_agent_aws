"""Build CSV and XLSX files from the export allowlist only."""

from __future__ import annotations

import csv
import io
from typing import Iterable

from openpyxl import Workbook

from app.services.export_fields import enabled_export_fields

MISSING = "Data not available"


def _cell(value) -> str | int | float:
    if value is None or value == "":
        return MISSING
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def project_row(source: dict) -> dict:
    projected = {}
    for field in enabled_export_fields():
        projected[field.key] = source.get(field.key)
    return projected


def render_csv(rows: Iterable[dict]) -> bytes:
    fields = enabled_export_fields()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([field.key for field in fields])
    for source in rows:
        writer.writerow([_cell(source.get(field.key)) for field in fields])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def render_xlsx(rows: Iterable[dict]) -> bytes:
    fields = enabled_export_fields()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Places"
    sheet.append([field.key for field in fields])
    for source in rows:
        sheet.append([_cell(source.get(field.key)) for field in fields])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def place_export_dict(place, *, google_place_id: str | None = None) -> dict:
    return {
        "name": place.name,
        "address": place.address,
        "phone": place.phone,
        "website": place.website,
        "rating": place.rating,
        "review_count": place.review_count,
        "place_id": google_place_id if google_place_id is not None else place.google_place_id,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "business_status": place.business_status,
        "maps_uri": place.maps_uri,
    }

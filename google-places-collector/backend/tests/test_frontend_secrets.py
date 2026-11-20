from pathlib import Path


def test_frontend_source_has_no_server_key():
    root = Path(__file__).resolve().parents[2] / "frontend"
    assert root.exists()
    banned = ("GOOGLE_MAPS_API_KEY", "AIza")
    allowed_suffixes = {".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".json", ".md", ".svg"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"node_modules", "dist"} for part in path.parts):
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in banned:
            assert marker not in text, f"{marker} found in {path}"

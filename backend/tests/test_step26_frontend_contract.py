from pathlib import Path


def test_frontend_files_exist():
    root = Path(__file__).resolve().parents[2] / "frontend"
    assert (root / "index.html").exists()
    assert (root / "app.js").exists()
    assert (root / "styles.css").exists()


def test_frontend_uses_core_mvp_modules():
    root = Path(__file__).resolve().parents[2] / "frontend"
    js = (root / "app.js").read_text()
    for label in ["H&P", "Progress Note", "Discharge", "Med Rec", "Signout"]:
        assert label in js
    assert "/overview" in js
    assert "/audit" in js
    assert "/finalize" in js
    assert "/final-text" in js


def test_routes_include_dashboard_support():
    routes = (Path(__file__).resolve().parents[1] / "app" / "api" / "routes.py").read_text()
    assert '@router.get("/encounters"' in routes
    assert '@router.get("/organizations"' in routes
    assert '@router.get("/documents/{document_id}/final-text"' in routes

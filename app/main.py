"""
OfisArama v2 — FastAPI backend
Clone DB: offices_clone.db (read-only for offices data)
"""
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "offices_clone.db")

app = FastAPI(title="OfisArama v2", version="2.0.0")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

TR_MAP = str.maketrans({
    'ç': 'c', 'Ç': 'c', 'ğ': 'g', 'Ğ': 'g',
    'ı': 'i', 'I': 'i', 'İ': 'i', 'ö': 'o',
    'Ö': 'o', 'ş': 's', 'Ş': 's', 'ü': 'u', 'Ü': 'u',
})

def normalize(text: str) -> str:
    return text.lower().translate(TR_MAP)

def get_db():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)

def search_offices(search: str = "", location: str = "", page: int = 1, per_page: int = 24):
    conn = get_db()
    try:
        params = []
        conditions = []

        if location and location != "all":
            conditions.append("UPPER(location) LIKE ?")
            params.append(f"%{location.upper()}%")

        if search:
            norm = normalize(search)
            conditions.append("""(
                LOWER(name) LIKE ? OR
                LOWER(location) LIKE ? OR
                LOWER(description) LIKE ? OR
                LOWER(IFNULL(alias_names,'')) LIKE ? OR
                LOWER(IFNULL(tenants,'')) LIKE ?
            )""")
            like = f"%{norm}%"
            params.extend([like, like, like, like, like])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM offices {where}", params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT id, name, location, description, asking_rent, service_charge, "
            f"gross_leasable_area, floor_size, image_url, picture1_url, picture2_url, "
            f"tenants, year_built, delivery_type, alias_names "
            f"FROM offices {where} ORDER BY name ASC LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

        return total, [row_to_dict(r) for r in rows]
    finally:
        conn.close()

def get_locations():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT location FROM offices WHERE location IS NOT NULL ORDER BY location"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()

def get_office_by_id(office_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM offices WHERE id = ?", (office_id,)).fetchone()
        if not row:
            return None, []
        office = row_to_dict(row)

        extras = conn.execute("""
            SELECT ef.label, ef.key, ef.section, ef.field_type, oev.value
            FROM office_extra_values oev
            JOIN extra_fields ef ON ef.id = oev.field_id
            WHERE oev.office_id = ?
            ORDER BY ef.section, ef.sort_order
        """, (office_id,)).fetchall()

        extra_sections = {}
        for e in extras:
            sec = e["section"] or "Diğer"
            if sec not in extra_sections:
                extra_sections[sec] = []
            extra_sections[sec].append({"label": e["label"], "value": e["value"], "key": e["key"]})

        return office, extra_sections
    finally:
        conn.close()


# ── Page routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM offices").fetchone()[0]
    locations = get_locations()
    conn.close()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "total": total,
        "locations": locations,
    })

@app.get("/ofis/{office_id}", response_class=HTMLResponse)
async def office_detail(request: Request, office_id: int):
    office, extra_sections = get_office_by_id(office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "office": office,
        "extra_sections": extra_sections,
    })


# ── HTMX partial routes ──────────────────────────────────────────────────────

@app.get("/htmx/offices", response_class=HTMLResponse)
async def htmx_offices(
    request: Request,
    search: str = Query(""),
    location: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
):
    total, offices = search_offices(search, location, page, per_page)
    pages = max(1, -(-total // per_page))
    return templates.TemplateResponse("partials/office_grid.html", {
        "request": request,
        "offices": offices,
        "total": total,
        "page": page,
        "pages": pages,
        "search": search,
        "location": location,
    })


# ── API routes ───────────────────────────────────────────────────────────────

@app.get("/api/offices")
async def api_offices(
    search: str = Query(""),
    location: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, le=100),
):
    total, offices = search_offices(search, location, page, per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-total // per_page)),
        "offices": offices,
    }

@app.get("/api/offices/{office_id}")
async def api_office_detail(office_id: int):
    office, extra_sections = get_office_by_id(office_id)
    if not office:
        raise HTTPException(status_code=404, detail="Ofis bulunamadı")
    return {"office": office, "extras": extra_sections}

@app.get("/api/locations")
async def api_locations():
    return get_locations()

@app.get("/api/stats")
async def api_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM offices").fetchone()[0]
    locs = conn.execute("SELECT COUNT(DISTINCT location) FROM offices").fetchone()[0]
    conn.close()
    return {"total_offices": total, "total_locations": locs}

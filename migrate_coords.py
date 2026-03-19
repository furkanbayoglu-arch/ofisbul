"""
Migration: add lat/lng columns to offices and populate by district
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "offices_clone.db")

DISTRICT_COORDS = {
    "4.LEVENT":     (41.0835, 29.0099),
    "AKARETLER":    (41.0503, 29.0072),
    "AKATLAR":      (41.0783, 29.0167),
    "ALTUNIZADE":   (41.0219, 29.0525),
    "ATASEHIR":     (40.9922, 29.1244),
    "BARBAROS":     (41.0572, 29.0122),
    "BEYOGLU":      (41.0335, 28.9748),
    "BOMONTI":      (41.0591, 28.9868),
    "CENDERE":      (41.0891, 28.9547),
    "ESENTEPE":     (41.0694, 28.9989),
    "ETILER":       (41.0834, 29.0301),
    "FULYA":        (41.0655, 29.0039),
    "GAYRETTEPE":   (41.0705, 28.9956),
    "GOZTEPE":      (40.9764, 29.0681),
    "GUNESLI":      (41.0264, 28.8247),
    "HALIC":        (41.0375, 28.9441),
    "KADIKOY":      (40.9927, 29.0297),
    "KAGITHANE":    (41.0860, 28.9768),
    "KARAKOY":      (41.0233, 28.9749),
    "KARTAL":       (40.9077, 29.1895),
    "KAVACIK":      (41.1060, 29.0693),
    "KOZYATAGI":    (40.9719, 29.0994),
    "LEVENT":       (41.0835, 29.0099),
    "MASLAK":       (41.1101, 29.0197),
    "MECIDIYEKOY":  (41.0683, 28.9924),
    "OKMEYDANI":    (41.0602, 28.9564),
    "PENDIK":       (40.8783, 29.2360),
    "SARIYER":      (41.1667, 29.0497),
    "SISLI":        (41.0602, 28.9872),
    "TAKSIM":       (41.0369, 28.9850),
    "UMRANIYE":     (41.0167, 29.1167),
    "USKUDAR":      (41.0231, 29.0153),
    "YESILKOY":     (40.9742, 28.8186),
    "MACKA":        (41.0472, 29.0061),
    "KASIMPASA":    (41.0444, 28.9497),
    "MALTEPE":      (40.9340, 29.1303),
    "KUCUKYALI":    (40.9503, 29.1197),
    "LIBADIYE":     (41.0033, 29.1058),
    "KURTKOY":      (40.8944, 29.3119),
    "TARABYA":      (41.1333, 29.0667),
    "PIYALEPASA":   (41.0556, 28.9544),
}

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Add columns if not exist
for col in ("lat", "lng"):
    try:
        cur.execute(f"ALTER TABLE offices ADD COLUMN {col} REAL")
        print(f"Added column: {col}")
    except sqlite3.OperationalError:
        print(f"Column {col} already exists")

# Populate coordinates
updated = 0
rows = cur.execute("SELECT id, location FROM offices").fetchall()
for office_id, location in rows:
    if not location:
        continue
    district = location.split("/")[0].strip().upper()
    coords = DISTRICT_COORDS.get(district)
    if coords:
        cur.execute("UPDATE offices SET lat=?, lng=? WHERE id=?", (coords[0], coords[1], office_id))
        updated += 1
    else:
        print(f"  No coords for district: {district!r}")

conn.commit()
conn.close()
print(f"\nDone — {updated}/{len(rows)} offices updated with coordinates.")

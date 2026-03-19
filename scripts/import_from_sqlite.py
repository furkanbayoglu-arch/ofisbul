import os
import sqlite3
from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import ExtraField, Office, OfficeExtraValue


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT_DIR.parent / "ofisarama_offices_live.db"
SOURCE_SQLITE_PATH = Path(os.environ.get("SOURCE_SQLITE_PATH", str(DEFAULT_SOURCE)))


def import_data() -> None:
    if not SOURCE_SQLITE_PATH.exists():
        raise FileNotFoundError(f"SQLite source not found: {SOURCE_SQLITE_PATH}")

    Base.metadata.create_all(bind=engine)

    sqlite_conn = sqlite3.connect(str(SOURCE_SQLITE_PATH))
    sqlite_conn.row_factory = sqlite3.Row

    with SessionLocal() as session:
        session.execute(
            text("TRUNCATE TABLE office_extra_values, extra_fields, offices RESTART IDENTITY CASCADE")
        )
        session.commit()

        office_rows = sqlite_conn.execute("SELECT * FROM offices ORDER BY id").fetchall()
        field_rows = sqlite_conn.execute("SELECT * FROM extra_fields ORDER BY id").fetchall()
        value_rows = sqlite_conn.execute(
            "SELECT * FROM office_extra_values ORDER BY office_id, field_id"
        ).fetchall()

        session.bulk_save_objects(
            [
                Office(
                    id=row["id"],
                    name=row["name"],
                    location=row["location"],
                    description=row["description"],
                    ownership=row["ownership"],
                    year_built=row["year_built"],
                    certificate=row["certificate"],
                    gross_leasable_area=row["gross_leasable_area"],
                    floor_size=row["floor_size"],
                    efficiency=row["efficiency"],
                    delivery_type=row["delivery_type"],
                    asking_rent=row["asking_rent"],
                    service_charge=row["service_charge"],
                    car_park_ratio=row["car_park_ratio"],
                    tenants=row["tenants"],
                    image_url=row["image_url"],
                    picture1_url=row["picture1_url"],
                    picture2_url=row["picture2_url"],
                    alias_names=row["alias_names"],
                    lat=row["lat"] if "lat" in row.keys() else None,
                    lng=row["lng"] if "lng" in row.keys() else None,
                    created_at=row["created_at"],
                )
                for row in office_rows
            ]
        )
        session.bulk_save_objects(
            [
                ExtraField(
                    id=row["id"],
                    key=row["key"],
                    label=row["label"],
                    section=row["section"],
                    field_type=row["field_type"],
                    sort_order=row["sort_order"],
                    created_at=row["created_at"],
                )
                for row in field_rows
            ]
        )
        session.bulk_save_objects(
            [
                OfficeExtraValue(
                    office_id=row["office_id"],
                    field_id=row["field_id"],
                    value=row["value"],
                )
                for row in value_rows
            ]
        )
        session.commit()

        session.execute(
            text(
                """
                SELECT setval(
                    pg_get_serial_sequence('offices', 'id'),
                    COALESCE((SELECT MAX(id) FROM offices), 1),
                    true
                )
                """
            )
        )
        session.execute(
            text(
                """
                SELECT setval(
                    pg_get_serial_sequence('extra_fields', 'id'),
                    COALESCE((SELECT MAX(id) FROM extra_fields), 1),
                    true
                )
                """
            )
        )
        session.commit()

    sqlite_conn.close()
    print(f"Imported data from {SOURCE_SQLITE_PATH} into {settings.database_url}")


if __name__ == "__main__":
    import_data()

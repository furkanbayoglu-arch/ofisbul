# OfisArama v2

Bu proje, mevcut `ofisarama` canlı sistemine dokunmadan geliştirilecek yeni sürümün temelidir.

## Mimari

- Uygulama: `FastAPI`
- Veritabanı: `PostgreSQL`
- Veri aktarımı: canlı SQLite kopyasından tek yönlü import

Canlı sistem yeni veritabanına yazmaz. `v2` kendi PostgreSQL veritabanı üstünde çalışır.

## Kurulum

1. Ortam dosyasını oluştur:

```bash
cp .env.example .env
```

2. PostgreSQL başlat:

```bash
docker compose up -d
```

3. Bağımlılıkları kur:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. SQLite kopyasından PostgreSQL'e veri aktar:

```bash
export $(grep -v '^#' .env | xargs)
PYTHONPATH=. python3 scripts/import_from_sqlite.py
```

5. Uygulamayı çalıştır:

```bash
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
```

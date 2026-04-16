from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine
from app.routes import router
from app.compliance_routes import router as compliance_router
from app.upgrade_routes import router as upgrade_router
from app.seed import seed_dimensions

Base.metadata.create_all(bind=engine)

# Seed scoring dimensions on startup
db = SessionLocal()
try:
    seed_dimensions(db)
finally:
    db.close()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Prompt Registry", version="0.1.0")


@app.get("/")
def root():
    return FileResponse(path=str(STATIC_DIR / "base.html"), media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(router)
app.include_router(compliance_router)
app.include_router(upgrade_router)
# Mount static files last so it doesn't shadow API routes
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

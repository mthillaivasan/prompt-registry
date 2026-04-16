from fastapi import FastAPI

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

app = FastAPI(title="Prompt Registry", version="0.1.0")
app.include_router(router)
app.include_router(compliance_router)
app.include_router(upgrade_router)


@app.get("/health")
def health():
    return {"status": "ok"}

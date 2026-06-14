from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import listings as listings_router

app = FastAPI(
    title="FeWo Ostsee SH",
    description="API für Ferienwohnungsdaten an der Schleswig-Holsteinischen Ostseeküste",
    version="0.1.0",
)

# CORS — erlaubt React-Dev-Server (localhost:5173) Zugriff
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(listings_router.router)


@app.get("/")
def root():
    return {"status": "ok", "version": "0.1.0"}

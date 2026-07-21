"""液压支架总体设计 Agent — 后端入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_routes import router as agent_router
from app.api.routes import router
from app.db import SessionLocal, init_db
from app.knowledge.seed import seed_knowledge
from app.modules.impl import register_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_all()
    init_db()
    with SessionLocal() as db:
        seed_knowledge(db)
    yield


app = FastAPI(title="液压支架总体设计 Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(agent_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

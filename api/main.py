"""FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import chat, eval

app = FastAPI(
    title="QuickResolve AI",
    description="D2C Customer Support Agent for Taara Boutique",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(eval.router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "quickresolve-ai"}

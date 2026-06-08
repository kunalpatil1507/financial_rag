from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.database import init_db
from app.api.routes import auth, documents, roles, rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (nothing to clean up for now)


app = FastAPI(
    title="Financial Document Management API",
    description=(
        "AI-powered financial document management with semantic search. "
        "Supports PDF, DOCX, and TXT documents with RAG-based retrieval using "
        "Qdrant vector database and cross-encoder reranking."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(roles.router)
app.include_router(documents.router)
app.include_router(rag.router)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "Financial Document Management API"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}

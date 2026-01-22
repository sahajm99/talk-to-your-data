"""FastAPI application entrypoint."""

import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.ingestion.vector_store import WeaviateVectorStore
from app.ingestion.embedder import get_embedder, BaseEmbedder
from app.api import routes_health, routes_ingest, routes_chat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global instances (initialized at startup)
vector_store: WeaviateVectorStore | None = None
embedder: BaseEmbedder | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    global vector_store, embedder
    
    logger.info("Initializing Weaviate connection...")
    vector_store = WeaviateVectorStore(
        weaviate_url=settings.weaviate_url,
        weaviate_api_key=settings.weaviate_api_key,
        class_name=settings.weaviate_class_name,
    )
    
    logger.info("Ensuring Weaviate schema...")
    vector_store.ensure_schema()
    
    logger.info("Initializing embedder...")
    embedder = get_embedder()
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if vector_store:
        vector_store.close()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Talk To Your Data - Document Intelligence API",
    description="Upload documents with visual grounding and chat with your data using RAG",
    version="2.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(routes_health.router)
app.include_router(routes_ingest.router)
app.include_router(routes_chat.router)

# Mount static files for web application
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Mounted web app static files from {static_dir}")
else:
    logger.warning(f"Static directory {static_dir} does not exist. Web app disabled.")

# Mount static files for serving chunk images and documents
data_dir = Path(settings.data_dir)
if data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")
    logger.info(f"Mounted data files from {data_dir}")
else:
    logger.warning(f"Data directory {data_dir} does not exist. Creating it...")
    # Create the directory
    data_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")
    logger.info(f"Created and mounted data directory at {data_dir}")


@app.get("/")
async def root():
    """Serve the web application."""
    static_dir = Path(__file__).parent.parent / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        return FileResponse(index_file)
    else:
        # Fallback if static files don't exist
        return RedirectResponse(url="/docs")


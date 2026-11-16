from fastapi import APIRouter

from app.api.v1 import auth, deadlines, documents, minutes, quotes, search

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(deadlines.router)
api_router.include_router(quotes.router)
api_router.include_router(minutes.router)

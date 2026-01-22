"""Chat API endpoints for RAG-based question answering."""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException

from app.models import ChatQuery, ChatResponse, ConversationMessage
from app.services.chat_service import ChatService
from app.services.session_manager import get_session_manager, SessionManager
from app.ingestion.vector_store import WeaviateVectorStore
from app.ingestion.embedder import BaseEmbedder

logger = logging.getLogger(__name__)

router = APIRouter()


def get_vector_store() -> WeaviateVectorStore:
    """Dependency to get the global vector store instance."""
    from app.main import vector_store
    return vector_store


def get_embedder() -> BaseEmbedder:
    """Dependency to get the global embedder instance."""
    from app.main import embedder
    return embedder


def get_chat_service(
    vector_store: WeaviateVectorStore = Depends(get_vector_store),
    embedder: BaseEmbedder = Depends(get_embedder),
) -> ChatService:
    """
    Dependency to create ChatService instance.

    Args:
        vector_store: WeaviateVectorStore instance (injected)
        embedder: BaseEmbedder instance (injected)

    Returns:
        ChatService instance
    """
    session_manager = get_session_manager()
    return ChatService(
        vector_store=vector_store,
        embedder=embedder,
        session_manager=session_manager
    )


@router.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    query: ChatQuery,
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Answer a question using RAG (Retrieval-Augmented Generation).

    This endpoint:
    1. Retrieves relevant document chunks using vector search
    2. Generates an answer using GPT-4o-mini with retrieved context
    3. Maintains conversation history within a session
    4. Returns answer with source citations and visual grounding data

    Args:
        query: ChatQuery with user question and parameters
        chat_service: ChatService instance (injected)

    Returns:
        ChatResponse with answer, sources, and metadata
    """
    try:
        logger.info(
            f"Chat query: project={query.project_id}, "
            f"session={query.session_id}, "
            f"query_length={len(query.query)}"
        )

        response = await chat_service.query(query)

        logger.info(
            f"Chat response: session={response.session_id}, "
            f"sources={len(response.sources)}, "
            f"total_time={response.total_time_ms:.2f}ms"
        )

        return response

    except Exception as e:
        logger.error(f"Error processing chat query: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )


@router.get("/chat/history/{session_id}")
async def get_chat_history(
    session_id: str,
    max_messages: Optional[int] = None,
    chat_service: ChatService = Depends(get_chat_service),
) -> list[ConversationMessage]:
    """
    Get conversation history for a session.

    Args:
        session_id: Session identifier
        max_messages: Maximum number of recent messages to return (optional)
        chat_service: ChatService instance (injected)

    Returns:
        List of conversation messages in chronological order
    """
    try:
        history = chat_service.get_conversation_history(
            session_id=session_id,
            max_messages=max_messages
        )

        logger.info(f"Retrieved {len(history)} messages for session {session_id}")

        return history

    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving history: {str(e)}"
        )


@router.delete("/chat/history/{session_id}")
async def clear_chat_history(
    session_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict:
    """
    Clear conversation history for a session.

    Args:
        session_id: Session identifier
        chat_service: ChatService instance (injected)

    Returns:
        Success message
    """
    try:
        success = chat_service.clear_conversation(session_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        logger.info(f"Cleared conversation history for session {session_id}")

        return {
            "message": "Conversation history cleared successfully",
            "session_id": session_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing history: {str(e)}"
        )


@router.get("/chat/sessions/stats")
async def get_session_stats() -> dict:
    """
    Get statistics about active sessions.

    Returns:
        Dictionary with session statistics
    """
    try:
        session_manager = get_session_manager()

        # Cleanup expired sessions first
        cleaned_count = session_manager.cleanup_expired_sessions()

        active_count = session_manager.get_active_session_count()

        return {
            "active_sessions": active_count,
            "expired_sessions_cleaned": cleaned_count
        }

    except Exception as e:
        logger.error(f"Error getting session stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting stats: {str(e)}"
        )

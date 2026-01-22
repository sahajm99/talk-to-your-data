"""Chat service with RAG (Retrieval-Augmented Generation) logic."""

import logging
import time
from typing import Optional
from openai import OpenAI

from app.models import ChatQuery, ChatResponse, SourceReference, ConversationMessage
from app.ingestion.embedder import BaseEmbedder
from app.ingestion.vector_store import WeaviateVectorStore
from app.services.session_manager import SessionManager
from app.config import settings

logger = logging.getLogger(__name__)


class ChatService:
    """
    Chat service implementing RAG pattern.

    Pipeline:
    1. Generate query embedding
    2. Search Weaviate for relevant chunks
    3. Build context from retrieved chunks
    4. Generate answer using LLM with conversation history
    5. Store conversation in session
    """

    def __init__(
        self,
        vector_store: WeaviateVectorStore,
        embedder: BaseEmbedder,
        session_manager: SessionManager,
    ):
        """
        Initialize chat service.

        Args:
            vector_store: WeaviateVectorStore instance
            embedder: BaseEmbedder instance for query embedding
            session_manager: SessionManager for conversation persistence
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.session_manager = session_manager
        self.openai_client = OpenAI(api_key=settings.openai_api_key)

        logger.info("ChatService initialized")

    async def query(self, chat_query: ChatQuery) -> ChatResponse:
        """
        Process a chat query using RAG.

        Args:
            chat_query: ChatQuery instance with user question

        Returns:
            ChatResponse with answer and sources
        """
        start_time = time.time()

        # Step 1: Get or create session
        session_id = self.session_manager.get_or_create_session(
            session_id=chat_query.session_id,
            project_id=chat_query.project_id
        )

        logger.info(
            f"Processing query for session {session_id}, project {chat_query.project_id}"
        )

        # Step 2: Retrieve relevant chunks
        retrieval_start = time.time()
        sources = await self._retrieve_relevant_chunks(
            query=chat_query.query,
            project_id=chat_query.project_id,
            top_k=chat_query.top_k,
            include_images=chat_query.include_images
        )
        retrieval_time = (time.time() - retrieval_start) * 1000  # Convert to ms

        logger.info(f"Retrieved {len(sources)} relevant chunks in {retrieval_time:.2f}ms")

        # Step 3: Get conversation history
        conversation_history = self.session_manager.get_conversation_history(
            session_id=session_id,
            max_messages=10  # Last 5 exchanges (10 messages)
        )

        # Step 4: Generate answer using LLM
        generation_start = time.time()
        answer = await self._generate_answer(
            query=chat_query.query,
            sources=sources,
            conversation_history=conversation_history
        )
        generation_time = (time.time() - generation_start) * 1000  # Convert to ms

        logger.info(f"Generated answer in {generation_time:.2f}ms")

        # Step 5: Store conversation in session
        self.session_manager.add_message(
            session_id=session_id,
            message=ConversationMessage(
                role="user",
                content=chat_query.query
            )
        )

        self.session_manager.add_message(
            session_id=session_id,
            message=ConversationMessage(
                role="assistant",
                content=answer,
                sources=sources
            )
        )

        # Step 6: Build response
        total_time = (time.time() - start_time) * 1000

        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
            query=chat_query.query,
            project_id=chat_query.project_id,
            retrieval_time_ms=retrieval_time,
            generation_time_ms=generation_time,
            total_time_ms=total_time
        )

    async def _retrieve_relevant_chunks(
        self,
        query: str,
        project_id: str,
        top_k: int,
        include_images: bool
    ) -> list[SourceReference]:
        """
        Retrieve relevant chunks from vector store.

        Args:
            query: User's question
            project_id: Project identifier
            top_k: Number of chunks to retrieve
            include_images: Whether to include image paths

        Returns:
            List of SourceReference objects
        """
        # Generate query embedding
        query_vector = self.embedder.embed_texts([query])[0]

        # Search Weaviate
        results = self.vector_store.search_with_visual_grounding(
            query_vector=query_vector,
            project_id=project_id,
            limit=top_k
        )

        # Convert to SourceReference objects
        sources = []
        for result in results:
            source = SourceReference(
                chunk_id=result.get("id", ""),
                source_id=result.get("sourceId", ""),
                file_name=result.get("fileName", "unknown"),
                page_number=result.get("pageNumber"),
                chunk_index=result.get("chunkIndex", 0),
                text=result.get("text", ""),
                score=result.get("score", 0.0),
                bounding_box=result.get("boundingBox"),
                image_path=result.get("imagePath") if include_images else None,
                chunk_type=result.get("chunkType", "text")
            )
            sources.append(source)

        return sources

    async def _generate_answer(
        self,
        query: str,
        sources: list[SourceReference],
        conversation_history: list[ConversationMessage]
    ) -> str:
        """
        Generate answer using LLM with retrieved context.

        Args:
            query: User's question
            sources: Retrieved source chunks
            conversation_history: Previous conversation messages

        Returns:
            Generated answer text
        """
        # Build context from sources
        context_parts = []
        for idx, source in enumerate(sources, 1):
            context_parts.append(
                f"[Source {idx}] {source.file_name} (Page {source.page_number or 'N/A'}):\n{source.text}\n"
            )

        context = "\n".join(context_parts)

        # Build conversation history for prompt
        history_text = ""
        if conversation_history:
            history_parts = []
            for msg in conversation_history[-6:]:  # Last 3 exchanges
                history_parts.append(f"{msg.role.upper()}: {msg.content}")
            history_text = "\n\n".join(history_parts)

        # Build system prompt
        system_prompt = """You are a helpful AI assistant that answers questions based on provided document context.

Guidelines:
1. Answer questions accurately using ONLY the information from the provided sources
2. If the answer is not in the sources, say "I don't have enough information to answer this question"
3. Cite sources by number when referencing specific information (e.g., "According to Source 1...")
4. Be concise but comprehensive
5. If sources conflict, acknowledge the discrepancy
6. Maintain conversation context and refer to previous messages when relevant

Format your answer clearly with proper paragraphs and citations."""

        # Build messages for OpenAI API
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add conversation history if exists
        if history_text:
            messages.append({
                "role": "system",
                "content": f"Previous conversation:\n{history_text}"
            })

        # Add current context and query
        user_message = f"""Context from documents:
{context}

Question: {query}

Please answer the question based on the context provided above. Cite sources by number."""

        messages.append({"role": "user", "content": user_message})

        # Call OpenAI API
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Fast and cost-effective
                messages=messages,
                temperature=0.2,  # Low temperature for factual answers
                max_tokens=1000,
                top_p=0.9
            )

            answer = response.choices[0].message.content.strip()
            logger.debug(f"Generated answer: {answer[:100]}...")

            return answer

        except Exception as e:
            logger.error(f"Error generating answer with OpenAI: {e}", exc_info=True)
            return f"Sorry, I encountered an error while generating the answer: {str(e)}"

    def get_conversation_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None
    ) -> list[ConversationMessage]:
        """
        Get conversation history for a session.

        Args:
            session_id: Session identifier
            max_messages: Maximum number of recent messages

        Returns:
            List of conversation messages
        """
        return self.session_manager.get_conversation_history(
            session_id=session_id,
            max_messages=max_messages
        )

    def clear_conversation(self, session_id: str) -> bool:
        """
        Clear conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully
        """
        return self.session_manager.clear_session(session_id)

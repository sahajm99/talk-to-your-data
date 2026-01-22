"""Embedding provider abstraction and implementations."""

import logging
import time
from typing import Protocol
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class BaseEmbedder(Protocol):
    """Protocol for embedding providers."""
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        ...


class OpenAIEmbedder:
    """OpenAI embedding provider implementation."""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-large"):
        """
        Initialize OpenAI embedder.
        
        Args:
            api_key: OpenAI API key
            model: Model name (default: text-embedding-3-large)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.batch_size = 64  # OpenAI's recommended batch size
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for texts using OpenAI API.
        
        Handles batching and rate limiting with retries.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            # Retry logic for rate limiting
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch,
                    )
                    
                    batch_embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(batch_embeddings)
                    break
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Embedding batch {i//self.batch_size + 1} failed, "
                            f"retrying in {retry_delay}s: {e}"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error(f"Failed to embed batch after {max_retries} attempts: {e}")
                        raise
        
        return all_embeddings


def get_embedder() -> BaseEmbedder:
    """
    Factory function to get the configured embedder.
    
    Returns:
        BaseEmbedder instance (currently OpenAIEmbedder)
    """
    return OpenAIEmbedder(api_key=settings.openai_api_key)


"""Weaviate vector store integration."""

import json
import logging
from typing import Optional
import weaviate
from weaviate.classes.config import Property, DataType
from weaviate.classes.query import Filter

from app.models import DocumentChunk

logger = logging.getLogger(__name__)


class WeaviateVectorStore:
    """Weaviate client wrapper for storing document chunks."""
    
    def __init__(
        self,
        weaviate_url: str,
        weaviate_api_key: Optional[str] = None,
        class_name: str = "IngestedChunk",
    ):
        """
        Initialize Weaviate client using HTTP only (gRPC checks are skipped).
        
        Args:
            weaviate_url: HTTP URL of the Weaviate instance (e.g., https://...)
            weaviate_api_key: Optional API key for authentication
            class_name: Name of the Weaviate class/collection to use
        """
        self.class_name = class_name
        
        # Parse HTTP URL
        from urllib.parse import urlparse
        http_parsed = urlparse(weaviate_url)
        
        # Extract HTTP connection parameters
        http_host = http_parsed.hostname or "localhost"
        http_port = http_parsed.port or (443 if http_parsed.scheme == "https" else 8080)
        http_secure = http_parsed.scheme == "https"
        
        # Set up authentication if provided
        auth_config = None
        if weaviate_api_key:
            auth_config = weaviate.auth.AuthApiKey(api_key=weaviate_api_key)
        
        # Import additional config for skipping gRPC checks
        import weaviate.classes.init as wvc_init
        from weaviate.exceptions import WeaviateGRPCUnavailableError
        
        # Check if this is a Weaviate Cloud instance (has .weaviate.cloud in URL)
        is_cloud = ".weaviate.cloud" in weaviate_url.lower()
        
        # For Weaviate Cloud, try using connect_to_weaviate_cloud() which handles gRPC better
        if is_cloud and auth_config:
            try:
                # Use connect_to_weaviate_cloud for cloud instances with skip_init_checks
                logger.info("Connecting to Weaviate Cloud...")
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=weaviate_url,
                    auth_credentials=auth_config,
                    skip_init_checks=True,  # Pass directly as parameter
                )
                logger.info("Successfully connected to Weaviate Cloud (HTTP-only mode)")
                return
            except Exception as e:
                logger.warning(f"connect_to_weaviate_cloud failed: {e}, falling back to connect_to_custom")
        
        # Fallback to connect_to_custom for local or if cloud method fails
        # For Weaviate Cloud, gRPC uses port 443 (secure), for local use 50051
        grpc_port = 443 if (is_cloud and http_secure) else 50051
        
        # Weaviate v4+ API requires gRPC parameters, but we skip gRPC checks
        # Use skip_init_checks=True to bypass gRPC health check
        additional_config = wvc_init.AdditionalConfig(
            skip_init_checks=True  # Skip gRPC health check - use HTTP only
        )
        
        # Create connection - catch gRPC errors since we only need HTTP
        try:
            if auth_config:
                self.client = weaviate.connect_to_custom(
                    http_host=http_host,
                    http_port=http_port,
                    http_secure=http_secure,
                    grpc_host=http_host,
                    grpc_port=grpc_port,
                    grpc_secure=http_secure,
                    auth_credentials=auth_config,
                    additional_config=additional_config,
                )
            else:
                self.client = weaviate.connect_to_custom(
                    http_host=http_host,
                    http_port=http_port,
                    http_secure=http_secure,
                    grpc_host=http_host,
                    grpc_port=grpc_port,
                    grpc_secure=http_secure,
                    additional_config=additional_config,
                )
        except WeaviateGRPCUnavailableError as e:
            # gRPC check failed - this is expected when using HTTP-only
            # Log warning but the error will propagate - HTTP should still work
            logger.warning(
                f"gRPC health check failed (this is expected for HTTP-only mode): {e}"
            )
            logger.info("Note: HTTP connection is working, but gRPC check failed")
            # Re-raise - the application startup will fail, but this indicates a config issue
            raise
    
    def ensure_schema(self) -> None:
        """
        Ensure the class exists in Weaviate.

        Creates the class with all required properties if it doesn't exist.
        Enhanced schema includes visual grounding fields.
        """
        if not self.client.collections.exists(self.class_name):
            logger.info(f"Creating Weaviate class: {self.class_name}")

            self.client.collections.create(
                name=self.class_name,
                properties=[
                    # Original fields
                    Property(name="projectId", data_type=DataType.TEXT),
                    Property(name="sourceId", data_type=DataType.TEXT),
                    Property(name="sourceType", data_type=DataType.TEXT),
                    Property(name="fileName", data_type=DataType.TEXT),
                    Property(name="filePath", data_type=DataType.TEXT),
                    Property(name="chunkIndex", data_type=DataType.INT),
                    Property(name="text", data_type=DataType.TEXT),
                    Property(name="metadataJson", data_type=DataType.TEXT),
                    # Visual grounding fields (Phase 1)
                    Property(name="chunkType", data_type=DataType.TEXT),  # text, table, image
                    Property(name="pageNumber", data_type=DataType.INT),
                    Property(name="boundingBox", data_type=DataType.NUMBER_ARRAY),  # [x1, y1, x2, y2]
                    Property(name="imagePath", data_type=DataType.TEXT),  # Path to cropped chunk image
                    Property(name="confidence", data_type=DataType.NUMBER),  # Extraction confidence
                ],
            )
            logger.info(f"Created Weaviate class with visual grounding: {self.class_name}")
        else:
            logger.info(f"Weaviate class {self.class_name} already exists")
    
    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        """
        Upsert document chunks with their embeddings into Weaviate.
        
        Args:
            chunks: List of DocumentChunk instances
            embeddings: List of embedding vectors (one per chunk)
        
        Raises:
            ValueError: If chunks and embeddings lengths don't match
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) "
                "must have the same length"
            )
        
        import uuid
        collection = self.client.collections.get(self.class_name)
        
        # Insert chunks with embeddings using v4 batch API
        # Use batch context manager for efficient insertion
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size]
            
            # Use batch context manager for efficient batch insertion
            with collection.batch.dynamic() as batch:
                for chunk, embedding in zip(batch_chunks, batch_embeddings):
                    # Deterministic UUID per chunk for idempotent upserts
                    chunk_id_str = f"{chunk.project_id}_{chunk.source_id}_{chunk.chunk_index}"
                    chunk_uuid = uuid.uuid5(uuid.NAMESPACE_URL, chunk_id_str)
                    
                    properties = {
                        "projectId": chunk.project_id,
                        "sourceId": chunk.source_id,
                        "sourceType": chunk.source_type,
                        "fileName": chunk.file_name,
                        "filePath": chunk.file_path or "",
                        "chunkIndex": chunk.chunk_index,
                        "text": chunk.text,
                        "metadataJson": json.dumps(chunk.metadata),
                    }
                    
                    # v4 batch API: use add_object (batch.add is not available)
                    batch.add_object(
                        properties=properties,
                        vector=embedding,
                        uuid=str(chunk_uuid),
                    )
            
            logger.info(f"Inserted batch of {len(batch_chunks)} chunks")
        
        logger.info(f"Successfully upserted {len(chunks)} chunks to Weaviate")
    
    def upsert_chunks_enhanced(
        self,
        chunks: list,  # List of EnhancedDocumentChunk or similar
        embeddings: list[list[float]],
        image_paths: list[str] = None,
    ) -> None:
        """
        Upsert enhanced document chunks with visual grounding into Weaviate.

        Args:
            chunks: List of EnhancedDocumentChunk instances
            embeddings: List of embedding vectors (one per chunk)
            image_paths: Optional list of image paths (one per chunk)

        Raises:
            ValueError: If chunks and embeddings lengths don't match
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) "
                "must have the same length"
            )

        # Default image paths if not provided
        if image_paths is None:
            image_paths = [""] * len(chunks)

        import uuid
        collection = self.client.collections.get(self.class_name)

        # Insert chunks with embeddings using v4 batch API
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size]
            batch_image_paths = image_paths[i:i + batch_size]

            # Use batch context manager for efficient batch insertion
            with collection.batch.dynamic() as batch:
                for chunk, embedding, img_path in zip(batch_chunks, batch_embeddings, batch_image_paths):
                    # Get chunk attributes (works with both dict and object)
                    if hasattr(chunk, '__dict__'):
                        chunk_data = chunk.__dict__
                    elif hasattr(chunk, 'to_dict'):
                        chunk_data = chunk.to_dict()
                    else:
                        chunk_data = chunk

                    # Extract fields
                    project_id = chunk_data.get('project_id', '')
                    document_id = chunk_data.get('document_id', '')
                    chunk_index = chunk_data.get('chunk_index', 0)
                    chunk_type = chunk_data.get('chunk_type', 'text')
                    page_number = chunk_data.get('page_number', 1)
                    bounding_box = chunk_data.get('bounding_box', [0.0, 0.0, 0.0, 0.0])
                    confidence = chunk_data.get('confidence', 1.0)

                    # Deterministic UUID per chunk for idempotent upserts
                    chunk_id_str = f"{project_id}_{document_id}_{chunk_index}"
                    chunk_uuid = uuid.uuid5(uuid.NAMESPACE_URL, chunk_id_str)

                    properties = {
                        # Original fields
                        "projectId": project_id,
                        "sourceId": document_id,
                        "sourceType": chunk_data.get('file_name', '').split('.')[-1] if chunk_data.get('file_name') else '',
                        "fileName": chunk_data.get('file_name', ''),
                        "filePath": chunk_data.get('file_path', ''),
                        "chunkIndex": chunk_index,
                        "text": chunk_data.get('text', ''),
                        "metadataJson": json.dumps(chunk_data.get('metadata', {})),
                        # Visual grounding fields
                        "chunkType": chunk_type,
                        "pageNumber": page_number,
                        "boundingBox": bounding_box,
                        "imagePath": img_path,
                        "confidence": confidence,
                    }

                    # v4 batch API: use add_object
                    batch.add_object(
                        properties=properties,
                        vector=embedding,
                        uuid=str(chunk_uuid),
                    )

            logger.info(f"Inserted batch of {len(batch_chunks)} enhanced chunks")

        logger.info(f"Successfully upserted {len(chunks)} enhanced chunks to Weaviate")

    def search_with_visual_grounding(
        self,
        query_vector: list[float],
        project_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Search for chunks with visual grounding metadata.

        Args:
            query_vector: Query embedding vector
            project_id: Project identifier to filter by
            limit: Maximum number of results

        Returns:
            List of chunk dictionaries with visual grounding data
        """
        collection = self.client.collections.get(self.class_name)

        # Perform vector search with filters (Weaviate v4 syntax)
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            return_properties=[
                "text",
                "fileName",
                "chunkType",
                "pageNumber",
                "boundingBox",
                "imagePath",
                "confidence",
                "sourceId",
                "projectId",
                "chunkIndex"
            ],
            return_metadata=["distance", "certainty"],  # Request distance/certainty in metadata
            filters=Filter.by_property("projectId").equal(project_id)
        )

        # Convert results to list of dicts
        results = []
        for obj in response.objects:
            # Calculate relevance score from distance (lower distance = higher relevance)
            # In Weaviate v4, distance is in metadata and represents cosine distance (0-2 range)
            # Lower distance = more similar (0 = identical)
            distance = None
            if hasattr(obj, 'metadata') and obj.metadata:
                # Try different possible attributes
                if hasattr(obj.metadata, 'distance'):
                    distance = obj.metadata.distance
                elif hasattr(obj.metadata, 'certainty'):
                    # Certainty is 0-1, higher is better (convert to distance-like score)
                    distance = 1.0 - obj.metadata.certainty

            # Convert distance to similarity score (0-1 scale, higher = more relevant)
            # For cosine distance: 0 = identical, 2 = opposite
            if distance is not None:
                # Normalize cosine distance (0-2) to similarity score (0-1)
                # Distance 0 → score 1.0, Distance 2 → score 0.0
                score = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
            else:
                # Fallback if no distance available
                score = 0.5
                logger.warning(f"No distance/certainty found for result, using default score")

            result = {
                "id": str(obj.uuid),  # Object UUID
                "text": obj.properties.get("text", ""),
                "fileName": obj.properties.get("fileName", ""),
                "chunkType": obj.properties.get("chunkType", "text"),
                "pageNumber": obj.properties.get("pageNumber", 1),
                "boundingBox": obj.properties.get("boundingBox"),
                "imagePath": obj.properties.get("imagePath", ""),
                "confidence": obj.properties.get("confidence", 1.0),
                "sourceId": obj.properties.get("sourceId", ""),
                "projectId": obj.properties.get("projectId", ""),
                "chunkIndex": obj.properties.get("chunkIndex", 0),
                "score": score
            }
            results.append(result)

        logger.info(f"Retrieved {len(results)} chunks for query")
        return results

    def close(self) -> None:
        """Close the Weaviate client connection."""
        if self.client:
            self.client.close()


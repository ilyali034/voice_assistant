import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from .qdrant.qdrant_cfg import QdrantCfg
from .qdrant.qdrant_engine import QEngine
from qdrant_client import models

class VQDBManager:
    """
    High-level Vector Qdrant Database Manager for the Assistant.
    Handles semantic long-term memory for chat dialogues and document indexing.
    """
    def __init__(self, cfg: QdrantCfg):
        self.engine = QEngine(cfg)

        self.chat_collection = "assistant_chat_history"
        self.doc_collection = "assistant_documents"

    async def init_database(self):
        """
        Initializes the necessary Qdrant collections if they do not exist.
        """
        vector_size = 384 if "all-MiniLM-L6-v2" in self.engine.model_name else 1536
        
        for collection in [self.chat_collection, self.doc_collection]:
            try:
                await self.engine.client.create_collection(
                    collection_name=collection,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                print(f"Collection '{collection}' successfully created.")
            except Exception as e:
                print(f"Collection '{collection}' is already initialized or ready.")


    async def save_chat_message(
        self, 
        user_id: int | str, 
        role: str, 
        text: str, 
        embedding: List[float]
    ) -> str:
        """
        Saves a single dialogue utterance (user or assistant) into the vector memory.
        
        :param user_id: Unique identifier of the chat user
        :param role: The sender role (e.g., 'user' or 'assistant')
        :param text: The raw text message content
        :param embedding: Vector representation of the message text
        :return: Generated message ID string
        """
        msg_id = str(uuid.uuid4())
        await self.engine.client.upsert(
            collection_name=self.chat_collection,
            points=[
                models.PointStruct(
                    id=msg_id,
                    vector=embedding,
                    payload={
                        "user_id": str(user_id),
                        "role": role,
                        "text": text,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            ]
        )
        return msg_id

    async def search_chat_context(
        self, 
        user_id: int | str, 
        query_embedding: List[float], 
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Searches historical dialogue utterances strictly isolated for a specific user.
        
        :param user_id: Target user identifier to prevent context bleeding
        :param query_embedding: Vector representation of the incoming request
        :param limit: Maximum number of contexts to fetch
        """
        user_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=str(user_id))
                )
            ]
        )
        
        points = await self.engine.search(
            cl_name=self.chat_collection,
            query_vector=query_embedding,
            limit=limit,
            query_filter=user_filter
        )
        
        return [
            {
                "role": p.payload["role"], 
                "text": p.payload["text"], 
                "score": p.score
            } for p in points
        ]


    async def save_document_chunk(
        self, 
        doc_name: str, 
        chunk_text: str, 
        embedding: List[float], 
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Saves an isolated contextual text chunk from imported files/documents.
        
        :param doc_name: Source document file name
        :param chunk_text: Raw string chunk segment
        :param embedding: Dense vector embedding array
        :param metadata: Optional extra attributes (tags, authors, headers)
        """
        chunk_id = str(uuid.uuid4())
        payload = metadata or {}
        payload.update({
            "document_name": doc_name,
            "text": chunk_text,
            "uploaded_at": datetime.utcnow().isoformat()
        })
        
        await self.engine.client.upsert(
            collection_name=self.doc_collection,
            points=[
                models.PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )
        return chunk_id

    async def search_documents(self, query_embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Searches all indexed knowledge base document segments matching the query vector.
        """
        points = await self.engine.search(
            cl_name=self.doc_collection,
            query_vector=query_embedding,
            limit=limit
        )
        
        return [
            {
                "document_name": p.payload.get("document_name"),
                "text": p.payload.get("text"),
                "score": p.score,
                "metadata": {k: v for k, v in p.payload.items() if k not in ["document_name", "text"]}
            } for p in points
        ]

    async def close(self):
        """
        Gracefully tears down underlying active async client connection pools.
        """
        await self.engine.close()

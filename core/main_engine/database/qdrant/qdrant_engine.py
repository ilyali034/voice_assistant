from qdrant_client import AsyncQdrantClient, models 
from .qdrant_cfg import QdrantCfg 

class QEngine: 
    def __init__(self, cfg: QdrantCfg):
        self.host = cfg.host
        self.port = cfg.port 
        self.model_name = cfg.model_name 

        if cfg.local is True: 
            self.local_path = cfg.local_path or ":memory:"
            self.client = AsyncQdrantClient(path=self.local_path)

        elif cfg.api_key and cfg.url is not None: 
            self.api_key = cfg.api_key 
            self.url = cfg.url
            self.client = AsyncQdrantClient(url=cfg.url, api_key=cfg.api_key)

        else:
            self.client = AsyncQdrantClient(host=cfg.host, port=cfg.port)

    async def create_collection(self, cl_name: str):
        """Asynchronously creates a Qdrant collection matching your model vector dimensions."""
        
        vector_size = 384 if "all-MiniLM-L6-v2" in self.model_name else 1536
        
        await self.client.create_collection(
            collection_name=cl_name,
            vectors_config=models.VectorParams(
                size=vector_size, 
                distance=models.Distance.COSINE
            )
        )

    async def search(
        self, 
        cl_name: str, 
        query_vector: list[float], 
        limit: int = 5,
        query_filter: models.Filter | None = None
    ) -> list[models.ScoredPoint]:
        """Asynchronously queries a collection for the closest matching vector embeddings."""
        
        response = await self.client.query_points(
            collection_name=cl_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,  
            with_vectors=False  
        )
        
        return response.points

    async def close(self):
        """Utility to safely shut down underlying client connection pools."""
        await self.client.close()

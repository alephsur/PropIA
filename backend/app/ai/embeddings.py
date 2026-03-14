"""Generación de embeddings con Voyage AI."""
import voyageai
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client: voyageai.AsyncClient | None = None


def get_voyage_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    return _client


async def embed_texto(texto: str) -> list[float]:
    """Genera embedding para un texto."""
    client = get_voyage_client()
    result = await client.embed([texto], model="voyage-3", input_type="query")
    return result.embeddings[0]


async def embed_batch(textos: list[str]) -> list[list[float]]:
    """Genera embeddings en batch."""
    client = get_voyage_client()
    result = await client.embed(textos, model="voyage-3", input_type="document")
    return result.embeddings

"""Generación de embeddings con Ollama (local, sin coste)."""
import asyncio
import httpx
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0


async def _embed_single(texto: str) -> list[float]:
    """Llama a la API REST de Ollama para obtener el embedding de un texto."""
    url = f"{settings.ollama_base_url}/api/embeddings"
    payload = {"model": settings.embedding_model, "prompt": texto}

    for intento in range(1, _RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                return r.json()["embedding"]
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if intento < _RETRY_ATTEMPTS:
                logger.warning(f"Ollama no disponible (intento {intento}/{_RETRY_ATTEMPTS}), reintentando en {_RETRY_DELAY}s...")
                await asyncio.sleep(_RETRY_DELAY)
            else:
                raise RuntimeError(
                    f"Ollama no está disponible en {settings.ollama_base_url}. "
                    "Comprueba que el servicio está corriendo y el modelo está descargado."
                ) from e
        except Exception as e:
            raise RuntimeError(f"Error generando embedding con Ollama: {e}") from e

    return []  # nunca se alcanza


async def embed_texto(texto: str) -> list[float]:
    """Genera embedding para un texto (consultas RAG)."""
    return await _embed_single(texto)


async def embed_batch(textos: list[str]) -> list[list[float]]:
    """Genera embeddings en batch (indexación de documentos).

    Ollama no tiene endpoint batch nativo, se llama secuencialmente.
    """
    embeddings = []
    for texto in textos:
        emb = await _embed_single(texto)
        embeddings.append(emb)
    return embeddings

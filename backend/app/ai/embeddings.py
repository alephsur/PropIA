"""Generación de embeddings con Ollama (local, sin coste)."""
import asyncio
import httpx
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0

# Endpoint moderno de Ollama (>=0.1.26): acepta input como string o lista de strings
_EMBED_URL_TEMPLATE = "{base}/api/embed"

# mxbai-embed-large: 512 tokens. Español legal ~1,5-2 tokens/char → límite conservador.
_MAX_CHARS = 400

# Nº de textos por llamada batch. Ollama procesa el lote en una sola inferencia.
_BATCH_SIZE = 32


def _truncar(texto: str) -> str:
    if len(texto) > _MAX_CHARS:
        logger.warning(
            f"Chunk truncado de {len(texto)} a {_MAX_CHARS} chars antes de embedding. "
            "Revisa CHUNK_SIZE en pgou_index.py si esto aparece con frecuencia."
        )
        return texto[:_MAX_CHARS]
    return texto


async def _embed_request(textos: list[str]) -> list[list[float]]:
    """Envía una lista de textos a Ollama y devuelve sus embeddings en orden."""
    url = _EMBED_URL_TEMPLATE.format(base=settings.ollama_base_url)
    payload = {
        "model": settings.embedding_model,
        "input": textos,
        "truncate": True,
        "options": {"num_ctx": 512},
    }

    for intento in range(1, _RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, json=payload)
                if r.status_code != 200:
                    logger.error(
                        f"Ollama respondió {r.status_code} (intento {intento}, "
                        f"n={len(textos)} textos): {r.text[:300]}"
                    )
                    r.raise_for_status()
                return r.json()["embeddings"]
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if intento < _RETRY_ATTEMPTS:
                logger.warning(
                    f"Ollama no disponible (intento {intento}/{_RETRY_ATTEMPTS}), "
                    f"reintentando en {_RETRY_DELAY}s... ({e})"
                )
                await asyncio.sleep(_RETRY_DELAY)
            else:
                raise RuntimeError(
                    f"Ollama no está disponible en {settings.ollama_base_url}. "
                    "Comprueba que el servicio está corriendo y el modelo está descargado."
                ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Error HTTP {e.response.status_code} de Ollama "
                f"(n={len(textos)} textos): {e.response.text[:300]}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Error inesperado generando embeddings con Ollama: {e}") from e

    return []  # nunca se alcanza


async def embed_texto(texto: str) -> list[float]:
    """Genera embedding para un texto (consultas RAG)."""
    resultados = await _embed_request([_truncar(texto)])
    return resultados[0]


async def embed_batch(textos: list[str]) -> list[list[float]]:
    """Genera embeddings en batch usando la capacidad nativa de Ollama.

    Divide en sub-lotes de _BATCH_SIZE para no saturar la memoria del modelo.
    1431 chunks → ~45 llamadas en lugar de 1431.
    """
    textos_truncados = [_truncar(t) for t in textos]
    total = len(textos_truncados)
    embeddings: list[list[float]] = []

    for inicio in range(0, total, _BATCH_SIZE):
        lote = textos_truncados[inicio: inicio + _BATCH_SIZE]
        fin = min(inicio + _BATCH_SIZE, total)
        logger.debug(f"embed_batch: lote {inicio+1}-{fin}/{total} ({len(lote)} textos)")
        resultado = await _embed_request(lote)
        embeddings.extend(resultado)

    return embeddings

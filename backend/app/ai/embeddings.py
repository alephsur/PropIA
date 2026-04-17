"""Generación de embeddings con Ollama (local, sin coste).

Para textos que exceden la ventana del modelo, se aplica sliding window
con mean-pooling: se divide el texto en ventanas solapadas, se embebe cada
una, y se promedian los vectores. Esto preserva la semántica del texto
completo en un único vector de la misma dimensión.
"""
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

# mxbai-embed-large: 512 tokens por arquitectura BERT (inamovible).
# Texto jurídico español con números/siglas ~2.5 chars/token → 1000 chars ≈ 400 tok,
# con margen bajo el límite real. Con 1500 chars algunos chunks rebotaban como
# "input length exceeds context length" y Ollama tumba el batch entero.
_MAX_CHARS = 1000

# Solapamiento entre ventanas para no cortar entidades en el borde
_WINDOW_OVERLAP = 200

# Nº de textos (ventanas) por llamada batch. Ollama procesa el lote en una sola inferencia.
_BATCH_SIZE = 32


def _split_windows(texto: str) -> list[str]:
    """Divide un texto en ventanas solapadas si excede _MAX_CHARS.

    Textos cortos devuelven [texto]. Textos largos devuelven múltiples ventanas
    cuyos embeddings se mean-pool'arán para obtener un vector representativo
    del conjunto.
    """
    texto = (texto or "").strip()
    if not texto:
        return [""]
    if len(texto) <= _MAX_CHARS:
        return [texto]

    step = _MAX_CHARS - _WINDOW_OVERLAP
    ventanas: list[str] = []
    start = 0
    while start < len(texto):
        ventanas.append(texto[start:start + _MAX_CHARS])
        if start + _MAX_CHARS >= len(texto):
            break
        start += step
    return ventanas


def _mean_pool(vectores: list[list[float]]) -> list[float]:
    """Promedia vectores coordenada a coordenada.

    mxbai-embed-large devuelve vectores normalizados; el promedio preserva
    bien la dirección semántica dominante del conjunto.
    """
    if len(vectores) == 1:
        return vectores[0]
    dim = len(vectores[0])
    acum = [0.0] * dim
    for v in vectores:
        for i in range(dim):
            acum[i] += v[i]
    n = float(len(vectores))
    return [x / n for x in acum]


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
    """Genera embedding para un texto, con ventaneo automático si excede _MAX_CHARS."""
    ventanas = _split_windows(texto)
    resultados = await _embed_request(ventanas)
    return _mean_pool(resultados)


async def embed_batch(textos: list[str]) -> list[list[float]]:
    """Genera embeddings en batch con sliding window transparente.

    Para cada texto calcula sus ventanas, agrupa todas en lotes de _BATCH_SIZE,
    y hace mean-pool por texto original. Un chunk de 4000 chars se convierte en
    3 ventanas que se promedian → sigue siendo un único embedding por chunk.
    """
    if not textos:
        return []

    # 1. Ventanear cada texto y guardar rangos
    todas_ventanas: list[str] = []
    rangos: list[tuple[int, int]] = []
    for t in textos:
        ventanas = _split_windows(t)
        inicio = len(todas_ventanas)
        todas_ventanas.extend(ventanas)
        rangos.append((inicio, inicio + len(ventanas)))

    total = len(todas_ventanas)
    logger.debug(
        f"embed_batch: {len(textos)} textos → {total} ventanas "
        f"(~{total / len(textos):.1f} ventanas/texto)"
    )

    # 2. Embedding en sub-lotes
    embeddings_planos: list[list[float]] = []
    for i in range(0, total, _BATCH_SIZE):
        lote = todas_ventanas[i: i + _BATCH_SIZE]
        resultado = await _embed_request(lote)
        embeddings_planos.extend(resultado)

    # 3. Mean-pool por texto original
    pooled: list[list[float]] = []
    for (start, end) in rangos:
        pooled.append(_mean_pool(embeddings_planos[start:end]))
    return pooled

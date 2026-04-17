"""
Abstracción de clientes LLM.
Soporta Anthropic, OpenRouter y Groq con una interfaz unificada.
Incluye fallback automático entre proveedores al alcanzar límites de uso.
"""
import time

import anthropic
import httpx
import openai
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Límite de caracteres de entrada por proveedor (conservador, deja margen para system prompt y respuesta)
# Groq free tier: ~12 000 tokens/request. Sistema ~200 tok + respuesta ~2 000 tok → input ~9 800 tok ≈ 35 000 chars
_PROVIDER_MAX_INPUT_CHARS: dict[str, int] = {
    "groq": 35_000,
}

# Modelos por defecto para cada proveedor
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openrouter": "anthropic/claude-sonnet-4-5",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "qwen2.5:7b",  # modelo local — sin coste, sin límite de tokens
}

# Proveedores compatibles con OpenAI SDK (Ollama usa su API nativa para respetar num_ctx)
_OPENAI_COMPAT_PROVIDERS = {"openrouter", "groq"}

# Ventana de contexto para Ollama en inferencia LLM (embeddings no se ven afectados)
_OLLAMA_NUM_CTX = 32768


def _get_model(provider: str, model_override: str = "", settings=None) -> str:
    """Devuelve el modelo configurado o el modelo por defecto del proveedor."""
    if model_override:
        return model_override
    # Ollama usa su propio setting para no mezclar con el modelo de embeddings
    if provider == "ollama" and settings is not None:
        return settings.ollama_llm_model
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["anthropic"])


def _get_anthropic_client(settings) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _get_openai_compat_client(provider: str, settings) -> openai.OpenAI:
    if provider == "openrouter":
        return openai.OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
    if provider == "groq":
        return openai.OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
    if provider == "ollama":
        # Ollama expone endpoint compatible con OpenAI en /v1
        return openai.OpenAI(
            api_key="ollama",  # Ollama no requiere clave real
            base_url=f"{settings.ollama_base_url}/v1",
        )
    raise ValueError(f"Proveedor desconocido: {provider}")


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detecta si el error es un rate limit (HTTP 429) o quota agotada."""
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, anthropic.RateLimitError):
        return True
    # Algunos proveedores devuelven 429 como APIStatusError genérico
    if isinstance(exc, openai.APIStatusError) and exc.status_code == 429:
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 429:
        return True
    return False


def complete(system: str, user_content, max_tokens: int = 2000, provider_override: str = "") -> str:
    """
    Llama al LLM configurado y devuelve el texto de respuesta.
    Si el proveedor principal alcanza el límite de uso y hay un fallback configurado,
    reintenta automáticamente con el proveedor alternativo.

    Args:
        system: Prompt de sistema.
        user_content: Texto o lista de bloques de contenido (para visión).
        max_tokens: Límite de tokens en la respuesta.
        provider_override: Si se indica, ignora ai_provider y usa este proveedor directamente.

    Returns:
        Texto de la respuesta del modelo.
    """
    settings = get_settings()
    provider = provider_override or settings.ai_provider
    model = _get_model(provider, settings.ai_model if not provider_override else "", settings)

    input_chars = len(user_content) if isinstance(user_content, str) else sum(
        len(b.get("text", "")) for b in user_content if isinstance(b, dict)
    )
    logger.info(f"LLM call → proveedor={provider}, modelo={model}, input={input_chars} chars, max_tokens={max_tokens}")

    t0 = time.monotonic()
    try:
        result = _call_provider(provider, model, system, user_content, max_tokens, settings)
        logger.info(f"LLM ok ← {provider}/{model} en {time.monotonic() - t0:.2f}s ({len(result)} chars salida)")
        return result
    except Exception as exc:
        if not _is_rate_limit_error(exc):
            logger.error(f"LLM error ← {provider}/{model} tras {time.monotonic() - t0:.2f}s: {type(exc).__name__}")
            raise

        fallback_provider = settings.ai_provider_fallback
        if not fallback_provider:
            logger.warning(f"Rate limit en {provider}. No hay proveedor fallback configurado.")
            raise

        if fallback_provider == provider:
            logger.warning(f"Rate limit en {provider}. El fallback es el mismo proveedor, ignorando.")
            raise

        fallback_model = _get_model(fallback_provider, settings.ai_model_fallback, settings)
        logger.warning(
            f"Rate limit en {provider} ({type(exc).__name__}) tras {time.monotonic() - t0:.2f}s. "
            f"Reintentando con fallback: {fallback_provider} / {fallback_model}"
        )

        t1 = time.monotonic()
        result = _call_provider(fallback_provider, fallback_model, system, user_content, max_tokens, settings)
        logger.info(f"LLM ok (fallback) ← {fallback_provider}/{fallback_model} en {time.monotonic() - t1:.2f}s")
        return result


def _call_provider(provider: str, model: str, system: str, user_content, max_tokens: int, settings) -> str:
    """Despacha la llamada al proveedor indicado."""
    if provider == "anthropic":
        return _complete_anthropic(system, user_content, max_tokens, model, settings)

    if provider == "ollama":
        return _complete_ollama(system, user_content, max_tokens, model, settings)

    if provider in _OPENAI_COMPAT_PROVIDERS:
        return _complete_openai_compat(provider, system, user_content, max_tokens, model, settings)

    raise ValueError(f"Proveedor no soportado: {provider}. Usa 'anthropic', 'openrouter', 'groq' u 'ollama'.")


def _complete_anthropic(system, user_content, max_tokens, model, settings) -> str:
    client = _get_anthropic_client(settings)

    if isinstance(user_content, str):
        messages = [{"role": "user", "content": user_content}]
    else:
        messages = [{"role": "user", "content": user_content}]

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def _complete_ollama(system, user_content, max_tokens, model, settings) -> str:
    """Llama a la API nativa de Ollama (/api/chat) para respetar num_ctx correctamente."""
    if isinstance(user_content, str):
        content = user_content
    elif isinstance(user_content, list):
        # Extraer solo el texto — Ollama local no tiene visión en la mayoría de modelos
        partes = [b["text"] for b in user_content if isinstance(b, dict) and b.get("type") == "text"]
        content = "\n".join(partes)
    else:
        content = str(user_content)

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "options": {
            "num_ctx": _OLLAMA_NUM_CTX,
            "num_predict": max_tokens,
        },
    }

    response = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        timeout=300.0,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]
    logger.debug(f"Ollama raw response ({len(content)} chars): {content[:200]!r}")
    return content


def _truncate_for_provider(provider: str, user_content):
    """Trunca el contenido de entrada al límite del proveedor si es necesario."""
    max_chars = _PROVIDER_MAX_INPUT_CHARS.get(provider)
    if max_chars is None:
        return user_content
    if isinstance(user_content, str) and len(user_content) > max_chars:
        logger.warning(
            f"Texto truncado para {provider}: {len(user_content)} → {max_chars} chars"
        )
        return user_content[:max_chars] + "\n\n[... texto truncado por límite del proveedor ...]"
    return user_content


def _complete_openai_compat(provider, system, user_content, max_tokens, model, settings) -> str:
    client = _get_openai_compat_client(provider, settings)

    user_content = _truncate_for_provider(provider, user_content)

    if isinstance(user_content, str):
        content = user_content
    elif isinstance(user_content, list):
        content = _convert_content_blocks_to_openai(user_content)
    else:
        content = str(user_content)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content


def _convert_content_blocks_to_openai(blocks: list) -> list:
    """
    Convierte bloques de contenido del formato Anthropic al formato OpenAI.
    Soporta texto e imágenes base64.
    """
    openai_content = []
    for block in blocks:
        if isinstance(block, dict):
            if block.get("type") == "text":
                openai_content.append({"type": "text", "text": block["text"]})
            elif block.get("type") == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    data_url = f"data:{source['media_type']};base64,{source['data']}"
                    openai_content.append({
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    })
        elif isinstance(block, str):
            openai_content.append({"type": "text", "text": block})
    return openai_content


def get_provider_info() -> dict:
    """Devuelve info del proveedor y modelo activos (sin exponer claves)."""
    settings = get_settings()
    provider = settings.ai_provider
    model = _get_model(provider, settings.ai_model, settings)
    fallback_provider = settings.ai_provider_fallback or None
    fallback_model = _get_model(fallback_provider, settings.ai_model_fallback, settings) if fallback_provider else None
    return {
        "provider": provider,
        "model": model,
        "fallback_provider": fallback_provider,
        "fallback_model": fallback_model,
        "available_providers": list(DEFAULT_MODELS.keys()),
        "default_models": DEFAULT_MODELS,
    }

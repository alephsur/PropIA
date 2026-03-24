"""
Abstracción de clientes LLM.
Soporta Anthropic, OpenRouter y Groq con una interfaz unificada.
Incluye fallback automático entre proveedores al alcanzar límites de uso.
"""
import anthropic
import openai
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Modelos por defecto para cada proveedor
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openrouter": "anthropic/claude-sonnet-4-5",
    "groq": "llama-3.3-70b-versatile",
}

# Proveedores compatibles con OpenAI SDK
_OPENAI_COMPAT_PROVIDERS = {"openrouter", "groq"}


def _get_model(provider: str, model_override: str = "") -> str:
    """Devuelve el modelo configurado o el modelo por defecto del proveedor."""
    if model_override:
        return model_override
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


def complete(system: str, user_content, max_tokens: int = 2000) -> str:
    """
    Llama al LLM configurado y devuelve el texto de respuesta.
    Si el proveedor principal alcanza el límite de uso y hay un fallback configurado,
    reintenta automáticamente con el proveedor alternativo.

    Args:
        system: Prompt de sistema.
        user_content: Texto o lista de bloques de contenido (para visión).
        max_tokens: Límite de tokens en la respuesta.

    Returns:
        Texto de la respuesta del modelo.
    """
    settings = get_settings()
    provider = settings.ai_provider
    model = _get_model(provider, settings.ai_model)

    logger.debug(f"LLM call → proveedor={provider}, modelo={model}")

    try:
        return _call_provider(provider, model, system, user_content, max_tokens, settings)
    except Exception as exc:
        if not _is_rate_limit_error(exc):
            raise

        fallback_provider = settings.ai_provider_fallback
        if not fallback_provider:
            logger.warning(f"Rate limit en {provider}. No hay proveedor fallback configurado.")
            raise

        if fallback_provider == provider:
            logger.warning(f"Rate limit en {provider}. El fallback es el mismo proveedor, ignorando.")
            raise

        fallback_model = _get_model(fallback_provider, settings.ai_model_fallback)
        logger.warning(
            f"Rate limit en {provider} ({type(exc).__name__}). "
            f"Reintentando con fallback: {fallback_provider} / {fallback_model}"
        )

        return _call_provider(fallback_provider, fallback_model, system, user_content, max_tokens, settings)


def _call_provider(provider: str, model: str, system: str, user_content, max_tokens: int, settings) -> str:
    """Despacha la llamada al proveedor indicado."""
    if provider == "anthropic":
        return _complete_anthropic(system, user_content, max_tokens, model, settings)

    if provider in _OPENAI_COMPAT_PROVIDERS:
        return _complete_openai_compat(provider, system, user_content, max_tokens, model, settings)

    raise ValueError(f"Proveedor no soportado: {provider}. Usa 'anthropic', 'openrouter' o 'groq'.")


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


def _complete_openai_compat(provider, system, user_content, max_tokens, model, settings) -> str:
    client = _get_openai_compat_client(provider, settings)

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
    model = _get_model(provider, settings.ai_model)
    fallback_provider = settings.ai_provider_fallback or None
    fallback_model = _get_model(fallback_provider, settings.ai_model_fallback) if fallback_provider else None
    return {
        "provider": provider,
        "model": model,
        "fallback_provider": fallback_provider,
        "fallback_model": fallback_model,
        "available_providers": list(DEFAULT_MODELS.keys()),
        "default_models": DEFAULT_MODELS,
    }

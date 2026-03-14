"""
Abstracción de clientes LLM.
Soporta Anthropic, OpenRouter y Groq con una interfaz unificada.
"""
import json
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


def _get_model(provider: str, settings) -> str:
    """Devuelve el modelo configurado o el modelo por defecto del proveedor."""
    if settings.ai_model:
        return settings.ai_model
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


def complete(system: str, user_content, max_tokens: int = 2000) -> str:
    """
    Llama al LLM configurado y devuelve el texto de respuesta.

    Args:
        system: Prompt de sistema.
        user_content: Texto o lista de bloques de contenido (para visión).
        max_tokens: Límite de tokens en la respuesta.

    Returns:
        Texto de la respuesta del modelo.
    """
    settings = get_settings()
    provider = settings.ai_provider
    model = _get_model(provider, settings)

    logger.debug(f"LLM call → proveedor={provider}, modelo={model}")

    if provider == "anthropic":
        return _complete_anthropic(system, user_content, max_tokens, model, settings)

    if provider in _OPENAI_COMPAT_PROVIDERS:
        return _complete_openai_compat(provider, system, user_content, max_tokens, model, settings)

    raise ValueError(f"Proveedor no soportado: {provider}. Usa 'anthropic', 'openrouter' o 'groq'.")


def _complete_anthropic(system, user_content, max_tokens, model, settings) -> str:
    client = _get_anthropic_client(settings)

    # user_content puede ser str o lista de bloques (visión)
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

    # Convertir bloques de contenido Anthropic al formato OpenAI si es necesario
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
    model = _get_model(provider, settings)
    return {
        "provider": provider,
        "model": model,
        "available_providers": list(DEFAULT_MODELS.keys()),
        "default_models": DEFAULT_MODELS,
    }

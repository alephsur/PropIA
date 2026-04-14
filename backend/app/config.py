from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # IA — Anthropic
    anthropic_api_key: str = ""

    # Embeddings — Ollama local
    ollama_base_url: str = "http://ollama:11434"
    embedding_model: str = "mxbai-embed-large"
    embedding_dimensions: int = 1024
    # Modelo Ollama para inferencia LLM (distinto del modelo de embeddings)
    ollama_llm_model: str = "llama3.2"

    # IA — OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # IA — Groq
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Proveedor activo: "anthropic" | "openrouter" | "groq" | "ollama"
    ai_provider: str = "anthropic"
    # Modelo a usar (si vacío, se usa el modelo por defecto del proveedor)
    ai_model: str = ""
    # Proveedor de fallback cuando el principal alcanza el límite de uso (vacío = sin fallback)
    ai_provider_fallback: str = ""
    # Modelo para el proveedor fallback (vacío = modelo por defecto del proveedor fallback)
    ai_model_fallback: str = ""
    # Proveedor exclusivo para el módulo de documentos (vacío = usar ai_provider)
    # Recomendado: "ollama" para evitar límites de tokens en documentos grandes
    ai_provider_documentos: str = ""
    ai_model_documentos: str = ""

    # Base de datos
    database_url: str = "postgresql+asyncpg://propia:propia@db:5432/propia"

    # Servidor
    allowed_origins: str = "http://localhost:5173"
    log_level: str = "DEBUG"

    # Almacenamiento
    storage_path: str = "./storage/docs"
    max_pdf_size_mb: int = 100

    # Rate limiting
    rate_catastro: int = 60
    rate_urbanismo: int = 30
    rate_documentos: int = 10
    rate_biblioteca: int = 20

    class Config:
        env_file = ".env"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()

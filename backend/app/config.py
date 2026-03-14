from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # IA — Anthropic
    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    # IA — OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # IA — Groq
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Proveedor activo: "anthropic" | "openrouter" | "groq"
    ai_provider: str = "anthropic"
    # Modelo a usar (si vacío, se usa el modelo por defecto del proveedor)
    ai_model: str = ""

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

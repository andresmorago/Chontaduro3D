"""Configuración, leída del entorno (.env en desarrollo)."""

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    app_timezone: str = "America/Bogota"

    database_url: str = "postgresql+asyncpg://impresiones:impresiones@db:5432/misimpresiones"
    sql_echo: bool = False

    secret_key: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    # None = decidir por petición con X-Forwarded-Proto.
    cookie_secure: bool | None = None

    # Detrás del Worker de Cloudflare: la IP real llega en X-Real-Client-IP,
    # y solo se cree si la petición trae el secreto compartido.
    trust_proxy: bool = False
    proxy_shared_secret: str = ""

    admin_email: str = ""
    admin_password: str = ""

    media_dir: str = "/media"
    max_upload_mb: int = 5

    whatsapp_negocio: str = ""

    @model_validator(mode="after")
    def _validar(self) -> "Settings":
        if self.app_env == "production" and len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY es obligatoria en producción (mínimo 32 caracteres).")
        if not self.secret_key:
            if self.trust_proxy or self.proxy_shared_secret:
                raise ValueError(
                    "SECRET_KEY vacía con TRUST_PROXY/PROXY_SHARED_SECRET: detrás de un túnel "
                    "público no se puede firmar con la clave de desarrollo, que es pública."
                )
            # Desarrollo/pruebas: clave fija y evidente; nunca válida en producción.
            self.secret_key = "desarrollo-no-usar-en-produccion-0123456789abcdef"
        return self

    @property
    def es_produccion(self) -> bool:
        return self.app_env == "production"


settings = Settings()

"""Configuración, leída del entorno (.env en desarrollo)."""

from typing import Literal

from pydantic import field_validator, model_validator
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
    max_upload_mb: int = 12

    whatsapp_negocio: str = ""

    # Cloudflare Turnstile (el «reCAPTCHA» de Cloudflare). Sin SECRETKEY queda apagado (desarrollo).
    turnstile_sitekey: str = ""
    turnstile_secretkey: str = ""
    turnstile_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    # Impresora Bambu Lab: AHORA se configuran en Administración → Conexión (quedan cifradas en la
    # base). Estas variables solo se leen UNA vez, para importar a la base lo que ya tenías en el
    # .env; después se pueden borrar. Solo las recibe el servicio `impresora`.
    bambu_ip: str = ""
    bambu_serial: str = ""
    bambu_access_code: str = ""
    # Historial de Bambu Cloud: el token se vincula en el panel. Este archivo (el de
    # `make bambu-login`, ya retirado) solo se importa una vez a la base si existe.
    bambu_nube_url: str = "https://api.bambulab.com"
    bambu_nube_archivo: str = "/nube/bambu.json"
    bambu_nube_dias: int = 7

    # Spoolman (inventario de bobinas). Vacío = integración apagada. Dentro de Docker es
    # http://spoolman:8000; SPOOLMAN_WEB es solo el enlace que el panel muestra para abrirlo
    # (desde la red de casa por WireGuard) y no se usa para conectar.
    spoolman_url: str = ""
    spoolman_web: str = ""
    # Registrar solas en Spoolman las bobinas Bambu con chip del AMS (el UID del chip
    # es único: no se duplican). Apágalo (0) si prefieres crearlas tú a mano.
    spoolman_autocrear: bool = True

    @field_validator("cookie_secure", mode="before")
    @classmethod
    def _cookie_secure_vacio(cls, v):
        # Compose pasa `COOKIE_SECURE=` (vacío) cuando no se define: vacío = decidir por petición.
        return None if isinstance(v, str) and not v.strip() else v

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
    def turnstile_activo(self) -> bool:
        return bool(self.turnstile_secretkey and self.turnstile_sitekey)

    @property
    def es_produccion(self) -> bool:
        return self.app_env == "production"


settings = Settings()

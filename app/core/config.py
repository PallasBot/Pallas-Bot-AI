from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    log_level: str = "INFO"
    log_format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"
    )
    log_loc_short: bool = Field(
        default=False,
        validation_alias=AliasChoices("log_loc_short", "LOG_LOC_SHORT"),
    )
    server_log_level: str = Field(
        default="WARNING",
        validation_alias=AliasChoices("server_log_level", "SERVER_LOG_LEVEL"),
    )
    log_id_chars: int = Field(
        default=8,
        ge=0,
        le=32,
        validation_alias=AliasChoices("log_id_chars", "LOG_ID_CHARS"),
    )
    log_verbose_tasks: bool = Field(
        default=False,
        validation_alias=AliasChoices("log_verbose_tasks", "LOG_VERBOSE_TASKS"),
    )
    log_file_enabled: bool = True
    log_path: str = "logs"
    log_rotation: str = "10 MB"
    log_retention: str = "30 days"
    log_compression: str = "zip"

    redis_url: str = "redis://localhost:6379/0"

    callback_host: str = "localhost"
    callback_port: int = 8080
    callback_timeout: int = 10
    callback_max_retries: int = 3
    api_bearer_token: str = Field(
        default="",
        description="与 Bot WebUI「AI 服务」Bearer Token 一致；非空时 /api/ops/logs 等需 Authorization Bearer",
        validation_alias=AliasChoices("api_bearer_token", "PALLAS_AI_API_TOKEN", "API_BEARER_TOKEN"),
    )

    sing_speakers: dict = {"帕拉斯": "pallas", "牛牛": "pallas"}
    sing_length: int = 60
    sing_cuda_device: int = 0
    song_cache_size: int = 100
    song_cache_days: int = 30
    gpu_lock_wait_timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        validation_alias=AliasChoices("gpu_lock_wait_timeout", "GPU_LOCK_WAIT_TIMEOUT"),
    )
    gpu_lock_lease_ttl: int = Field(
        default=120,
        ge=10,
        le=600,
        validation_alias=AliasChoices("gpu_lock_lease_ttl", "GPU_LOCK_LEASE_TTL"),
    )
    gpu_lock_max_hold: int = Field(
        default=1800,
        ge=60,
        le=7200,
        validation_alias=AliasChoices("gpu_lock_max_hold", "GPU_LOCK_MAX_HOLD"),
    )
    media_subprocess_timeout: int = Field(
        default=600,
        ge=30,
        le=7200,
        validation_alias=AliasChoices("media_subprocess_timeout", "MEDIA_SUBPROCESS_TIMEOUT"),
    )
    media_device: str = Field(
        default="auto",
        validation_alias=AliasChoices("media_device", "MEDIA_DEVICE"),
    )
    svc_models_root: str = "resource/sing/models"
    svc_registry_path: str = "resource/sing/registry.yaml"
    svc_inference_timeout: int = 600
    ncm_phone: str = ""
    ncm_email: str = ""
    ncm_password: str = ""
    ncm_ctcode: int = 86

    translator_enable: bool = False
    baidu_app_id: str = ""
    baidu_secret_key: str = ""
    youdao_app_key: str = ""
    youdao_app_secret: str = ""
    default_translator: str = "baidu"

    chat_strategy: str = "cpu fp32"

    image_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("image_enabled", "IMAGE_ENABLED"),
    )
    image_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("image_base_url", "IMAGE_BASE_URL"),
    )
    image_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("image_api_key", "IMAGE_API_KEY"),
    )
    image_model: str = Field(
        default="gpt-image-1",
        validation_alias=AliasChoices("image_model", "IMAGE_MODEL"),
    )
    image_request_timeout: float = Field(
        default=180.0,
        validation_alias=AliasChoices("image_request_timeout", "IMAGE_REQUEST_TIMEOUT"),
    )
    image_open_circuit_failures: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias=AliasChoices("image_open_circuit_failures", "IMAGE_OPEN_CIRCUIT_FAILURES"),
    )
    image_circuit_cooldown_sec: int = Field(
        default=120,
        ge=5,
        le=3600,
        validation_alias=AliasChoices("image_circuit_cooldown_sec", "IMAGE_CIRCUIT_COOLDOWN_SEC"),
    )
    image_omit_response_format: bool = Field(
        default=True,
        validation_alias=AliasChoices("image_omit_response_format", "IMAGE_OMIT_RESPONSE_FORMAT"),
    )
    image_ref_download_timeout: float = Field(
        default=60.0,
        validation_alias=AliasChoices("image_ref_download_timeout", "IMAGE_REF_DOWNLOAD_TIMEOUT"),
    )
    media_task_ttl_sec: int = Field(
        default=86_400,
        ge=300,
        le=604_800,
        validation_alias=AliasChoices("media_task_ttl_sec", "MEDIA_TASK_TTL_SEC"),
    )

    celery_worker_concurrency: int = Field(
        default=3,
        ge=1,
        le=64,
        validation_alias=AliasChoices("celery_worker_concurrency", "CELERY_WORKER_CONCURRENCY"),
    )
    celery_worker_soft_shutdown_timeout: float = Field(
        default=15.0,
        ge=0.0,
        le=300.0,
        validation_alias=AliasChoices(
            "celery_worker_soft_shutdown_timeout",
            "CELERY_WORKER_SOFT_SHUTDOWN_TIMEOUT",
        ),
    )
    celery_task_packages: str = Field(
        default="sing,tts,chat",
        validation_alias=AliasChoices("celery_task_packages", "CELERY_TASK_PACKAGES"),
    )
    celery_task_soft_time_limit: float = Field(
        default=600.0,
        ge=0.0,
        le=7200.0,
        validation_alias=AliasChoices("celery_task_soft_time_limit", "CELERY_TASK_SOFT_TIME_LIMIT"),
    )
    celery_task_time_limit: float = Field(
        default=900.0,
        ge=0.0,
        le=7200.0,
        validation_alias=AliasChoices("celery_task_time_limit", "CELERY_TASK_TIME_LIMIT"),
    )

    uvicorn_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("uvicorn_host", "UVICORN_HOST"),
    )
    uvicorn_port: int = Field(
        default=9099,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("uvicorn_port", "UVICORN_PORT"),
    )
    uvicorn_reload: bool = Field(
        default=False,
        validation_alias=AliasChoices("uvicorn_reload", "UVICORN_RELOAD"),
    )
    uvicorn_reload_dirs: str = Field(
        default="app/api,app/core,app/services,app/schemas",
        validation_alias=AliasChoices("uvicorn_reload_dirs", "UVICORN_RELOAD_DIRS"),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

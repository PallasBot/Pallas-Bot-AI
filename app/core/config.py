from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    log_level: str = "INFO"
    log_format: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
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

    sing_speakers: dict = {"帕拉斯": "pallas", "牛牛": "pallas"}
    sing_length: int = 60
    sing_cuda_device: int = 0
    song_cache_size: int = 100
    song_cache_days: int = 30
    # SVC 模型后端注册表:加新模型族改 registry.yaml 即可,无需改 Python
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

    ollama_enable: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_auto_start: bool = False
    ollama_binary: str = "ollama"
    ollama_auto_pull: bool = True
    ollama_startup_timeout: float = 60.0
    ollama_max_histories: int = 100
    ollama_temperature: float = 0.55
    ollama_num_gpu: int | None = 12
    ollama_request_timeout: float = 90.0
    ollama_max_retries: int = 1
    ollama_retry_backoff: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

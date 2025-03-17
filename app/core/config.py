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

    sing_callback_endpoint: str = "/callback/sing"
    sing_speakers: dict = {"帕拉斯": "pallas", "牛牛": "pallas"}
    sing_length: int = 60
    sing_cuda_device: int = 0
    song_cache_size: int = 100
    song_cache_days: int = 30
    ncm_phone: str = ""
    ncm_email: str = ""
    ncm_password: str = ""
    ncm_ctcode: int = 86

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

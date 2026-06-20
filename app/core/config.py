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

    sing_speakers: dict = {"帕拉斯": "pallas", "牛牛": "pallas"}
    sing_length: int = 60
    sing_cuda_device: int = 0
    song_cache_size: int = 100
    song_cache_days: int = 30
    # GPU 全局互斥锁：所有上卡任务（LLM 推理 / 唱歌 / SVC / TTS）共用同一把锁，
    # 单卡显存装不下多任务并发，必须串行化。详见 app/utils/gpu_locker.py。
    gpu_lock_wait_timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        validation_alias=AliasChoices("gpu_lock_wait_timeout", "GPU_LOCK_WAIT_TIMEOUT"),
    )
    gpu_lock_lease_ttl: int = Field(
        default=60,
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
    # 是否让本地 LLM 推理也参与 GPU 锁。单卡部署必须开（默认），否则 LLM 与媒体
    # 任务会同时上卡 OOM。远程 LLM（LLM_BACKEND_URL 指向独立机器）可关掉省开销。
    gpu_lock_llm_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("gpu_lock_llm_enabled", "GPU_LOCK_LLM_ENABLED"),
    )
    # 媒体任务（唱歌分离 / SVC / TTS）运行设备：auto=用 GPU（sing_cuda_device），
    # cpu=强制 CPU。显存吃紧或想把 GPU 专留给 LLM 时设 cpu，代价是媒体任务变慢数倍。
    media_device: str = Field(
        default="auto",
        validation_alias=AliasChoices("media_device", "MEDIA_DEVICE"),
    )
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

    llm_chat_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("llm_chat_enabled", "LLM_CHAT_ENABLED", "ollama_enable", "OLLAMA_ENABLE"),
    )
    llm_backend_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("llm_backend_url", "LLM_BACKEND_URL", "ollama_url", "OLLAMA_URL"),
    )
    llm_model: str = Field(
        default="qwen2.5:7b",
        validation_alias=AliasChoices("llm_model", "LLM_MODEL", "ollama_model", "OLLAMA_MODEL"),
    )
    llm_auto_start: bool = Field(
        default=False,
        validation_alias=AliasChoices("llm_auto_start", "LLM_AUTO_START", "ollama_auto_start", "OLLAMA_AUTO_START"),
    )
    llm_backend_binary: str = Field(
        default="ollama",
        validation_alias=AliasChoices("llm_backend_binary", "LLM_BACKEND_BINARY", "ollama_binary", "OLLAMA_BINARY"),
    )
    llm_auto_pull: bool = Field(
        default=True,
        validation_alias=AliasChoices("llm_auto_pull", "LLM_AUTO_PULL", "ollama_auto_pull", "OLLAMA_AUTO_PULL"),
    )
    llm_startup_timeout: float = Field(
        default=60.0,
        validation_alias=AliasChoices(
            "llm_startup_timeout",
            "LLM_STARTUP_TIMEOUT",
            "ollama_startup_timeout",
            "OLLAMA_STARTUP_TIMEOUT",
        ),
    )
    llm_max_histories: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "llm_max_histories",
            "LLM_MAX_HISTORIES",
            "ollama_max_histories",
            "OLLAMA_MAX_HISTORIES",
        ),
    )
    llm_temperature: float = Field(
        default=0.55,
        validation_alias=AliasChoices(
            "llm_temperature",
            "LLM_TEMPERATURE",
            "ollama_temperature",
            "OLLAMA_TEMPERATURE",
        ),
    )
    llm_think_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("llm_think_enabled", "LLM_THINK_ENABLED"),
    )
    llm_num_gpu: int | None = Field(
        default=12,
        validation_alias=AliasChoices("llm_num_gpu", "LLM_NUM_GPU", "ollama_num_gpu", "OLLAMA_NUM_GPU"),
    )
    llm_request_timeout: float = Field(
        default=90.0,
        validation_alias=AliasChoices(
            "llm_request_timeout",
            "LLM_REQUEST_TIMEOUT",
            "ollama_request_timeout",
            "OLLAMA_REQUEST_TIMEOUT",
        ),
    )
    llm_max_retries: int = Field(
        default=1,
        validation_alias=AliasChoices("llm_max_retries", "LLM_MAX_RETRIES", "ollama_max_retries", "OLLAMA_MAX_RETRIES"),
    )
    llm_retry_backoff: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "llm_retry_backoff",
            "LLM_RETRY_BACKOFF",
            "ollama_retry_backoff",
            "OLLAMA_RETRY_BACKOFF",
        ),
    )
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

    llm_drunk_temperature: float = 1.0

    llm_provider_mode: str = Field(
        default="local_only",
        validation_alias=AliasChoices("llm_provider_mode", "LLM_PROVIDER_MODE"),
    )
    llm_local_multi_model_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("llm_local_multi_model_enabled", "LLM_LOCAL_MULTI_MODEL_ENABLED"),
    )
    llm_remote_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("llm_remote_base_url", "LLM_REMOTE_BASE_URL"),
    )
    llm_remote_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("llm_remote_api_key", "LLM_REMOTE_API_KEY"),
    )
    llm_remote_model: str = Field(
        default="",
        validation_alias=AliasChoices("llm_remote_model", "LLM_REMOTE_MODEL"),
    )
    llm_providers_file: str = Field(
        default="config/providers.toml",
        validation_alias=AliasChoices("llm_providers_file", "LLM_PROVIDERS_FILE"),
    )
    llm_chain_order: str = Field(
        default="local,remote",
        validation_alias=AliasChoices("llm_chain_order", "LLM_CHAIN_ORDER"),
    )
    llm_chain_on_failure: str = Field(
        default="try_next",
        validation_alias=AliasChoices("llm_chain_on_failure", "LLM_CHAIN_ON_FAILURE"),
    )
    llm_chain_local_tasks: str = Field(
        default="llm_chat,drunk",
        validation_alias=AliasChoices("llm_chain_local_tasks", "LLM_CHAIN_LOCAL_TASKS"),
    )
    llm_chain_remote_tasks: str = Field(
        default="repeater_fallback,repeater_polish,repeater_polish_lite,repeater_select",
        validation_alias=AliasChoices("llm_chain_remote_tasks", "LLM_CHAIN_REMOTE_TASKS"),
    )
    llm_routing: str = Field(
        default="manual",
        validation_alias=AliasChoices("llm_routing", "LLM_ROUTING"),
    )
    llm_moe_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("llm_moe_enabled", "LLM_MOE_ENABLED"),
    )
    llm_moe_model_simple: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_model_simple", "LLM_MOE_MODEL_SIMPLE"),
    )
    llm_moe_model_medium: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_model_medium", "LLM_MOE_MODEL_MEDIUM"),
    )
    llm_moe_model_complex: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_model_complex", "LLM_MOE_MODEL_COMPLEX"),
    )
    llm_moe_model_vision: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_model_vision", "LLM_MOE_MODEL_VISION"),
    )
    llm_moe_remote_model_simple: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_remote_model_simple", "LLM_MOE_REMOTE_MODEL_SIMPLE"),
    )
    llm_moe_remote_model_medium: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_remote_model_medium", "LLM_MOE_REMOTE_MODEL_MEDIUM"),
    )
    llm_moe_remote_model_complex: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_remote_model_complex", "LLM_MOE_REMOTE_MODEL_COMPLEX"),
    )
    llm_moe_remote_model_vision: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_remote_model_vision", "LLM_MOE_REMOTE_MODEL_VISION"),
    )
    llm_moe_tier_remote_tiers: str = Field(
        default="",
        validation_alias=AliasChoices("llm_moe_tier_remote_tiers", "LLM_MOE_TIER_REMOTE_TIERS"),
    )
    llm_moe_tier_remote_tasks: str = Field(
        default="llm_chat,drunk",
        validation_alias=AliasChoices("llm_moe_tier_remote_tasks", "LLM_MOE_TIER_REMOTE_TASKS"),
    )
    llm_moe_tier_remote_fallback: str = Field(
        default="local",
        validation_alias=AliasChoices("llm_moe_tier_remote_fallback", "LLM_MOE_TIER_REMOTE_FALLBACK"),
    )
    llm_task_model_chat: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_chat", "LLM_TASK_MODEL_CHAT"),
    )
    llm_task_model_chat_remote: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_chat_remote", "LLM_TASK_MODEL_CHAT_REMOTE"),
    )
    llm_task_model_drunk: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_drunk", "LLM_TASK_MODEL_DRUNK"),
    )
    llm_task_model_drunk_remote: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_drunk_remote", "LLM_TASK_MODEL_DRUNK_REMOTE"),
    )
    llm_task_model_repeater_fallback: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_repeater_fallback", "LLM_TASK_MODEL_REPEATER_FALLBACK"),
    )
    llm_task_model_repeater_fallback_remote: str = Field(
        default="",
        validation_alias=AliasChoices(
            "llm_task_model_repeater_fallback_remote",
            "LLM_TASK_MODEL_REPEATER_FALLBACK_REMOTE",
        ),
    )
    llm_task_model_repeater_polish: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_repeater_polish", "LLM_TASK_MODEL_REPEATER_POLISH"),
    )
    llm_task_model_repeater_polish_remote: str = Field(
        default="",
        validation_alias=AliasChoices(
            "llm_task_model_repeater_polish_remote",
            "LLM_TASK_MODEL_REPEATER_POLISH_REMOTE",
        ),
    )
    llm_task_model_repeater_polish_lite: str = Field(
        default="",
        validation_alias=AliasChoices(
            "llm_task_model_repeater_polish_lite",
            "LLM_TASK_MODEL_REPEATER_POLISH_LITE",
        ),
    )
    llm_task_model_repeater_polish_lite_remote: str = Field(
        default="",
        validation_alias=AliasChoices(
            "llm_task_model_repeater_polish_lite_remote",
            "LLM_TASK_MODEL_REPEATER_POLISH_LITE_REMOTE",
        ),
    )
    llm_task_model_repeater_select: str = Field(
        default="",
        validation_alias=AliasChoices("llm_task_model_repeater_select", "LLM_TASK_MODEL_REPEATER_SELECT"),
    )
    llm_task_model_repeater_select_remote: str = Field(
        default="",
        validation_alias=AliasChoices(
            "llm_task_model_repeater_select_remote",
            "LLM_TASK_MODEL_REPEATER_SELECT_REMOTE",
        ),
    )
    llm_task_model_affect_refine_remote: str = Field(
        default="",
        validation_alias=AliasChoices(
            "llm_task_model_affect_refine_remote",
            "LLM_TASK_MODEL_AFFECT_REFINE_REMOTE",
        ),
    )
    llm_tools_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("llm_tools_enabled", "LLM_TOOLS_ENABLED"),
    )
    llm_tools_max_rounds: int = Field(
        default=2,
        ge=1,
        le=8,
        validation_alias=AliasChoices("llm_tools_max_rounds", "LLM_TOOLS_MAX_ROUNDS"),
    )
    llm_tools_selective: bool = Field(
        default=True,
        validation_alias=AliasChoices("llm_tools_selective", "LLM_TOOLS_SELECTIVE"),
    )
    llm_categorizer_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("llm_categorizer_enabled", "LLM_CATEGORIZER_ENABLED"),
    )
    llm_categorizer_provider: str = Field(
        default="local",
        validation_alias=AliasChoices("llm_categorizer_provider", "LLM_CATEGORIZER_PROVIDER"),
    )
    llm_categorizer_model: str = Field(
        default="",
        validation_alias=AliasChoices("llm_categorizer_model", "LLM_CATEGORIZER_MODEL"),
    )
    llm_categorizer_num_predict: int = Field(
        default=48,
        ge=16,
        le=256,
        validation_alias=AliasChoices("llm_categorizer_num_predict", "LLM_CATEGORIZER_NUM_PREDICT"),
    )
    llm_session_backend: str = Field(
        default="redis",
        validation_alias=AliasChoices("llm_session_backend", "LLM_SESSION_BACKEND"),
    )
    llm_session_summary_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("llm_session_summary_enabled", "LLM_SESSION_SUMMARY_ENABLED"),
    )
    llm_session_summary_threshold: int = Field(
        default=40,
        ge=8,
        le=200,
        validation_alias=AliasChoices(
            "llm_session_summary_threshold",
            "LLM_SESSION_SUMMARY_THRESHOLD",
        ),
    )
    llm_session_summary_keep_messages: int = Field(
        default=16,
        ge=4,
        le=120,
        validation_alias=AliasChoices(
            "llm_session_summary_keep_messages",
            "LLM_SESSION_SUMMARY_KEEP_MESSAGES",
        ),
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
        default="llm",
        validation_alias=AliasChoices("celery_task_packages", "CELERY_TASK_PACKAGES"),
    )
    # 任务级超时兜底：软超时抛 SoftTimeLimitExceeded（任务可捕获并回调 failed），
    # 硬超时直接杀线程，防止单个卡死任务（GPU hang / ollama 无响应）拖垮整个 worker。
    # 软超时需大于 llm_request_timeout(默认90s)，媒体任务（唱歌分离/SVC）耗时更长，故默认给到分钟级。
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
    # LLM 聊天任务的入队过期时间（秒）：worker 取到时若已超过此时长，直接丢弃不执行。
    # 防止 worker 重启后把积压几小时的旧消息一股脑跑出来刷屏（聊天回复积压超过 2 分钟已无意义）。
    # 设 0 关闭过期（旧行为：积压任务全部执行）。
    llm_chat_task_expires: float = Field(
        default=120.0,
        ge=0.0,
        le=86400.0,
        validation_alias=AliasChoices("llm_chat_task_expires", "LLM_CHAT_TASK_EXPIRES"),
    )

    persona_affect_refine_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("persona_affect_refine_enabled", "PERSONA_AFFECT_REFINE_ENABLED"),
    )
    persona_affect_refine_model: str = ""
    persona_affect_refine_timeout_sec: float = Field(
        default=90.0,
        ge=10.0,
        le=300.0,
        validation_alias=AliasChoices(
            "persona_affect_refine_timeout_sec",
            "PERSONA_AFFECT_REFINE_TIMEOUT_SEC",
        ),
    )
    persona_affect_refine_max_concurrent: int = Field(
        default=1,
        ge=1,
        le=4,
        validation_alias=AliasChoices(
            "persona_affect_refine_max_concurrent",
            "PERSONA_AFFECT_REFINE_MAX_CONCURRENT",
        ),
    )
    persona_affect_refine_temperature: float = 0.3
    persona_affect_refine_max_samples: int = 12
    persona_affect_refine_min_confidence: float = 0.4
    persona_affect_refine_allow_heuristic: bool = True

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
        default="app/api,app/core,app/providers,app/services,app/schemas,app/session",
        validation_alias=AliasChoices("uvicorn_reload_dirs", "UVICORN_RELOAD_DIRS"),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

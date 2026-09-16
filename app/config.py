from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://user:cyberdb@localhost:5432/cyber_ai_festival"

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    log_level: str = "INFO"

    # API Security
    api_key: str = ""

    # External venue queue system (see doc/QUEUE_INTEGRATION.md).
    # Disabled unless the deployment provides a queue id + api key.
    queue_enabled: bool = False
    queue_base_url: str = "https://queue-system-e6780.web.app/api"
    queue_queue_id: str = ""
    queue_api_key: str = ""
    queue_timeout_seconds: float = 10.0

    # CORS: comma-separated origin allow-list, e.g.
    # "https://d24umo4oysfx97.cloudfront.net,http://localhost:1688".
    # Empty = keep the current permissive behaviour ("*"), so not configuring this
    # never breaks the platform; set it in the deployment env to actually restrict.
    cors_origins: str = ""


settings = Settings()

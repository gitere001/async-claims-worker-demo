from pydantic_settings import BaseSettings
from config.app_settings import settings as st


class Settings(BaseSettings):
    DATABASE_URL: str = st.get("database_url", "")
    REDIS_URL: str = st.get("redis_url", "")
    RABBIT_MQ_URL: str = st.get("rabbitmq_url", "")


settings = Settings()

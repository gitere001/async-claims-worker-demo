import os
from dotenv import load_dotenv

load_dotenv()

settings = {
    "database_url": os.getenv("DATABASE_URL"),
    "redis_url": os.getenv("REDIS_URL"),
    "rabbitmq_url": os.getenv("RABBIT_MQ_URL"),
}

import os
from dotenv import load_dotenv

load_dotenv()

settings = {
    "database_url": os.getenv("DATABASE_URL"),
    "redis_url": os.getenv("REDIS_URL"),
    "rabbitmq_url": os.getenv("RABBIT_MQ_URL"),
    "resend_api_key": os.getenv("RESEND_API_KEY"),
    "from_email": os.getenv("FROM_EMAIL"),
    "to_email": os.getenv("TO_EMAIL"),
}

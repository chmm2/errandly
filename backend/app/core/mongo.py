from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_url)
mongo_db = mongo_client[settings.mongo_db]

# Chat messages live here (one document per message).
chat_messages = mongo_db["chat_messages"]

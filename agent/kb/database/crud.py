from motor.motor_asyncio import AsyncIOMotorCollection


class MongoDBCRUD:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def create(self, data: dict) -> dict:
        await self.collection.insert_one(data)
        return {"success": True}

    async def read(self, query: dict) -> dict:
        return await self.collection.find_one(query)

    async def read_all(self, query: dict, projection: dict = None) -> list:
        cursor = self.collection.find(query, projection)
        return await cursor.to_list(length=None)

    async def update(self, query, update_data: dict) -> dict:
        await self.collection.update_one(query, {"$set": update_data})
        return await self.read(query)

    async def delete_one(self, data):
        result = await self.collection.delete_one(data)
        return result.deleted_count > 0

    async def delete_many(self, data):
        result = await self.collection.delete_many(data)
        return result.deleted_count

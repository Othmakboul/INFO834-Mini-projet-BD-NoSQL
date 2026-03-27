import redis 
from pymongo import MongoClient

def get_redis_client():
    return redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True
    )

def get_mongo_db():
    # On se connecte en direct (Direct Connection) au port local mappé 
    # pour contourner le problème de résolution DNS de Windows vers Docker
    uri = "mongodb://localhost:27017/?directConnection=true"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client["tchat_app"]
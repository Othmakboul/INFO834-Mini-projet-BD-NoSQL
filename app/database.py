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
    # Liste complète des membres pour que le driver trouve le nouveau "chef"
    uri = "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=tchat-rs"    # On ajoute un timeout pour ne pas attendre 30s en cas de problème
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client["tchat_app"]
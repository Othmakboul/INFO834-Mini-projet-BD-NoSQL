import redis 
from pymongo import MongoClient

def redis_connection():
    client = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True
    )
    return client


def get_mongo_connection():
    uri = "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=tchat-rs"
    client = MongoClient(uri)
    db = client["tchat_app"]
    return db
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
    # directConnection=true : connexion directe au Primary depuis l'hôte Windows.
    # Le ReplicaSet tourne bien dans Docker (tolérance aux pannes),
    # mais la découverte automatique échoue car les nœuds s'annoncent
    # en "host.docker.internal" inaccessible depuis l'extérieur.
    uri = "mongodb://localhost:27017/?directConnection=true"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client["tchat_app"]
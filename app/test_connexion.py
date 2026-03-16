from database import get_redis_client, get_mongo_db
import datetime

def tester_redis():
    print("--- Test Redis ---")
    client = get_redis_client()
    
    client.set("othmane", "en ligne")
    
    
    valeur = client.get("othmane")
    print(f"Statut lu depuis Redis : {valeur}")

def tester_mongo():
    print("\n Test MongoDB ")
    db = get_mongo_db()
    
    collection = db["messages_test"]
    
    faux_message = {
        "expediteur": "Bot",
        "message": "Connexion au ReplicaSet réussie ",
        "date": datetime.datetime.now(datetime.timezone.utc)
    }
    resultat = collection.insert_one(faux_message)
    print(f"Document inséré avec l'ID : {resultat.inserted_id}")
    
    message_lu = collection.find_one({"expediteur": "Bot"})
    print(f"Message lu depuis MongoDB : {message_lu['message']}")

if __name__ == "__main__":
    tester_redis()
    tester_mongo()
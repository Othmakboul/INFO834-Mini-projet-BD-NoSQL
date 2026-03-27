from database import get_mongo_db
import datetime

class MongoManager:
    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db["messages"]

    def save_message(self, sender, receiver, content, room="Général"):
        """Enregistre un message dans MongoDB avec contexte de salon."""
        try:
            message = {
                "sender": sender,
                "receiver": receiver,
                "content": content,
                "room": room,
                "timestamp": datetime.datetime.now(datetime.timezone.utc)
            }
            result = self.collection.insert_one(message)
            return result.inserted_id
        except Exception as e:
            print(f"❌ Erreur MongoDB (save) : {e}")
            return None

    def get_room_history(self, room_id, limit=50):
        """Récupère l'historique pour un salon ou une conversation privée."""
        try:
            query = {"room": room_id}
            cursor = self.collection.find(query).sort("timestamp", 1).limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"❌ Erreur MongoDB (history) : {e}")
            return []
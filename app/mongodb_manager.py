from database import get_mongo_db
import datetime

class MongoManager:
    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db["messages"]

    def get_conversation(self, user_a, user_b):
        """Récupère tous les messages échangés entre deux utilisateurs."""
        query = {
            "$or": [
                {"sender": user_a, "receiver": user_b},
                {"sender": user_b, "receiver": user_a}
            ]
        }
        # On trie par date pour avoir l'ordre chronologique
        messages = self.collection.find(query).sort("timestamp", 1)
        
        print(f"\n--- Historique entre {user_a} et {user_b} ---")
        for msg in messages:
            heure = msg['timestamp'].strftime("%H:%M")
            print(f"[{heure}] {msg['sender']} : {msg['content']}")

    def save_message(self, sender, receiver, content):
        try:
            message = {
                "sender": sender,
                "receiver": receiver,
                "content": content,
                "timestamp": datetime.datetime.now(datetime.timezone.utc)
            }
            result = self.collection.insert_one(message)
            print(f"✅ Message enregistré avec l'ID : {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Erreur lors de l'enregistrement : {e}")

# --- PETIT TEST POUR TOI ---
if __name__ == "__main__":
    manager = MongoManager()
    
    # 1. On simule quelques messages
    print("Envoi de messages de test...")
    manager.save_message("Othmane", "Alice", "Salut Alice !")
    manager.save_message("Alice", "Othmane", "Coucou Othmane, ça marche ?")
    manager.save_message("Othmane", "Alice", "Oui, le ReplicaSet est opérationnel !")

    # 2. On affiche l'historique
    manager.get_conversation("Othmane", "Alice")
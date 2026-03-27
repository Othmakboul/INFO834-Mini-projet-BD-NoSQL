from database import get_mongo_db
import datetime

class MongoManager:
    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db["messages"]

    def get_all_messages(self):
        """Récupère tous les messages du tchat public."""
        messages = self.collection.find().sort("timestamp", 1)
        print("\n--- Historique Complet du Tchat ---")
        for msg in messages:
            # Gestion de l'heure
            dt = msg.get('timestamp')
            heure = dt.strftime("%H:%M") if dt else "--:--"
            print(f"[{heure}] {msg['sender']} : {msg['content']}")

    def get_user_stats(self):
        """Statistiques : Qui envoie le plus de messages."""
        pipeline = [
            {"$group": {"_id": "$sender", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        stats = list(self.collection.aggregate(pipeline))
        print("\n--- Stats : Top Envoyeurs ---")
        for s in stats:
            print(f"Utilisateur: {s['_id']} | Messages: {s['count']}")

if __name__ == "__main__":
    manager = MongoManager()
    
    # On affiche TOUT ce qui a été capturé par le serveur
    manager.get_all_messages()
    
    # On affiche les stats
    manager.get_user_stats()
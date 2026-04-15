from database import get_mongo_db
import datetime

class MongoManager:
    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db["messages"]

    def save_message(self, sender, receiver, content):
        """Enregistre un nouveau message dans MongoDB."""
        message_doc = {
            "sender": sender,
            "receiver": receiver,
            "content": content,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        self.collection.insert_one(message_doc)

    # ------------------------------------------------------------------
    # REQUÊTES D'HISTORIQUE
    # ------------------------------------------------------------------

    def get_all_messages(self):
        """Récupère tous les messages du tchat public."""
        messages = list(self.collection.find().sort("timestamp", 1))
        lines = []
        for msg in messages:
            dt = msg.get('timestamp')
            heure = dt.strftime("%H:%M") if dt else "--:--"
            lines.append(f"[{heure}] {msg['sender']} -> {msg['receiver']} : {msg['content']}")
        return lines

    def get_conversation(self, user1, user2):
        """Historique filtré entre deux utilisateurs précis (privé dans les deux sens)."""
        query = {
            "$or": [
                {"sender": user1, "receiver": user2},
                {"sender": user2, "receiver": user1}
            ]
        }
        messages = list(self.collection.find(query).sort("timestamp", 1))
        lines = []
        for msg in messages:
            dt = msg.get('timestamp')
            heure = dt.strftime("%H:%M") if dt else "--:--"
            lines.append(f"[{heure}] {msg['sender']} : {msg['content']}")
        return lines

    def search_by_keyword(self, keyword):
        """Recherche tous les messages contenant un mot-clé (insensible à la casse)."""
        query = {"content": {"$regex": keyword, "$options": "i"}}
        messages = list(self.collection.find(query).sort("timestamp", 1))
        lines = []
        for msg in messages:
            dt = msg.get('timestamp')
            heure = dt.strftime("%H:%M") if dt else "--:--"
            lines.append(f"[{heure}] {msg['sender']} -> {msg['receiver']} : {msg['content']}")
        return lines

    def search_by_time_range(self, heure_debut, heure_fin):
        """
        Recherche les messages envoyés dans une plage horaire (format HH:MM).
        Compare uniquement l'heure/minute sur la journée en cours (UTC).
        """
        aujourd_hui = datetime.datetime.now(datetime.timezone.utc).date()
        h_debut = int(heure_debut.split(":")[0])
        m_debut = int(heure_debut.split(":")[1])
        h_fin   = int(heure_fin.split(":")[0])
        m_fin   = int(heure_fin.split(":")[1])

        debut = datetime.datetime(
            aujourd_hui.year, aujourd_hui.month, aujourd_hui.day,
            h_debut, m_debut, tzinfo=datetime.timezone.utc
        )
        fin = datetime.datetime(
            aujourd_hui.year, aujourd_hui.month, aujourd_hui.day,
            h_fin, m_fin, tzinfo=datetime.timezone.utc
        )

        query = {"timestamp": {"$gte": debut, "$lte": fin}}
        messages = list(self.collection.find(query).sort("timestamp", 1))
        lines = []
        for msg in messages:
            dt = msg.get('timestamp')
            heure = dt.strftime("%H:%M") if dt else "--:--"
            lines.append(f"[{heure}] {msg['sender']} -> {msg['receiver']} : {msg['content']}")
        return lines

    # ------------------------------------------------------------------
    # REQUÊTES STATISTIQUES
    # ------------------------------------------------------------------

    def get_top_senders(self):
        """Qui envoie le plus de messages (tous types confondus)."""
        pipeline = [
            {"$group": {"_id": "$sender", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        stats = list(self.collection.aggregate(pipeline))
        lines = ["--- Top expéditeurs ---"]
        for s in stats:
            lines.append(f"  {s['_id']} : {s['count']} message(s) envoyé(s)")
        return lines

    def get_most_solicited(self):
        """Utilisateur le plus sollicité : qui reçoit le plus de messages privés."""
        pipeline = [
            {"$match": {"receiver": {"$ne": "Tous"}}},
            {"$group": {"_id": "$receiver", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        stats = list(self.collection.aggregate(pipeline))
        lines = ["--- Utilisateurs les plus sollicités (messages privés) ---"]
        if not stats:
            lines.append("  Aucun message privé pour l'instant.")
        for s in stats:
            lines.append(f"  {s['_id']} : {s['count']} message(s) reçu(s) en privé")
        return lines

    def get_full_stats(self):
        """Retourne toutes les stats en une seule réponse."""
        lines = []
        lines += self.get_top_senders()
        lines.append("")
        lines += self.get_most_solicited()
        lines.append(f"\n  Total messages : {self.collection.count_documents({})}")
        return lines


if __name__ == "__main__":
    manager = MongoManager()

    print("\n".join(manager.get_all_messages()) or "Aucun message.")
    print()
    print("\n".join(manager.get_full_stats()))

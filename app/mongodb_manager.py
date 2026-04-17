from database import get_mongo_db
import datetime

class MongoManager:
    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db["messages"]
        self.users = self.db["users"]
        self.groups = self.db["groups"]

    def save_message(self, sender, receiver, content, room="Général"):
        """Enregistre un nouveau message dans MongoDB."""
        message_doc = {
            "sender": sender,
            "receiver": receiver,
            "content": content,
            "room": room,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        self.collection.insert_one(message_doc)

    # ------------------------------------------------------------------
    # REQUÊTES D'HISTORIQUE (TEAM FEATURES)
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

    def get_room_history(self, room, limit=50):
        """Récupère l'historique d'un salon ou groupe."""
        try:
            return list(self.collection.find({"room": room}).sort("timestamp", 1).limit(limit))
        except Exception as e:
            print(f"❌ Erreur Mongo (get_room_history) : {e}")
            return []

    def search_by_keyword(self, keyword):
        """Recherche tous les messages contenant un mot-clé (retourne les objets complets)."""
        query = {"content": {"$regex": keyword, "$options": "i"}}
        messages = list(self.collection.find(query).sort("timestamp", 1))
        # On convertit les ObjectId en string pour JSON
        for m in messages:
            m['_id'] = str(m['_id'])
            if 'timestamp' in m and m['timestamp']:
                m['timestamp'] = m['timestamp'].strftime("%H:%M")
        return messages

    def search_by_time_range(self, heure_debut, heure_fin):
        """Recherche les messages envoyés dans une plage horaire (retourne les objets complets)."""
        aujourd_hui = datetime.datetime.now(datetime.timezone.utc).date()
        try:
            h_debut, m_debut = map(int, heure_debut.split(":"))
            h_fin, m_fin = map(int, heure_fin.split(":"))
            
            debut = datetime.datetime(aujourd_hui.year, aujourd_hui.month, aujourd_hui.day, h_debut, m_debut, tzinfo=datetime.timezone.utc)
            fin = datetime.datetime(aujourd_hui.year, aujourd_hui.month, aujourd_hui.day, h_fin, m_fin, tzinfo=datetime.timezone.utc)
            
            query = {"timestamp": {"$gte": debut, "$lte": fin}}
            messages = list(self.collection.find(query).sort("timestamp", 1))
            for m in messages:
                m['_id'] = str(m['_id'])
                if 'timestamp' in m and m['timestamp']:
                    m['timestamp'] = m['timestamp'].strftime("%H:%M")
            return messages
        except Exception as e:
            return []

    # ------------------------------------------------------------------
    # REQUÊTES STATISTIQUES (TEAM FEATURES)
    # ------------------------------------------------------------------

    def get_top_senders(self):
        """Qui envoie le plus de messages."""
        pipeline = [
            {"$group": {"_id": "$sender", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        return list(self.collection.aggregate(pipeline))

    def get_most_solicited(self):
        """Utilisateur le plus sollicité."""
        pipeline = [
            {"$match": {"receiver": {"$ne": "Tous"}}},
            {"$group": {"_id": "$receiver", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        return list(self.collection.aggregate(pipeline))

    def get_full_stats_as_lines(self):
        """Version texte des stats pour le client TCP."""
        lines = ["--- Top expéditeurs ---"]
        for s in self.get_top_senders():
            lines.append(f"  {s['_id']} : {s['count']} message(s)")
        lines.append("\n--- Les plus sollicités (MP) ---")
        for s in self.get_most_solicited():
            lines.append(f"  {s['_id']} : {s['count']} message(s)")
        lines.append(f"\n  Total messages : {self.collection.count_documents({})}")
        return lines

    # ------------------------------------------------------------------
    # GESTION UTILISATEURS & GROUPES (UI FEATURES)
    # ------------------------------------------------------------------

    def register_or_login(self, username, password):
        """Authentification simple pour le mode Pro."""
        try:
            user = self.users.find_one({"_id": username})
            if user:
                if user.get("password") == password:
                    return True, "Bon retour !"
                else:
                    return False, "Pseudo déjà pris ou mauvais mot de passe."
            else:
                self.users.insert_one({
                    "_id": username,
                    "password": password,
                    "bio": "",
                    "contacts": [],
                    "groups": ["Général"],
                    "created_at": datetime.datetime.now(datetime.timezone.utc)
                })
                return True, "Compte créé !"
        except Exception as e:
            print(f"❌ Erreur Mongo (login) : {e}")
            return False, "Erreur interne serveur."

    def get_user_info(self, username):
        user = self.users.find_one({"_id": username})
        if user:
            return {"username": user["_id"], "bio": user.get("bio", "Salut !")}
        return None

    def update_profile(self, username, bio):
        self.users.update_one({"_id": username}, {"$set": {"bio": bio}})
        return True, "Profil mis à jour."

    def add_contact(self, username, contact_username):
        if not self.users.find_one({"_id": contact_username}):
            return False, "Utilisateur inexistant."
        if username == contact_username:
            return False, "C'est vous !"
        self.users.update_one({"_id": username}, {"$addToSet": {"contacts": contact_username}})
        self.users.update_one({"_id": contact_username}, {"$addToSet": {"contacts": username}})
        return True, "Contact ajouté."

    def create_group(self, name, creator, members):
        if self.groups.find_one({"_id": name}):
            return False, "Groupe déjà existant."
        all_members = list(set([creator] + members))
        self.groups.insert_one({"_id": name, "creator": creator, "members": all_members})
        for m in all_members:
            self.users.update_one({"_id": m}, {"$addToSet": {"groups": name}})
        return True, "Groupe créé !"

    def get_user_conversations(self, username):
        user = self.users.find_one({"_id": username})
        if not user: return {"contacts": [], "groups": ["Général"]}
        return {"contacts": user.get("contacts", []), "groups": user.get("groups", ["Général"])}

    def search_users(self, prefix):
        results = self.users.find({"_id": {"$regex": f"^{prefix}", "$options": "i"}}).limit(5)
        return [u["_id"] for u in results]

if __name__ == "__main__":
    manager = MongoManager()
    print("\n".join(manager.get_full_stats_as_lines()))

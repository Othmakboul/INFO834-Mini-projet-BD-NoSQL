from database import get_mongo_db
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

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
        return self.collection.insert_one(message_doc).inserted_id

    def get_room_history(self, room, limit=50):
        """Récupère l'historique d'un salon ou groupe."""
        try:
            return list(self.collection.find({"room": room}).sort("timestamp", 1).limit(limit))
        except Exception as e:
            print(f"❌ Erreur Mongo (get_room_history) : {e}")
            return []

    def get_conversation(self, user1, user2):
        """Historique filtré entre deux utilisateurs précis."""
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

    # ------------------------------------------------------------------
    # REQUÊTES RECHERCHE & STATS (DASHBOARD ELITE)
    # ------------------------------------------------------------------

    def search_by_keyword(self, keyword):
        """Recherche tous les messages contenant un mot-clé."""
        query = {"content": {"$regex": keyword, "$options": "i"}}
        messages = list(self.collection.find(query).sort("timestamp", 1))
        for m in messages:
            m['_id'] = str(m['_id'])
            if 'timestamp' in m and m['timestamp']:
                m['timestamp'] = m['timestamp'].strftime("%H:%M")
        return messages

    def search_by_time_range(self, heure_debut, heure_fin):
        """Recherche les messages envoyés dans une plage horaire."""
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

    def get_top_senders(self):
        """Agrégation : Qui envoie le plus de messages."""
        pipeline = [
            {"$group": {"_id": "$sender", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        return list(self.collection.aggregate(pipeline))

    def get_most_solicited(self):
        """Agrégation : Utilisateur le plus sollicité (MP)."""
        pipeline = [
            {"$match": {"receiver": {"$nin": ["Tous", "GLOBAL"]}}},
            {"$group": {"_id": "$receiver", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        return list(self.collection.aggregate(pipeline))

    def get_full_stats_as_lines(self):
        """Version texte pour client TCP."""
        lines = ["--- Top expéditeurs ---"]
        for s in self.get_top_senders():
            lines.append(f"  {s['_id']} : {s['count']} message(s)")
        lines.append("\n--- Les plus sollicités (MP) ---")
        for s in self.get_most_solicited():
            lines.append(f"  {s['_id']} : {s['count']} message(s)")
        lines.append(f"\n  Total messages : {self.collection.count_documents({})}")
        return lines

    # ------------------------------------------------------------------
    # GESTION UTILISATEURS & GROUPES (SECURITY & ADMIN)
    # ------------------------------------------------------------------

    def register_or_login(self, username, password):
        """Authentification unifiée intelligente."""
        try:
            user = self.users.find_one({"_id": username})
            if user:
                stored_password = user.get("password")
                if not stored_password:
                    # Cas rare d'un utilisateur sans mot de passe (migration?)
                    hashed = generate_password_hash(password)
                    self.users.update_one({"_id": username}, {"$set": {"password": hashed}})
                    return True, "Mot de passe configuré."
                
                if check_password_hash(stored_password, password):
                    return True, "Connexion réussie."
                else:
                    return False, f"Le pseudo '{username}' est déjà pris. Si c'est vous, vérifiez votre mot de passe."
            else:
                hashed = generate_password_hash(password)
                self.users.insert_one({
                    "_id": username,
                    "password": hashed,
                    "contacts": [],
                    "groups": ["Général"],
                    "bio": "Salut ! J'utilise Nexus Chat."
                })
                return True, "Nouveau compte créé ! Bienvenue."
        except Exception as e:
            print(f"❌ Erreur Mongo (auth) : {e}")
            return False, "Erreur serveur. Veuillez réessayer."

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
        self.groups.insert_one({"_id": name, "creator": creator, "members": all_members, "created_at": datetime.datetime.now(datetime.timezone.utc)})
        for m in all_members:
            self.users.update_one({"_id": m}, {"$addToSet": {"groups": name}})
        return True, "Groupe créé !"

    def get_group_info(self, group_name):
        if group_name == "Général":
            return {"_id": "Général", "creator": "Système", "members": []}
        return self.groups.find_one({"_id": group_name})

    def add_group_members(self, admin, group_name, new_members):
        group = self.groups.find_one({"_id": group_name})
        if not group or group.get("creator") != admin:
            return False, "Non autorisé.", []
        valid_users = [u["_id"] for u in self.users.find({"_id": {"$in": new_members}})]
        if not valid_users:
            return False, "Membres invalides.", []
        self.groups.update_one({"_id": group_name}, {"$addToSet": {"members": {"$each": valid_users}}})
        self.users.update_many({"_id": {"$in": valid_users}}, {"$addToSet": {"groups": group_name}})
        return True, "Membres ajoutés.", valid_users

    def kick_group_member(self, admin, group_name, target):
        group = self.groups.find_one({"_id": group_name})
        if not group or group.get("creator") != admin:
            return False, "Non autorisé."
        if target == admin:
            return False, "Action impossible."
        self.groups.update_one({"_id": group_name}, {"$pull": {"members": target}})
        self.users.update_one({"_id": target}, {"$pull": {"groups": group_name}})
        return True, f"{target} exclu."

    def get_user_conversations(self, username):
        user = self.users.find_one({"_id": username})
        if not user: return {"contacts": [], "groups": ["Général"]}
        return {"contacts": user.get("contacts", []), "groups": user.get("groups", ["Général"])}

    def search_users(self, prefix):
        results = self.users.find({"_id": {"$regex": f"^{prefix}", "$options": "i"}}).limit(5)
        return [u["_id"] for u in results]

    def remove_contact(self, username, contact_username):
        self.users.update_one({"_id": username}, {"$pull": {"contacts": contact_username}})
        return True, "Contact supprimé."

    def leave_group(self, username, group_name):
        if group_name == "Général": return False, "Action interdite."
        self.groups.update_one({"_id": group_name}, {"$pull": {"members": username}})
        self.users.update_one({"_id": username}, {"$pull": {"groups": group_name}})
        return True, "Groupe quitté."

if __name__ == "__main__":
    manager = MongoManager()
    print("\n".join(manager.get_full_stats_as_lines()))

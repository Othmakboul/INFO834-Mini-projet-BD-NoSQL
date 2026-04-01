from database import get_mongo_db
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class MongoManager:
    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db["messages"]  # Pour la rétrocompatibilité ou usage général
        self.users = self.db["users"]
        self.groups = self.db["groups"]

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

    def register_or_login(self, username, password):
        """Vérifie le mot de passe s'il existe, ou créé le compte sinon."""
        try:
            user = self.users.find_one({"_id": username})
            if user:
                # Utilisateur existe, on vérifie le mot de passe
                stored_password = user.get("password")
                if not stored_password:
                    # Cas des anciens utilisateurs sans mot de passe
                    hashed = generate_password_hash(password)
                    self.users.update_one({"_id": username}, {"$set": {"password": hashed}})
                    return True, "Mot de passe configuré."
                
                if check_password_hash(stored_password, password):
                    return True, "Connexion réussie."
                else:
                    return False, "Mot de passe incorrect."
            else:
                # Création du compte
                hashed = generate_password_hash(password)
                self.users.insert_one({
                    "_id": username,
                    "password": hashed,
                    "contacts": [],
                    "groups": ["Général"],
                    "bio": "Salut ! J'utilise ChatPro."
                })
                return True, "Compte créé avec succès."
        except Exception as e:
            print(f"❌ Erreur Mongo (auth) : {e}")
            return False, "Erreur interne serveur."

    def get_user_info(self, username):
        """Récupère les informations publiques d'un utilisateur."""
        try:
            user = self.users.find_one({"_id": username})
            if user:
                return {
                    "username": user["_id"],
                    "bio": user.get("bio", "Salut ! J'utilise ChatPro.")
                }
            return None
        except Exception as e:
            print(f"❌ Erreur Mongo (get_user_info) : {e}")
            return None

    def update_profile(self, username, bio):
        """Met à jour l'actu/bio de l'utilisateur."""
        try:
            self.users.update_one(
                {"_id": username},
                {"$set": {"bio": bio}}
            )
            return True, "Profil mis à jour."
        except Exception as e:
            print(f"❌ Erreur Mongo (update_profile) : {e}")
            return False, "Erreur interne."

    def add_contact(self, username, contact_username):
        """Ajoute un contact mutuellement s'il existe dans la DB."""
        try:
            # On vérifie si le contact existe vraiment en tant qu'utilisateur
            if not self.users.find_one({"_id": contact_username}):
                return False, "Cet utilisateur n'existe pas encore."
            
            # On empêche de s'ajouter soi-même
            if username == contact_username:
                return False, "Vous ne pouvez pas vous ajouter vous-même."
            
            # Ajout de B chez A
            self.users.update_one(
                {"_id": username},
                {"$addToSet": {"contacts": contact_username}}
            )
            # Ajout de A chez B (mutuel)
            self.users.update_one(
                {"_id": contact_username},
                {"$addToSet": {"contacts": username}}
            )
            return True, "Contact ajouté avec succès (mutuellement)."
        except Exception as e:
            print(f"❌ Erreur Mongo (add_contact) : {e}")
            return False, "Erreur interne."

    def create_group(self, name, creator, members):
        """Créé un groupe et met à jour les profils des membres."""
        try:
            if self.groups.find_one({"_id": name}):
                return False, "Un groupe avec ce nom existe déjà."
            
            # Liste unique incluant le créateur
            all_members = list(set([creator] + members))
            self.groups.insert_one({
                "_id": name,
                "creator": creator,
                "members": all_members,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            })
            
            # Ajouter ce groupe à la liste de chaque membre
            for member in all_members:
                self.users.update_one(
                    {"_id": member},
                    {"$addToSet": {"groups": name}}
                )
                
            return True, "Groupe créé !"
        except Exception as e:
            print(f"❌ Erreur Mongo (create_group) : {e}")
            return False, "Erreur interne."

    def get_group_info(self, group_name):
        """Récupère le créateur et les membres du groupe."""
        try:
            if group_name == "Général":
                return {"_id": "Général", "creator": "Système", "members": []}
            return self.groups.find_one({"_id": group_name})
        except Exception as e:
            print(f"❌ Erreur Mongo (get_group_info) : {e}")
            return None

    def add_group_members(self, admin, group_name, new_members):
        """L'admin ajoute de nouveaux membres."""
        try:
            group = self.groups.find_one({"_id": group_name})
            if not group or group.get("creator") != admin:
                return False, "Action non autorisée ou groupe inexistant."
            
            # Filtrer les membres valides
            valid_users = list(self.users.find({"_id": {"$in": new_members}}))
            valid_usernames = [u["_id"] for u in valid_users]
            
            if not valid_usernames:
                return False, "Aucun nom valide."

            self.groups.update_one(
                {"_id": group_name},
                {"$addToSet": {"members": {"$each": valid_usernames}}}
            )
            self.users.update_many(
                {"_id": {"$in": valid_usernames}},
                {"$addToSet": {"groups": group_name}}
            )
            return True, "Membres ajoutés avec succès.", valid_usernames
        except Exception as e:
            print(f"❌ Erreur Mongo (add_group_members): {e}")
            return False, "Erreur interne.", []

    def kick_group_member(self, admin, group_name, target):
        """L'admin exclut un membre."""
        try:
            group = self.groups.find_one({"_id": group_name})
            if not group or group.get("creator") != admin:
                return False, "Action non autorisée ou groupe inexistant."
            
            if target == admin:
                return False, "Impossible de s'exclure soi-même."
            
            if target not in group.get("members", []):
                return False, "Ce membre n'est pas dans le groupe."

            self.groups.update_one({"_id": group_name}, {"$pull": {"members": target}})
            self.users.update_one({"_id": target}, {"$pull": {"groups": group_name}})
            return True, f"{target} a été exclu avec succès."
        except Exception as e:
            print(f"❌ Erreur Mongo (kick_group_member): {e}")
            return False, "Erreur interne."

    def get_user_conversations(self, username):
        """Retourne la liste des contacts et groupes de l'utilisateur."""
        try:
            user = self.users.find_one({"_id": username})
            if not user:
                return {"contacts": [], "groups": []}
            return {
                "contacts": user.get("contacts", []),
                "groups": user.get("groups", ["Général"])
            }
        except Exception as e:
            print(f"❌ Erreur Mongo (conversations) : {e}")
            return {"contacts": [], "groups": []}

    def search_users(self, prefix, limit=5):
        """Recherche des utilisateurs dont le pseudo commence par prefix."""
        try:
            # Regex insensible à la casse ^prefix
            query = {"_id": {"$regex": f"^{prefix}", "$options": "i"}}
            results = self.users.find(query).limit(limit)
            return [user["_id"] for user in results]
        except Exception as e:
            print(f"❌ Erreur Mongo (search_users) : {e}")
            return []

    def remove_contact(self, username, contact_username):
        """Supprime un contact de la liste de l'utilisateur."""
        try:
            self.users.update_one(
                {"_id": username},
                {"$pull": {"contacts": contact_username}}
            )
            return True, "Contact supprimé."
        except Exception as e:
            print(f"❌ Erreur Mongo (remove_contact) : {e}")
            return False, "Erreur interne."

    def leave_group(self, username, group_name):
        """Retire l'utilisateur du groupe et le groupe de sa liste."""
        try:
            if group_name == "Général":
                return False, "Impossible de quitter le salon Général."
            
            # Retirer le membre du groupe
            self.groups.update_one(
                {"_id": group_name},
                {"$pull": {"members": username}}
            )
            # Retirer le groupe du profil
            self.users.update_one(
                {"_id": username},
                {"$pull": {"groups": group_name}}
            )
            return True, f"Vous avez quitté {group_name}."
        except Exception as e:
            print(f"❌ Erreur Mongo (leave_group) : {e}")
            return False, "Erreur interne."
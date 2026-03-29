import socket
import threading
from database import get_redis_client
from mongodb_manager import MongoManager
import datetime

HOST = '127.0.0.1'
PORT = 5555

# Initialisation des outils NoSQL
mongo = MongoManager()
redis_c = get_redis_client()
clients_connectes = {}

def diffuser_message(message_str, client_expediteur=None):
    """Envoie un message à tout le monde."""
    for client in clients_connectes:
        if client != client_expediteur:
            try:
                client.send(message_str.encode('utf-8'))
            except:
                client.close()

def gerer_client(client_socket, adresse):
    try:
        # 1. Connexion : On récupère le pseudo
        pseudo = client_socket.recv(1024).decode('utf-8')
        clients_connectes[client_socket] = pseudo

        # --- PARTIE REDIS : GESTION DES CONNECTÉS ET HISTORIQUE ---
        # On ajoute l'utilisateur au Set des connectés
        redis_c.sadd("online_users", pseudo)

        # On ajoute une trace dans l'historique (Liste)
        maintenant = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{maintenant}] Connexion de {pseudo}"
        redis_c.lpush("login_history", log_msg)

        print(f"[+] {pseudo} est en ligne (Set Redis mis à jour)")

        diffuser_message(f"--- {pseudo} a rejoint le tchat ---", client_socket)

        while True:
            message_brut = client_socket.recv(1024).decode('utf-8')
            if not message_brut: break

            # ---  COMMANDES SPÉCIALES REDIS ---
            if message_brut.strip() == '/users':
                # On récupère tous les membres du Set Redis
                membres = redis_c.smembers("online_users")
                liste_membres = ", ".join(membres) if membres else "Personne"
                reponse = f"\n[Serveur Redis] En ligne : {liste_membres}\n"
                client_socket.send(reponse.encode('utf-8'))
                continue
            elif message_brut.strip() == '/historique':
                # Récupère les 10 derniers événements de la Liste Redis
                logs = redis_c.lrange("login_history", 0, 9)
                texte_logs = "\n".join(logs) if logs else "Aucun historique."
                reponse = f"\n[Serveur Redis] --- 10 derniers logs ---\n{texte_logs}\n"
                client_socket.send(reponse.encode('utf-8'))
                continue

            # --- PARTIE MONGODB ---
            # On stocke CHAQUE message dans MongoDB
            mongo.save_message(sender=pseudo, receiver="GLOBAL", content=message_brut)

            # Affichage et diffusion
            message_formate = f"{pseudo}: {message_brut}"
            print(message_formate)
            diffuser_message(message_formate, client_socket)

    except Exception as e:
        print(f"Erreur avec {adresse}: {e}")
    finally:
        if client_socket in clients_connectes:
            pseudo_deco = clients_connectes[client_socket]
            # --- PARTIE REDIS : DÉCONNEXION ---
            # On supprime l'utilisateur du Set Redis quand il part
            redis_c.srem("online_users", pseudo_deco)

            # On trace la déconnexion dans l'historique
            maintenant = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            redis_c.lpush("login_history", f"[{maintenant}] Déconnexion de {pseudo_deco}")

            del clients_connectes[client_socket]
            client_socket.close()
            diffuser_message(f"--- {pseudo_deco} a quitté le tchat ---")

def demarrer_serveur():
    serveur = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveur.bind((HOST, PORT))
    serveur.listen()
    print(f"[*] Serveur actif avec MongoDB ReplicaSet et Redis.")

    while True:
        client_socket, adresse = serveur.accept()
        thread = threading.Thread(target=gerer_client, args=(client_socket, adresse))
        thread.start()

if __name__ == "__main__":
    demarrer_serveur()
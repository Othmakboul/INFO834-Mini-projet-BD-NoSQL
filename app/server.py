import socket
import threading
from database import get_redis_client
from mongodb_manager import MongoManager

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
        
        # --- PARTIE REDIS ---
        # On enregistre l'utilisateur comme "En ligne"
        redis_c.set(f"user:{pseudo}", "online")
        print(f"[+] {pseudo} est en ligne (enregistré dans Redis)")

        diffuser_message(f"--- {pseudo} a rejoint le tchat ---", client_socket)

        while True:
            message_brut = client_socket.recv(1024).decode('utf-8')
            if not message_brut: break

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
            # --- PARTIE REDIS ---
            # On supprime l'utilisateur de Redis quand il part
            redis_c.delete(f"user:{pseudo_deco}")
            
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
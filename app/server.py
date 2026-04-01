import socket
import threading
from database import get_redis_client
from mongodb_manager import MongoManager

HOST = '127.0.0.1'
PORT = 5555

# --- INITIALISATION ---
clients_connectes = {}
redis_client = get_redis_client()
mongo_manager = MongoManager()

def diffuser_message(message, client_expediteur=None):
    """Envoie un message à tous les clients, sauf à l'expéditeur."""
    # list() permet de figer les clés pendant l'itération pour éviter les erreurs
    for client in list(clients_connectes.keys()):
        if client != client_expediteur:
            try:
                client.send(message) # Correction: on envoie le message directement
            except:
                client.close()
                if client in clients_connectes:
                    del clients_connectes[client]

def gerer_client(client_socket, adresse):
    """Gère la connexion d'un client spécifique (tourne dans un Thread)."""
    pseudo = None
    try:
        # 1. Connexion : On récupère le pseudo
        pseudo = client_socket.recv(1024).decode('utf-8')
        clients_connectes[client_socket] = pseudo
        
        # --- REDIS : Marquer l'utilisateur en ligne ---
        redis_client.set(pseudo, "en ligne")
        
        print(f"[+] {pseudo} s'est connecté depuis {adresse}")
        diffuser_message(f"--- {pseudo} a rejoint le tchat ---".encode('utf-8'), client_socket)

        while True:
            message_brut = client_socket.recv(1024)
            if message_brut:
                texte_message = message_brut.decode('utf-8')
                
                # --- MONGODB : Sauvegarder dans l'historique ---
                mongo_manager.save_message(sender=pseudo, receiver="Tous", content=texte_message)
                
                message_formate = f"{pseudo}: {texte_message}".encode('utf-8')
                print(message_formate.decode('utf-8')) 
                diffuser_message(message_formate, client_socket)
            else:
                break
                
    except Exception as e:
        print(f"Erreur avec {adresse}: {e}")
    finally:
        if client_socket in clients_connectes:
            pseudo_deco = clients_connectes[client_socket]
            print(f"[-] {pseudo_deco} s'est déconnecté.")
            
            # --- REDIS : Nettoyer la déconnexion ---
            if pseudo:
                redis_client.delete(pseudo)
                
            del clients_connectes[client_socket]
            client_socket.close()
            # Correction: ajout de .encode('utf-8') pour l'envoi via socket
            diffuser_message(f"--- {pseudo_deco} a quitté le tchat ---".encode('utf-8'))

def demarrer_serveur():
    serveur = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveur.bind((HOST, PORT))
    serveur.listen()
    print(f"[*] Serveur actif avec MongoDB ReplicaSet et Redis sur {HOST}:{PORT}")

    while True:
        client_socket, adresse = serveur.accept()
        thread = threading.Thread(target=gerer_client, args=(client_socket, adresse))
        thread.start()

if __name__ == "__main__":
    demarrer_serveur()
import socket
import threading
from database import get_redis_client
from mongodb_manager import MongoManager

HOST = '127.0.0.1'
PORT = 5555

# TTL en secondes pour les clés Redis (renouvellé à chaque message)
REDIS_TTL = 300

clients_connectes = {}  # socket -> pseudo
redis_client = get_redis_client()
mongo_manager = MongoManager()
lock = threading.Lock()


def diffuser_message(message, client_expediteur=None):
    """Envoie un message à tous les clients connectés, sauf à l'expéditeur."""
    with lock:
        destinataires = list(clients_connectes.keys())
    for client in destinataires:
        if client != client_expediteur:
            try:
                client.send(message)
            except:
                client.close()
                with lock:
                    clients_connectes.pop(client, None)


def envoyer_message_prive(message, pseudo_destinataire, client_expediteur):
    """Envoie un message privé à un utilisateur spécifique."""
    with lock:
        socket_destinataire = next(
            (sock for sock, pseudo in clients_connectes.items() if pseudo == pseudo_destinataire),
            None
        )
    if socket_destinataire:
        try:
            socket_destinataire.send(message)
            return True
        except:
            pass
    return False


def get_liste_connectes():
    """Retourne la liste des pseudos connectés depuis Redis."""
    pseudos = redis_client.keys("user:*")
    return [p.replace("user:", "") for p in pseudos]


def gerer_client(client_socket, adresse):
    """Gère la connexion d'un client spécifique (tourne dans un Thread)."""
    pseudo = None
    try:
        # 1. Récupération du pseudo
        pseudo = client_socket.recv(1024).decode('utf-8').strip()
        with lock:
            clients_connectes[client_socket] = pseudo

        # --- REDIS : Marquer l'utilisateur en ligne avec TTL ---
        redis_client.set(f"user:{pseudo}", "en ligne", ex=REDIS_TTL)

        print(f"[+] {pseudo} s'est connecté depuis {adresse}")
        diffuser_message(f"--- {pseudo} a rejoint le tchat ---".encode('utf-8'), client_socket)

        while True:
            message_brut = client_socket.recv(1024)
            if not message_brut:
                break

            texte = message_brut.decode('utf-8').strip()

            # Renouveler le TTL Redis à chaque activité
            redis_client.expire(f"user:{pseudo}", REDIS_TTL)

            # --- Commande : /liste ---
            if texte == "/liste":
                connectes = get_liste_connectes()
                reponse = "Connectés : " + ", ".join(connectes) if connectes else "Aucun utilisateur connecté."
                client_socket.send(reponse.encode('utf-8'))

            # --- Commande : /stats ---
            elif texte == "/stats":
                try:
                    lines = mongo_manager.get_full_stats()
                    reponse = "\n".join(lines)
                except Exception as e:
                    reponse = f"Erreur MongoDB : {e}"
                client_socket.send(reponse.encode('utf-8'))

            # --- Commande : /historique <user> ---
            elif texte.startswith("/historique "):
                autre_user = texte[len("/historique "):].strip()
                try:
                    conversation = mongo_manager.get_conversation(pseudo, autre_user)
                    reponse = "\n".join(conversation) if conversation else f"Aucune conversation trouvée avec {autre_user}."
                except Exception as e:
                    reponse = f"Erreur MongoDB : {e}"
                client_socket.send(reponse.encode('utf-8'))

            # --- Commande : /search <mot-clé> ---
            elif texte.startswith("/search "):
                keyword = texte[len("/search "):].strip()
                try:
                    resultats = mongo_manager.search_by_keyword(keyword)
                    reponse = "\n".join(resultats) if resultats else f"Aucun message contenant '{keyword}'."
                except Exception as e:
                    reponse = f"Erreur MongoDB : {e}"
                client_socket.send(reponse.encode('utf-8'))

            # --- Commande : /plage <HH:MM> <HH:MM> ---
            elif texte.startswith("/plage "):
                parties = texte[len("/plage "):].strip().split()
                if len(parties) == 2:
                    try:
                        resultats = mongo_manager.search_by_time_range(parties[0], parties[1])
                        reponse = "\n".join(resultats) if resultats else f"Aucun message entre {parties[0]} et {parties[1]}."
                    except Exception as e:
                        reponse = f"Erreur : {e}"
                else:
                    reponse = "Usage: /plage HH:MM HH:MM"
                client_socket.send(reponse.encode('utf-8'))

            # --- Commande : /msg <pseudo> <message> ---
            elif texte.startswith("/msg "):
                parties = texte[5:].split(" ", 1)
                if len(parties) == 2:
                    destinataire, contenu = parties
                    try:
                        mongo_manager.save_message(sender=pseudo, receiver=destinataire, content=contenu)
                    except Exception as e:
                        print(f"[WARN] MongoDB save_message échoué: {e}")
                    msg_prive = f"[Privé] {pseudo} -> {destinataire}: {contenu}".encode('utf-8')
                    succes = envoyer_message_prive(msg_prive, destinataire, client_socket)
                    if succes:
                        client_socket.send(f"[Privé envoyé à {destinataire}]: {contenu}".encode('utf-8'))
                    else:
                        client_socket.send(f"Utilisateur '{destinataire}' introuvable ou déconnecté.".encode('utf-8'))
                else:
                    client_socket.send("Usage: /msg <pseudo> <message>".encode('utf-8'))

            # --- Message public ---
            else:
                try:
                    mongo_manager.save_message(sender=pseudo, receiver="Tous", content=texte)
                except Exception as e:
                    print(f"[WARN] MongoDB save_message échoué: {e}")
                message_formate = f"{pseudo}: {texte}".encode('utf-8')
                print(message_formate.decode('utf-8'))
                diffuser_message(message_formate, client_socket)

    except Exception as e:
        print(f"Erreur avec {adresse}: {e}")
    finally:
        with lock:
            pseudo_deco = clients_connectes.pop(client_socket, pseudo)
        client_socket.close()

        if pseudo_deco:
            redis_client.delete(f"user:{pseudo_deco}")
            print(f"[-] {pseudo_deco} s'est déconnecté.")
            diffuser_message(f"--- {pseudo_deco} a quitté le tchat ---".encode('utf-8'))


def demarrer_serveur():
    serveur = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveur.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serveur.bind((HOST, PORT))
    serveur.listen()
    print(f"[*] Serveur actif avec MongoDB ReplicaSet et Redis sur {HOST}:{PORT}")
    print("[*] Commandes disponibles : /liste | /msg <pseudo> <msg> | /historique <pseudo>")

    while True:
        client_socket, adresse = serveur.accept()
        thread = threading.Thread(target=gerer_client, args=(client_socket, adresse))
        thread.daemon = True
        thread.start()


if __name__ == "__main__":
    demarrer_serveur()

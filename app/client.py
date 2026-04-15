import socket
import threading
import sys

HOST = '127.0.0.1'
PORT = 5555


def recevoir_messages(client_socket):
    """Écoute les messages venant du serveur (tourne dans un Thread)."""
    while True:
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if message:
                print(f"\n{message}")
            else:
                print("Connexion au serveur perdue.")
                client_socket.close()
                sys.exit()
        except Exception as e:
            print(f"Erreur de réception: {e}")
            client_socket.close()
            sys.exit()


def afficher_aide():
    print("\n--- Commandes disponibles ---")
    print("  /liste                      : Utilisateurs connectés (Redis)")
    print("  /msg <pseudo> <msg>         : Envoyer un message privé")
    print("  /historique <pseudo>        : Conversation avec un utilisateur (MongoDB)")
    print("  /stats                      : Top expéditeurs + plus sollicités (MongoDB)")
    print("  /search <mot>               : Rechercher un mot-clé dans les messages")
    print("  /plage <HH:MM> <HH:MM>     : Messages dans une plage horaire")
    print("  quitter                     : Se déconnecter")
    print("-----------------------------\n")


def demarrer_client():
    pseudo = input("Entrez votre pseudo pour rejoindre le tchat: ").strip()
    if not pseudo:
        print("Pseudo invalide.")
        sys.exit()

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((HOST, PORT))
    except Exception as e:
        print(f"Impossible de se connecter au serveur : {e}")
        sys.exit()

    client_socket.send(pseudo.encode('utf-8'))
    print("Connecté au serveur de tchat !")
    afficher_aide()

    thread_reception = threading.Thread(target=recevoir_messages, args=(client_socket,), daemon=True)
    thread_reception.start()

    while True:
        try:
            message = input()
            if message.lower() == 'quitter':
                client_socket.close()
                sys.exit()
            elif message == '/aide':
                afficher_aide()
            elif message.strip():
                client_socket.send(message.encode('utf-8'))
        except (KeyboardInterrupt, EOFError):
            print("\nDéconnexion.")
            client_socket.close()
            sys.exit()
        except Exception as e:
            print(f"Erreur d'envoi : {e}")
            client_socket.close()
            sys.exit()


if __name__ == "__main__":
    demarrer_client()

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
                break
        except Exception as e:
            print(f"Erreur de réception: {e}")
            client_socket.close()
            break

def demarrer_client():
    pseudo = input("Entrez votre pseudo pour rejoindre le tchat: ")

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        client_socket.connect((HOST, PORT))
    except Exception as e:
        print(f"Impossible de se connecter au serveur : {e}")
        sys.exit()

    client_socket.send(pseudo.encode('utf-8'))
    print("Connecté au serveur de tchat ! Vous pouvez écrire vos messages.")

    thread_reception = threading.Thread(target=recevoir_messages, args=(client_socket,))
    thread_reception.start()

    while True:
        try:
            message = input()
            if message.lower() == 'quitter':
                client_socket.close()
                break
            client_socket.send(message.encode('utf-8'))
        except:
            print("Erreur d'envoi. Fermeture de l'application.")
            client_socket.close()
            break

if __name__ == "__main__":
    demarrer_client()
import socket
import threading

HOST = '127.0.0.1' 
PORT = 5555        

clients_connectes = {}

def diffuser_message(message, client_expediteur=None):
    """Envoie un message à tous les clients, sauf bien sur à l'expéditeur."""
    for client in clients_connectes:
        if client != client_expediteur:
            try:
                client.send(message)
            except:
                client.close()
                del clients_connectes[client]

def gerer_client(client_socket, adresse):
    """Gère la connexion d'un client spécifique (tourne dans un Thread)."""
    try:
        pseudo = client_socket.recv(1024).decode('utf-8')
        clients_connectes[client_socket] = pseudo
        
        print(f"[+] {pseudo} s'est connecté depuis {adresse}")
        diffuser_message(f"--- {pseudo} a rejoint le tchat ---".encode('utf-8'), client_socket)

        while True:
            message = client_socket.recv(1024)
            if message:
                message_formate = f"{pseudo}: {message.decode('utf-8')}".encode('utf-8')
                print(message_formate.decode('utf-8')) 
                diffuser_message(message_formate, client_socket)
            else:
                break
                
    except Exception as e:
        print(f"Erreur avec le client {adresse}: {e}")
    finally:
        if client_socket in clients_connectes:
            pseudo_deco = clients_connectes[client_socket]
            print(f"[-] {pseudo_deco} s'est déconnecté.")
            del clients_connectes[client_socket]
            client_socket.close()
            diffuser_message(f"--- {pseudo_deco} a quitté le tchat ---".encode('utf-8'))

def demarrer_serveur():
    """Démarre le serveur et écoute les nouvelles connexions."""
    serveur = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveur.bind((HOST, PORT))
    serveur.listen()
    print(f"[*] Serveur de Tchat en écoute sur {HOST}:{PORT}")

    while True:
        client_socket, adresse = serveur.accept()
        
        # On crée un processus (Thread) parallèle pour gérer ce client sans bloquer les autres
        thread = threading.Thread(target=gerer_client, args=(client_socket, adresse))
        thread.start()

if __name__ == "__main__":
    demarrer_serveur()
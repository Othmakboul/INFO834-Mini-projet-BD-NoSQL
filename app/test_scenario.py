"""
Scénario de test automatisé — teste toutes les commandes du tchat.
Lance le serveur AVANT d'exécuter ce script.
"""
import socket
import threading
import time
import sys

HOST = '127.0.0.1'
PORT = 5555

reponses = {}  # pseudo -> liste de messages reçus
verrous   = {}  # pseudo -> threading.Event (signal de réception)

SEPARATEUR = "=" * 55


def log(pseudo, tag, texte):
    couleurs = {"alice": "\033[94m", "bob": "\033[92m", "zak": "\033[93m"}
    reset = "\033[0m"
    c = couleurs.get(pseudo, "")
    print(f"{c}[{pseudo.upper():>5}] [{tag}] {texte}{reset}")


class ClientTest:
    def __init__(self, pseudo):
        self.pseudo = pseudo
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        reponses[pseudo] = []
        verrous[pseudo] = threading.Event()

    def connecter(self):
        self.sock.connect((HOST, PORT))
        self.sock.send(self.pseudo.encode('utf-8'))
        t = threading.Thread(target=self._ecouter, daemon=True)
        t.start()
        time.sleep(0.3)  # laisser le serveur enregistrer la connexion

    def _ecouter(self):
        while True:
            try:
                data = self.sock.recv(4096).decode('utf-8')
                if data:
                    reponses[self.pseudo].append(data)
                    verrous[self.pseudo].set()
                    log(self.pseudo, "RECU", data)
            except:
                break

    def envoyer(self, message, attendre_reponse=True, timeout=3):
        log(self.pseudo, "ENVOI", message)
        verrous[self.pseudo].clear()
        self.sock.send(message.encode('utf-8'))
        if attendre_reponse:
            verrous[self.pseudo].wait(timeout=timeout)
        time.sleep(0.3)

    def deconnecter(self):
        try:
            self.sock.close()
        except:
            pass
        log(self.pseudo, "INFO", "Déconnecté.")


def titre(texte):
    print(f"\n{SEPARATEUR}")
    print(f"  TEST : {texte}")
    print(SEPARATEUR)


def verifier_connexion():
    """Vérifie que le serveur est accessible avant de lancer les tests."""
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect((HOST, PORT))
        s.close()
        return True
    except:
        return False


# ==============================================================
# SCÉNARIO PRINCIPAL
# ==============================================================

def run():
    print(f"\n{'#'*55}")
    print("   SCÉNARIO DE TEST — Tchat Redis/MongoDB")
    print(f"{'#'*55}\n")

    if not verifier_connexion():
        print("ERREUR : Le serveur n'est pas lancé.")
        print("Lancez d'abord : python server.py")
        sys.exit(1)

    alice = ClientTest("alice")
    bob   = ClientTest("bob")
    zak   = ClientTest("zak")

    # ----------------------------------------------------------
    titre("1. Connexion de 3 utilisateurs")
    # ----------------------------------------------------------
    alice.connecter()
    time.sleep(0.2)
    bob.connecter()
    time.sleep(0.2)
    zak.connecter()
    time.sleep(0.5)
    print("  => alice, bob et zak connectés.")

    # ----------------------------------------------------------
    titre("2. /liste — utilisateurs connectés (Redis)")
    # ----------------------------------------------------------
    alice.envoyer("/liste")

    # ----------------------------------------------------------
    titre("3. Messages publics (sauvegardés dans MongoDB)")
    # ----------------------------------------------------------
    alice.envoyer("Bonjour tout le monde !", attendre_reponse=False)
    time.sleep(0.2)
    bob.envoyer("Salut alice !", attendre_reponse=False)
    time.sleep(0.2)
    zak.envoyer("Hello les amis !", attendre_reponse=False)
    time.sleep(0.5)

    # ----------------------------------------------------------
    titre("4. /msg — messages privés")
    # ----------------------------------------------------------
    alice.envoyer("/msg bob Coucou bob, message privé !")
    time.sleep(0.3)
    bob.envoyer("/msg alice Reçu alice, bonne continuation !")
    time.sleep(0.3)
    alice.envoyer("/msg zak Salut zak, tu vas bien ?")
    time.sleep(0.3)

    # ----------------------------------------------------------
    titre("5. /historique — conversation entre alice et bob")
    # ----------------------------------------------------------
    alice.envoyer("/historique bob")

    # ----------------------------------------------------------
    titre("6. /stats — top expéditeurs + plus sollicités")
    # ----------------------------------------------------------
    alice.envoyer("/stats")

    # ----------------------------------------------------------
    titre("7. /search — recherche par mot-clé")
    # ----------------------------------------------------------
    alice.envoyer("/search bonjour")
    time.sleep(0.3)
    bob.envoyer("/search privé")

    # ----------------------------------------------------------
    titre("8. /plage — messages sur une plage horaire")
    # ----------------------------------------------------------
    # On prend 00:00 -> 23:59 pour être sûr de tout capturer
    alice.envoyer("/plage 00:00 23:59")

    # ----------------------------------------------------------
    titre("9. Commande inconnue — doit être traitée comme message public")
    # ----------------------------------------------------------
    bob.envoyer("/inconnu test", attendre_reponse=False)
    time.sleep(0.3)

    # ----------------------------------------------------------
    titre("10. Déconnexion")
    # ----------------------------------------------------------
    alice.deconnecter()
    time.sleep(0.2)
    bob.deconnecter()
    time.sleep(0.2)
    zak.deconnecter()
    time.sleep(0.5)

    # ----------------------------------------------------------
    # BILAN
    # ----------------------------------------------------------
    print(f"\n{'#'*55}")
    print("   BILAN DES MESSAGES REÇUS PAR CLIENT")
    print(f"{'#'*55}")
    for pseudo, msgs in reponses.items():
        print(f"\n  [{pseudo.upper()}] — {len(msgs)} message(s) reçu(s)")
        for m in msgs:
            print(f"    • {m[:100]}")

    print(f"\n{'='*55}")
    print("  Scénario terminé. Vérifiez MongoDB avec :")
    print("  docker exec -it mongo_primary mongosh tchat_app \\")
    print('    --eval "db.messages.find().pretty()"')
    print(f"{'='*55}\n")


if __name__ == "__main__":
    run()

import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from database import get_redis_client
from mongodb_manager import MongoManager
import datetime
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_zak_pro'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

mongo = MongoManager()
redis_c = get_redis_client()

# --- FILTRE PERSONNALISÉ POUR LES AVATARS ---
@app.template_filter('colorfor')
def colorfor_filter(s):
    """Génère une couleur HSL unique pour chaque pseudo"""
    if not s:
        return "hsl(220, 50%, 50%)"
    # Création d'un hash à partir du nom
    hash_object = hashlib.md5(s.encode('utf-8'))
    hash_hex = hash_object.hexdigest()
    # Calcul de la teinte (0-360)
    hue = int(hash_hex[:4], 16) % 360
    return f"hsl({hue}, 60%, 50%)"

@app.route('/')
def index():
    try:
        # On récupère l'historique
        history_list = list(mongo.collection.find().sort("timestamp", 1).limit(50))
    except Exception as e:
        print(f"Erreur Mongo: {e}")
        history_list = []
    return render_template('chat_pro.html', history=history_list)

@socketio.on('connect_user')
def handle_connect(data):
    username = data.get('username')
    if username:
        # Enregistrement Redis
        redis_c.set(f"user:{username}", "online")
        # Mise à jour de la liste pour tout le monde
        emit('status_update', {'users': get_online_users()}, broadcast=True)
        print(f"DEBUG: {username} connecté")

@socketio.on('send_message')
def handle_message(data):
    user = data.get('username')
    msg = data.get('message')
    if user and msg:
        # Sauvegarde MongoDB
        mongo.save_message(user, "GLOBAL", msg)
        now = datetime.datetime.now().strftime("%H:%M")
        # Envoi en temps réel
        emit('new_msg', {
            'username': user, 
            'message': msg, 
            'time': now
        }, broadcast=True)

def get_online_users():
    keys = redis_c.keys("user:*")
    return [k.split(":")[1] for k in keys]

if __name__ == "__main__":
    # Port 5001 car le 5000 est bloqué par AirPlay sur Mac
    print("🚀 Serveur lancé sur http://127.0.0.1:5001")
    socketio.run(app, debug=True, port=5001)
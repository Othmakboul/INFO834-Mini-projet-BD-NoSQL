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
    salons = ['Général', 'Projets', 'Cafète', 'Développement']
    try:
        # Historique par défaut (Général)
        history_list = mongo.get_room_history("Général")
        for m in history_list: m['timestamp'] = m['timestamp'].strftime("%H:%M")
    except Exception as e:
        print(f"Erreur Mongo initial: {e}")
        history_list = []
    return render_template('chat_pro.html', history=history_list, salons=salons)

@socketio.on('connect_user')
def handle_connect(data):
    username = data.get('username')
    if username:
        # Enregistrement Redis : status et SID pour les MP
        redis_c.set(f"user:{username}", "online")
        redis_c.set(f"sid:{username}", request.sid)
        
        # Par défaut, on rejoint le salon Général
        join_room('Général')
        
        # Mise à jour de la liste pour tout le monde
        emit('status_update', {'users': get_online_users()}, broadcast=True)
        print(f"DEBUG: {username} connecté (sid: {request.sid})")

@socketio.on('disconnect')
def handle_disconnect():
    # On cherche l'utilisateur par son SID dans Redis (ou via session)
    keys = redis_c.keys("sid:*")
    for key in keys:
        if redis_c.get(key) == request.sid:
            username = key.split(":")[1]
            redis_c.delete(f"user:{username}")
            redis_c.delete(f"sid:{username}")
            emit('status_update', {'users': get_online_users()}, broadcast=True)
            print(f"DEBUG: {username} déconnecté")
            break

@socketio.on('join_room')
def on_join(data):
    username = data.get('username')
    room = data.get('room', 'Général')
    join_room(room)
    # On renvoie l'historique du salon
    history = mongo.get_room_history(room)
    # Conversion des timestamps pour JSON
    for m in history: m['_id'] = str(m['_id']); m['timestamp'] = m['timestamp'].strftime("%H:%M")
    emit('room_history', {'room': room, 'history': history})

@socketio.on('send_message')
def handle_message(data):
    user = data.get('username')
    msg = data.get('message')
    room = data.get('room', 'Général')
    is_private = data.get('is_private', False)
    target = data.get('target') # Username cible si PM

    if user and msg:
        now = datetime.datetime.now().strftime("%H:%M")
        
        if is_private and target:
            # Salon unique pour les MP (trié pour être consistant)
            room_id = f"pm:{min(user, target)}:{max(user, target)}"
            mongo.save_message(user, target, msg, room=room_id)
            
            # Envoi au destinataire via son SID
            target_sid = redis_c.get(f"sid:{target}")
            payload = {'username': user, 'message': msg, 'time': now, 'room': room_id, 'is_private': True}
            
            if target_sid:
                emit('new_msg', payload, room=target_sid)
            # Envoi à soi-même (si on a plusieurs onglets ou juste pour confirmation)
            emit('new_msg', payload, room=request.sid)
        else:
            # Salon public
            mongo.save_message(user, "GLOBAL", msg, room=room)
            emit('new_msg', {
                'username': user, 
                'message': msg, 
                'time': now,
                'room': room
            }, room=room)

@socketio.on('typing')
def handle_typing(data):
    emit('display_typing', data, room=data.get('room'), include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    emit('hide_typing', data, room=data.get('room'), include_self=False)

def get_online_users():
    keys = redis_c.keys("user:*")
    return sorted([k.split(":")[1] for k in keys])

if __name__ == "__main__":
    # Port 5001 car le 5000 est bloqué par AirPlay sur Mac
    print("🚀 Serveur lancé sur http://127.0.0.1:5001")
    socketio.run(app, debug=True, port=5001)
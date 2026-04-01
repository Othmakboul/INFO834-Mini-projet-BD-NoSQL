from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from database import get_redis_client
from mongodb_manager import MongoManager
import datetime
import hashlib
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_zak_pro'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

mongo = MongoManager()
redis_c = get_redis_client()

# --- REDIS PUB/SUB ---
def ecouter_redis_pour_web():
    """Écoute Redis et envoie les messages au Web via Socket.IO"""
    pubsub = redis_c.pubsub()
    pubsub.subscribe('chat_room:Général')
    print("[*] Web Chat écoute sur le canal Redis 'chat_room:Général'")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            data = message['data']
            # On ne traite que les messages venant du serveur TCP
            if data.startswith('[TCP]'):
                msg_content_raw = data.replace('[TCP] ', '')
                if ": " in msg_content_raw:
                    parts = msg_content_raw.split(": ", 1)
                    username = parts[0]
                    msg_content = parts[1]
                    
                    # On émet vers tout le monde sur le site web
                    now = datetime.datetime.now().strftime("%H:%M")
                    socketio.emit('new_msg', {
                        'username': username,
                        'message': msg_content,
                        'time': now,
                        'room': 'Général'
                    }, room='Général')

# Lancement du thread de fond
threading.Thread(target=ecouter_redis_pour_web, daemon=True).start()

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
    password = data.get('password')
    if username and password:
        # Enregistrer l'utilisateur (créé le profil si 1ère fois, ou vérifie Mdp)
        success, msg = mongo.register_or_login(username, password)
        if not success:
            emit('login_result', {'success': False, 'message': msg})
            return

        # Enregistrement Redis : status et SID pour les MP
        redis_c.set(f"user:{username}", "online")
        redis_c.set(f"sid:{username}", request.sid)
        
        # Par défaut, on rejoint le salon Général et tous ses groupes
        join_room('Général')
        conversations = mongo.get_user_conversations(username)
        for group in conversations["groups"]:
            join_room(group)
        
        # On envoie au client ses conversations (contacts + groupes)
        emit('conversations_data', conversations, room=request.sid)
        emit('login_result', {'success': True, 'message': msg})

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
            payload = {'username': user, 'message': msg, 'time': now, 'room': room_id, 'is_private': True, 'target': target}
            
            if target_sid:
                emit('new_msg', payload, room=target_sid.decode('utf-8'))
            # Envoi à soi-même (si on a plusieurs onglets ou juste pour confirmation)
            emit('new_msg', payload, room=request.sid)
        else:
            # Salon public ou groupe
            mongo.save_message(user, "GLOBAL", msg, room=room)
            
            # --- SYNC AVEC LE SERVEUR TCP ---
            # Format: [WEB] [#SALON] Pseudo: Message
            message_formate = f"[WEB] [#{room}] {user}: {msg}"
            redis_c.publish('chat_room:Général', message_formate)

            emit('new_msg', {
                'username': user, 
                'message': msg, 
                'time': now,
                'room': room
            }, room=room)

@socketio.on('add_contact')
def handle_add_contact(data):
    user = data.get('username')
    contact = data.get('contact')
    success, msg = mongo.add_contact(user, contact)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        # On renvoie la liste à jour
        conversations = mongo.get_user_conversations(user)
        emit('conversations_data', conversations, room=request.sid)
        
        # Notifier l'autre utilisateur que 'user' l'a ajouté !
        target_sid = redis_c.get(f"sid:{contact}")
        if target_sid:
            target_sid = target_sid.decode('utf-8')
            target_convs = mongo.get_user_conversations(contact)
            emit('conversations_data', target_convs, room=target_sid)
            emit('notification', {'success': True, 'message': f"{user} vous a ajouté à ses contacts !"}, room=target_sid)

@socketio.on('get_profile')
def handle_get_profile(data):
    target = data.get('username')
    info = mongo.get_user_info(target)
    if info:
        emit('profile_data', info, room=request.sid)

@socketio.on('update_profile')
def handle_update_profile(data):
    user = data.get('username')
    bio = data.get('bio')
    success, msg = mongo.update_profile(user, bio)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)

@socketio.on('create_group')
def handle_create_group(data):
    creator = data.get('username')
    group_name = data.get('group_name')
    members = data.get('members', [])
    
    success, msg = mongo.create_group(group_name, creator, members)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    
    if success:
        join_room(group_name)
        all_members = list(set([creator] + members))
        # Notifier tous les membres pour qu'ils rejoignent le groupe
        # (Si connectés, on utilise Redis SID)
        for member in all_members:
            sid = redis_c.get(f"sid:{member}")
            if sid:
                # Rafraichir leurs conversations
                convs = mongo.get_user_conversations(member)
                emit('conversations_data', convs, room=sid)
                # Le client web devra envoyer un "join_room" explicite ou on le force :
                socketio.server.enter_room(sid, group_name, namespace='/')
                emit('new_msg', {
                    'username': "Système",
                    'message': f"Vous avez été ajouté au groupe {group_name}.",
                    'time': datetime.datetime.now().strftime("%H:%M"),
                    'room': group_name
                }, room=sid)

@socketio.on('search_users')
def handle_search_users(data):
    query = data.get('query', '')
    if len(query) >= 1:
        results = mongo.search_users(query)
        emit('search_results', {'results': results}, room=request.sid)

@socketio.on('remove_contact')
def handle_remove_contact(data):
    user = data.get('username')
    contact = data.get('contact')
    success, msg = mongo.remove_contact(user, contact)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        conversations = mongo.get_user_conversations(user)
        emit('conversations_data', conversations, room=request.sid)

@socketio.on('get_group_info')
def handle_get_group_info(data):
    group_name = data.get('group_name')
    info = mongo.get_group_info(group_name)
    if info:
        emit('group_info_data', info, room=request.sid)

@socketio.on('add_group_members')
def handle_add_group_members(data):
    admin = data.get('username')
    group_name = data.get('group_name')
    members = data.get('members', [])
    success, msg, added = mongo.add_group_members(admin, group_name, members)
    
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        # Rafraîchir l'admin
        emit('group_members_updated', {'group_name': group_name}, room=request.sid)
        
        # Envoyer notification système et ajouter les membres
        now = datetime.datetime.now().strftime("%H:%M")
        for m in added:
            sid = redis_c.get(f"sid:{m}")
            if sid:
                sid = sid.decode('utf-8')
                convs = mongo.get_user_conversations(m)
                emit('conversations_data', convs, room=sid)
                socketio.server.enter_room(sid, group_name, namespace='/')
                emit('new_msg', {
                    'username': "Système",
                    'message': f"{admin} vous a ajouté au groupe {group_name}.",
                    'time': now,
                    'room': group_name
                }, room=sid)
            # Annonce dans le salon
            emit('new_msg', {
                'username': "Système",
                'message': f"{m} a été ajouté au groupe par {admin}.",
                'time': now,
                'room': group_name
            }, room=group_name)

@socketio.on('kick_group_member')
def handle_kick_group_member(data):
    admin = data.get('username')
    group_name = data.get('group_name')
    target = data.get('target')
    
    success, msg = mongo.kick_group_member(admin, group_name, target)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    
    if success:
        # Mettre à jour la modale
        emit('group_members_updated', {'group_name': group_name}, room=request.sid)
        
        # Gérer la personne exclue
        now = datetime.datetime.now().strftime("%H:%M")
        target_sid = redis_c.get(f"sid:{target}")
        if target_sid:
            target_sid = target_sid.decode('utf-8')
            socketio.server.leave_room(target_sid, group_name, namespace='/')
            convs = mongo.get_user_conversations(target)
            emit('conversations_data', convs, room=target_sid)
            emit('kicked_from_group', {'group_name': group_name}, room=target_sid)
            emit('notification', {'success': False, 'message': f"Vous avez été exclu du groupe {group_name}."}, room=target_sid)
            
        emit('new_msg', {
            'username': "Système",
            'message': f"{target} a été exclu par l'administrateur.",
            'time': now,
            'room': group_name
        }, room=group_name)

@socketio.on('leave_group')
def handle_leave_group(data):
    user = data.get('username')
    group = data.get('group_name')
    success, msg = mongo.leave_group(user, group)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        leave_room(group)
        conversations = mongo.get_user_conversations(user)
        emit('conversations_data', conversations, room=request.sid)
        # Inform the group
        emit('new_msg', {
            'username': "Système",
            'message': f"{user} a quitté le groupe.",
            'time': datetime.datetime.now().strftime("%H:%M"),
            'room': group
        }, room=group)

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
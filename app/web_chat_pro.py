import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from database import get_redis_client
from mongodb_manager import MongoManager
import datetime
import hashlib
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_zak_pro'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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
            if isinstance(data, bytes):
                data = data.decode('utf-8')
                
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

# Lancement de la tâche de fond avec eventlet
eventlet.spawn(ecouter_redis_pour_web)

# --- FILTRE PERSONNALISÉ POUR LES AVATARS ---
@app.template_filter('colorfor')
def colorfor_filter(s):
    """Génère une couleur HSL unique pour chaque pseudo"""
    if not s:
        return "hsl(220, 50%, 50%)"
    hash_object = hashlib.md5(s.encode('utf-8'))
    hash_hex = hash_object.hexdigest()
    hue = int(hash_hex[:4], 16) % 360
    return f"hsl({hue}, 60%, 50%)"

@app.route('/')
def index():
    salons = ['Général', 'Projets', 'Cafète', 'Développement']
    try:
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
        success, msg = mongo.register_or_login(username, password)
        if not success:
            emit('login_result', {'success': False, 'message': msg})
            return

        redis_c.set(f"user:{username}", "online")
        redis_c.set(f"sid:{username}", request.sid)
        
        join_room('Général')
        conversations = mongo.get_user_conversations(username)
        for group in conversations["groups"]:
            join_room(group)
        
        emit('conversations_data', conversations, room=request.sid)
        emit('login_result', {'success': True, 'message': msg})
        emit('status_update', {'users': get_online_users()}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    keys = redis_c.keys("sid:*")
    for key in keys:
        if redis_c.get(key).decode('utf-8') == request.sid:
            username = key.decode('utf-8').split(":")[1]
            redis_c.delete(f"user:{username}")
            redis_c.delete(f"sid:{username}")
            emit('status_update', {'users': get_online_users()}, broadcast=True)
            break

@socketio.on('join_room')
def on_join(data):
    room = data.get('room', 'Général')
    join_room(room)
    history = mongo.get_room_history(room)
    for m in history: 
        m['_id'] = str(m['_id'])
        m['timestamp'] = m['timestamp'].strftime("%H:%M")
    emit('room_history', {'room': room, 'history': history})

@socketio.on('send_message')
def handle_message(data):
    user = data.get('username')
    msg = data.get('message')
    room = data.get('room', 'Général')
    is_private = data.get('is_private', False)
    target = data.get('target')

    if user and msg:
        now = datetime.datetime.now().strftime("%H:%M")
        if is_private and target:
            room_id = f"pm:{min(user, target)}:{max(user, target)}"
            mongo.save_message(user, target, msg, room=room_id)
            target_sid = redis_c.get(f"sid:{target}")
            payload = {'username': user, 'message': msg, 'time': now, 'room': room_id, 'is_private': True, 'target': target}
            if target_sid:
                emit('new_msg', payload, room=target_sid.decode('utf-8'))
            emit('new_msg', payload, room=request.sid)
        else:
            mongo.save_message(user, "GLOBAL", msg, room=room)
            redis_c.publish('chat_room:Général', f"[WEB] [#{room}] {user}: {msg}")
            emit('new_msg', {'username': user, 'message': msg, 'time': now, 'room': room}, room=room)

@socketio.on('add_contact')
def handle_add_contact(data):
    user = data.get('username')
    contact = data.get('contact')
    success, msg = mongo.add_contact(user, contact)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        emit('conversations_data', mongo.get_user_conversations(user), room=request.sid)
        target_sid = redis_c.get(f"sid:{contact}")
        if target_sid:
            sid_str = target_sid.decode('utf-8')
            emit('conversations_data', mongo.get_user_conversations(contact), room=sid_str)
            emit('notification', {'success': True, 'message': f"{user} vous a ajouté !"}, room=sid_str)

@socketio.on('get_profile')
def handle_get_profile(data):
    info = mongo.get_user_info(data.get('username'))
    if info: emit('profile_data', info, room=request.sid)

@socketio.on('update_profile')
def handle_update_profile(data):
    success, msg = mongo.update_profile(data.get('username'), data.get('bio'))
    emit('notification', {'success': success, 'message': msg}, room=request.sid)

@socketio.on('create_group')
def handle_create_group(data):
    creator = data.get('username')
    gn = data.get('group_name')
    mems = data.get('members', [])
    success, msg = mongo.create_group(gn, creator, mems)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        join_room(gn)
        for m in list(set([creator] + mems)):
            sid = redis_c.get(f"sid:{m}")
            if sid:
                sid_str = sid.decode('utf-8')
                emit('conversations_data', mongo.get_user_conversations(m), room=sid_str)
                socketio.server.enter_room(sid_str, gn, namespace='/')
                emit('new_msg', {'username': "Système", 'message': f"Groupe {gn} rejoint.", 'time': datetime.datetime.now().strftime("%H:%M"), 'room': gn}, room=sid_str)

@socketio.on('get_stats')
def handle_get_stats():
    try:
        top = mongo.get_top_senders()
        sol = mongo.get_most_solicited()
        tot = mongo.collection.count_documents({})
        emit('stats_data', {'top_senders': top, 'most_solicited': sol, 'total_messages': tot}, room=request.sid)
    except Exception as e:
        emit('notification', {'success': False, 'message': str(e)}, room=request.sid)

@socketio.on('search_messages')
def handle_search_messages(data):
    kw = data.get('keyword')
    tr = data.get('time_range')
    try:
        res = mongo.search_by_keyword(kw) if kw else mongo.search_by_time_range(tr['start'], tr['end'])
        emit('search_messages_results', {'results': res}, room=request.sid)
    except Exception as e:
        emit('notification', {'success': False, 'message': str(e)}, room=request.sid)

@socketio.on('get_group_info')
def handle_get_group_info(data):
    info = mongo.get_group_info(data.get('group_name'))
    if info: emit('group_info_data', info, room=request.sid)

@socketio.on('add_group_members')
def handle_add_group_members(data):
    admin, gn, mems = data.get('username'), data.get('group_name'), data.get('members', [])
    success, msg, added = mongo.add_group_members(admin, gn, mems)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        emit('group_members_updated', {'group_name': gn}, room=request.sid)
        now = datetime.datetime.now().strftime("%H:%M")
        for m in added:
            sid = redis_c.get(f"sid:{m}")
            if sid:
                sid_str = sid.decode('utf-8')
                emit('conversations_data', mongo.get_user_conversations(m), room=sid_str)
                socketio.server.enter_room(sid_str, gn, namespace='/')
                emit('new_msg', {'username': "Système", 'message': f"Ajouté à {gn}.", 'time': now, 'room': gn}, room=sid_str)
            emit('new_msg', {'username': "Système", 'message': f"{m} a rejoint.", 'time': now, 'room': gn}, room=gn)

@socketio.on('kick_group_member')
def handle_kick_group_member(data):
    admin, gn, target = data.get('username'), data.get('group_name'), data.get('target')
    success, msg = mongo.kick_group_member(admin, gn, target)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        emit('group_members_updated', {'group_name': gn}, room=request.sid)
        target_sid = redis_c.get(f"sid:{target}")
        if target_sid:
            sid_str = target_sid.decode('utf-8')
            socketio.server.leave_room(sid_str, gn, namespace='/')
            emit('conversations_data', mongo.get_user_conversations(target), room=sid_str)
            emit('kicked_from_group', {'group_name': gn}, room=sid_str)
        emit('new_msg', {'username': "Système", 'message': f"{target} exclu.", 'time': datetime.datetime.now().strftime("%H:%M"), 'room': gn}, room=gn)

@socketio.on('leave_group')
def handle_leave_group(data):
    user, gn = data.get('username'), data.get('group_name')
    success, msg = mongo.leave_group(user, gn)
    emit('notification', {'success': success, 'message': msg}, room=request.sid)
    if success:
        leave_room(gn)
        emit('conversations_data', mongo.get_user_conversations(user), room=request.sid)
        emit('new_msg', {'username': "Système", 'message': f"{user} est parti.", 'time': datetime.datetime.now().strftime("%H:%M"), 'room': gn}, room=gn)

@socketio.on('typing')
def handle_typing(data):
    emit('display_typing', data, room=data.get('room'), include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    emit('hide_typing', data, room=data.get('room'), include_self=False)

@socketio.on('search_users')
def handle_search_users(data):
    emit('search_results', {'results': mongo.search_users(data.get('query', ''))}, room=request.sid)

def get_online_users():
    keys = redis_c.keys("user:*")
    return sorted([k.decode('utf-8').split(":")[1] for k in keys])

if __name__ == "__main__":
    print("🚀 Serveur lancé sur http://127.0.0.1:5001")
    socketio.run(app, debug=True, port=5001)
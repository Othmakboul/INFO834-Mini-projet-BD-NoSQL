from flask import Flask, render_template, request, redirect
from database import get_redis_client
from mongodb_manager import MongoManager

app = Flask(__name__)
mongo = MongoManager()
redis_c = get_redis_client()

@app.route('/')
def index():
    # 1. Récupérer les messages depuis MongoDB
    messages = list(mongo.collection.find().sort("timestamp", -1).limit(20))
    
    # 2. Récupérer les utilisateurs en ligne depuis Redis
    keys = redis_c.keys("user:*")
    users_online = [k.split(":")[1] for k in keys]
    
    return render_template('index.html', messages=messages, users=users_online)

@app.route('/send', methods=['POST'])
def send():
    pseudo = request.form.get('pseudo')
    message = request.form.get('message')
    if pseudo and message:
        mongo.save_message(pseudo, "GLOBAL", message)
    return redirect('/')

if __name__ == "__main__":
    app.run(debug=True, port=5000)
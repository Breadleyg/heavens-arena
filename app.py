from flask import Flask, render_template, request, session, jsonify, g
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, time, os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'geheim123')

# 🔧 Fix Socket.IO for Heroku deployment
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
    transports=['websocket', 'polling'],
    ping_timeout=60,
    ping_interval=25
)

DATABASE = 'users.db'

def init_db():
    """Initialize database if it doesn't exist"""
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        with open('schema.sql', 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

# Initialize database on startup
init_db()

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db: db.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username, password = data['username'], data['password']
    db = get_db()
    if db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({"error": "Gebruiker bestaat al"}), 409
    db.execute("INSERT INTO users (username, password) VALUES (?, ?)",
               (username, generate_password_hash(password)))
    db.commit()
    session['username'] = username
    return jsonify({"message": "Geregistreerd", "floor": 1})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username, password = data['username'], data['password']
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user and check_password_hash(user['password'], password):
        session['username'] = username
        return jsonify({"message": "Ingelogd", "floor": user['floor']})
    return jsonify({"error": "Ongeldige login"}), 403

@app.route('/active_users')
def active_users():
    return jsonify({"active": len(user_sid)})


# --- WebSocket systeem ---

waiting_players = []
active_rooms = {}  # room_id: {players: [p1, p2], accepted: set(), moves: dict}
user_sid = {}      # username -> socket id
user_room = {}     # username -> room_id

def get_result(p1, p2):
    rules = {'rock': 'scissors', 'paper': 'rock', 'scissors': 'paper'}
    if p1 == p2: return "draw"
    return "win" if rules[p1] == p2 else "lose"

def update_floor(username, won):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    floor = user['floor']
    floor = floor + 1 if won else max(1, floor - 1)
    db.execute("UPDATE users SET floor = ? WHERE username = ?", (floor, username))
    db.commit()
    return floor

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Socket connected: {request.sid}")
    emit('connected', {'status': 'connected', 'sid': request.sid})

@socketio.on('register_user')
def handle_register_user(data):
    username = data.get('username')
    if not username:
        print("❌ No username provided in register_user")
        return
    
    user_sid[username] = request.sid
    print(f"✅ {username} registered with socket: {request.sid}")
    print(f"📊 Total connected users: {len(user_sid)}")
    emit('user_registered', {'status': 'registered', 'username': username})

@socketio.on('find_match')
def handle_find_match(data):
    username = data.get('username')
    if not username:
        print("❌ No username provided in find_match")
        emit('match_error', {'error': 'Username is required'})
        return
        
    print(f"🔍 {username} looking for match. Socket: {request.sid}")
    
    # Verify user is properly registered
    if username not in user_sid:
        print(f"❌ {username} not found in user_sid, re-registering")
        user_sid[username] = request.sid
    
    if username in user_room:
        print(f"❌ {username} already in room: {user_room[username]}")
        emit('match_error', {'error': 'Je zit al in een actieve match'}, room=user_sid.get(username))
        return
        
    if username not in waiting_players:
        waiting_players.append(username)
        print(f"📝 Added {username} to waiting list. Total waiting: {len(waiting_players)}")

    print(f"🎯 Current waiting players: {waiting_players}")
    
    if len(waiting_players) >= 2:
        p1 = waiting_players.pop(0)
        p2 = waiting_players.pop(0)
        room_id = f"room_{p1}_{p2}_{int(time.time())}"

        print(f"🎮 Creating match: {p1} vs {p2} in room {room_id}")

        active_rooms[room_id] = {
            "players": [p1, p2],
            "accepted": set(),
            "moves": {}
        }
        user_room[p1] = room_id
        user_room[p2] = room_id

        # Ensure both players have valid socket connections
        p1_sid = user_sid.get(p1)
        p2_sid = user_sid.get(p2)
        
        if not p1_sid or not p2_sid:
            print(f"❌ Missing socket IDs: {p1}={p1_sid}, {p2}={p2_sid}")
            # Cleanup and re-add to waiting if socket missing
            if room_id in active_rooms:
                del active_rooms[room_id]
            user_room.pop(p1, None)
            user_room.pop(p2, None)
            if p1_sid:
                waiting_players.insert(0, p1)
            if p2_sid:
                waiting_players.insert(0, p2)
            emit('match_error', {'error': 'Connection error, please try again'})
            return

        join_room(room_id, sid=p1_sid)
        join_room(room_id, sid=p2_sid)

        print(f"✅ Sending match_found to both players")
        emit('match_found', {'opponent': p2}, room=p1_sid)
        emit('match_found', {'opponent': p1}, room=p2_sid)
    else:
        print(f"⏳ {username} waiting for opponent...")
        emit('waiting', {'message': 'Wachten op tegenstander...'}, room=request.sid)

@socketio.on('accept_match')
def handle_accept_match(data):
    username = data.get('username')
    room_id = user_room.get(username)
    if not room_id or room_id not in active_rooms:
        emit('match_error', {'error': 'Geen geldige kamer'}, room=request.sid)
        return

    room = active_rooms[room_id]
    room["accepted"].add(username)

    if len(room["accepted"]) == 2:
        emit('start_game', {'message': 'Beide spelers hebben geaccepteerd! Kies je zet.'}, room=room_id)
    else:
        opponent = [p for p in room["players"] if p != username][0]
        emit('waiting_accept', {'message': f'Wachten op {opponent} om te accepteren...'}, room=request.sid)

@socketio.on('make_move')
def handle_make_move(data):
    username = data.get('username')
    move = data.get('move')
    room_id = user_room.get(username)

    if not room_id or room_id not in active_rooms:
        emit('match_error', {'error': 'Geen geldige kamer'}, room=request.sid)
        return

    room = active_rooms[room_id]
    room["moves"][username] = move

    if len(room["moves"]) < 2:
        emit('waiting_move', {'message': 'Wachten op tegenstander...'}, room=request.sid)
        return

    # Beide zetten binnen → bepaal resultaat
    p1, p2 = room["players"]
    move1, move2 = room["moves"][p1], room["moves"][p2]
    result1 = get_result(move1, move2)
    result2 = "draw" if result1 == "draw" else ("lose" if result1 == "win" else "win")

    floor1 = update_floor(p1, result1 == "win")
    floor2 = update_floor(p2, result2 == "win")

    emit('game_result', {
        'your_move': move1,
        'opponent_move': move2,
        'result': result1,
        'new_floor': floor1
    }, room=user_sid[p1])

    emit('game_result', {
        'your_move': move2,
        'opponent_move': move1,
        'result': result2,
        'new_floor': floor2
    }, room=user_sid[p2])

    # Cleanup
    del active_rooms[room_id]
    user_room.pop(p1, None)
    user_room.pop(p2, None)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    disconnected_user = None
    
    # Find and remove disconnected user
    for user, s in list(user_sid.items()):
        if s == sid:
            disconnected_user = user
            print(f"🔌 {user} disconnected (socket: {sid})")
            user_sid.pop(user, None)
            break
    
    if disconnected_user:
        # Remove from waiting list
        if disconnected_user in waiting_players:
            waiting_players.remove(disconnected_user)
            print(f"📝 Removed {disconnected_user} from waiting list")
        
        # Handle active room cleanup
        room_id = user_room.get(disconnected_user)
        if room_id and room_id in active_rooms:
            room = active_rooms[room_id]
            other_player = [p for p in room["players"] if p != disconnected_user]
            if other_player:
                other_player = other_player[0]
                print(f"🎮 Notifying {other_player} that opponent disconnected")
                if other_player in user_sid:
                    emit('match_error', {'error': 'Tegenstander heeft de verbinding verbroken'}, 
                         room=user_sid[other_player])
                user_room.pop(other_player, None)
            
            del active_rooms[room_id]
            user_room.pop(disconnected_user, None)
            print(f"🧹 Cleaned up room {room_id}")
    
    print(f"📊 Remaining connected users: {len(user_sid)}")

@app.route('/leaderboard')
def leaderboard():
    db = get_db()
    rows = db.execute("SELECT username, floor FROM users ORDER BY floor DESC, username ASC LIMIT 10").fetchall()
    return jsonify([
        {
            "username": row["username"],
            "floor": row["floor"],
            "online": row["username"] in user_sid  # ✅ check live status
        }
        for row in rows
    ])

@app.route('/debug')
def debug():
    return jsonify({
        "connected_users": len(user_sid),
        "waiting_players": waiting_players,
        "active_rooms": len(active_rooms),
        "user_sid_keys": list(user_sid.keys())
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

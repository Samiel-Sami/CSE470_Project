from flask import Flask, request,render_template, redirect,session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, join_room, leave_room
import bcrypt
from datetime import datetime  # New import

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)
app.secret_key = 'secret_key'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

    def __init__(self,email,password,name):
        self.name = name
        self.email = email
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self,password):
        return bcrypt.checkpw(password.encode('utf-8'),self.password.encode('utf-8'))
    

# new code (added by afra)
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(100), nullable=False)
    recipient = db.Column(db.String(100), nullable=True)  # Can be null for group chat
    room = db.Column(db.String(100), nullable=True)  # Can be null for private chats
    message = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __init__(self, sender, recipient, room, message):
        self.sender = sender
        self.recipient = recipient
        self.room = room
        self.message = message


with app.app_context():
    db.create_all()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method == 'POST':
        # handle request
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        new_user = User(name=name,email=email,password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')



    return render_template('register.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['email'] = user.email
            return redirect('/dashboard')
        else:
            return render_template('login.html',error='Invalid user')

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if session['email']:
        user = User.query.filter_by(email=session['email']).first()
        return render_template('dashboard.html',user=user)
    
    return redirect('/login')

@app.route('/logout')
def logout():
    session.pop('email',None)
    return redirect('/login')



@app.route('/chat')
def chat():
    username = request.args.get('username')
    room = request.args.get('room')

    # new code (added by Afra) for one-to-one chat
    recipient = request.args.get('recipient')  # New parameter for one-to-one chat

    if username and (room or recipient):    #  Ensure at least one of room or recipient exists
        return render_template('chat.html', username=username, room=room, recipient=recipient)
    else:
        return redirect(url_for('index'))

@socketio.on('send_message')
def handle_send_message_event(data):

    # new code (added by Afra)
    username = data['username']
    message = data['message']
    room = data.get('room')  # Get room if it's a group chat
    recipient = data.get('recipient')  # Get recipient if it's a one-to-one chat


    # code modifed (by Afra) to integrate one-to-one chat feature to the existing group chat feature

    if recipient:  # One-to-one chat
        # Log the private message event
        app.logger.info(f"{username} has sent a private message to {recipient}: {message}")

        # Save private message (newly added)
        new_message = Message(sender=username, recipient=recipient, room=None, message=message)
        
        # Emit the message only to the recipient
        socketio.emit('receive_message', data, to=recipient)
    
    elif room:  # Group chat
        # Log the group message event
        app.logger.info(f"{username} has sent a message to room {room}: {message}")
        
        # Save group message
        new_message = Message(sender=username, recipient=None, room=room, message=message)

        # Emit the message to everyone in the room
        socketio.emit('receive_message', data, room=room)

    
    db.session.add(new_message)
    db.session.commit()


    


@socketio.on('join_room')
def handle_join_room_event(data):
    app.logger.info("{} has joined the room {}".format(data['username'], data['room']))
    join_room(data['room'])
    socketio.emit('join_room_announcement', data, room=data['room'])



@socketio.on('leave_room')
def handle_leave_room_event(data):
    app.logger.info("{} has left the room {}".format(data['username'], data['room']))
    leave_room(data['room'])
    socketio.emit('leave_room_announcement', data, room=data['room'])



# new code (added by Afra) [Delete Specific Message]
@app.route('/delete_message/<int:message_id>', methods=['POST'])
def delete_message(message_id):
    message = Message.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    return redirect('/recent_chats')



# new coded (added by Afra) [Search specific messages in a chat]
@app.route('/search_chat', methods=['GET', 'POST'])
def search_chat():
    query = request.args.get('query')  # Query from search form
    if query:
        # Search for messages containing the query (case-insensitive)
        messages = Message.query.filter(Message.message.ilike(f'%{query}%')).all()
    else:
        messages = []
    
    return render_template('search_chat.html', messages=messages)






# new code (added by Afra) [Recent Chats functionality]
@app.route('/recent_chats')
def recent_chats():
    # Get the last 10 messages for the logged-in user (either private or group)
    user_email = session.get('email')
    user = User.query.filter_by(email=user_email).first()

    # Get recent private messages for the user (sent or received)
    recent_private_messages = Message.query.filter(
        (Message.sender == user.name) | (Message.recipient == user.name)
    ).order_by(Message.timestamp.desc()).limit(10).all()

    return render_template('recent_chats.html', messages=recent_private_messages)


#     History
@app.route('/chat_history')
def chat_history():
    # Fetch all messages, ordered by timestamp descending
    all_messages = Message.query.order_by(Message.timestamp.desc()).all()
    
    return render_template('chat_history.html', messages=all_messages)



if __name__ == '__main__':
    #app.run(debug=True)
    socketio.run(app, debug=True)
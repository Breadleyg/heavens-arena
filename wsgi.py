"""
WSGI entry point for production deployment
"""
from app import app, socketio

# For gunicorn with Socket.IO, we need to expose the socketio app
application = socketio

if __name__ == "__main__":
    socketio.run(app)

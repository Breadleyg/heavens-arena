#!/bin/bash
# Render startup script

# Install dependencies
pip install -r requirements.txt

# Start the application
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT wsgi:application

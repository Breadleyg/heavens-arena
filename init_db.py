import sqlite3
import os

# Initialize database
DATABASE = 'users.db'

def init_db():
    """Initialize the database with schema.sql"""
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        with open('schema.sql', 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print("Database initialized!")

if __name__ == '__main__':
    init_db()

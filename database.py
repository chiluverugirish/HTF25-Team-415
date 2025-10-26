import sqlite3
from datetime import datetime
import hashlib
import os

DATABASE = 'video_captions.db'

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Videos table (history of processed videos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_filename TEXT NOT NULL,
            video_file TEXT NOT NULL,
            srt_file TEXT NOT NULL,
            style TEXT NOT NULL,
            language TEXT NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, email, password):
    """Create a new user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        password_hash = hash_password(password)
        cursor.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return True, user_id
    except sqlite3.IntegrityError as e:
        conn.close()
        if 'username' in str(e):
            return False, "Username already exists"
        elif 'email' in str(e):
            return False, "Email already exists"
        return False, "User creation failed"

def verify_user(username, password):
    """Verify user credentials"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute(
        'SELECT * FROM users WHERE username = ? AND password_hash = ?',
        (username, password_hash)
    )
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return True, dict(user)
    return False, None

def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def save_video_record(user_id, original_filename, video_file, srt_file, style, language):
    """Save processed video record to database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO videos (user_id, original_filename, video_file, srt_file, style, language)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, original_filename, video_file, srt_file, style, language))
    
    conn.commit()
    video_id = cursor.lastrowid
    conn.close()
    return video_id

def get_user_videos(user_id, limit=10):
    """Get user's video processing history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM videos 
        WHERE user_id = ? 
        ORDER BY processed_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    
    videos = cursor.fetchall()
    conn.close()
    return [dict(video) for video in videos]

def get_all_user_videos(user_id):
    """Get all videos for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM videos 
        WHERE user_id = ? 
        ORDER BY processed_at DESC
    ''', (user_id,))
    
    videos = cursor.fetchall()
    conn.close()
    return [dict(video) for video in videos]

def delete_video_record(video_id, user_id):
    """Delete a video record (for cleanup)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify ownership before deleting
    cursor.execute('DELETE FROM videos WHERE id = ? AND user_id = ?', (video_id, user_id))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

# Initialize database on import
if __name__ == '__main__':
    init_db()

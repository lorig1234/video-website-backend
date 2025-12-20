# database.py
import sqlite3
from datetime import datetime
from pathlib import Path

DATABASE_PATH = Path("data/streaming.db")

def get_db():
    """Get database connection"""
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # User sessions table (for token management)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_valid BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Watch history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watch_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            show_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            episode_title TEXT,
            show_title TEXT,
            position_seconds INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            progress_percent REAL DEFAULT 0,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, episode_id)
        )
    ''')
    
    # User IP addresses log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ip_address TEXT NOT NULL,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, ip_address)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# User operations
def create_user(username: str, email: str, password_hash: str) -> int:
    """Create a new user and return user ID"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as e:
        if 'username' in str(e):
            raise ValueError("Username already exists")
        elif 'email' in str(e):
            raise ValueError("Email already exists")
        raise
    finally:
        conn.close()

def get_user_by_username(username: str) -> dict:
    """Get user by username"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> dict:
    """Get user by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_last_login(user_id: int):
    """Update user's last login time"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET last_login = ? WHERE id = ?',
        (datetime.utcnow(), user_id)
    )
    conn.commit()
    conn.close()

# Session operations
def create_session(user_id: int, token: str, ip_address: str, user_agent: str, expires_at: datetime) -> int:
    """Create a new session"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO user_sessions (user_id, token, ip_address, user_agent, expires_at) 
           VALUES (?, ?, ?, ?, ?)''',
        (user_id, token, ip_address, user_agent, expires_at)
    )
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id

def invalidate_session(token: str):
    """Invalidate a session (logout)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE user_sessions SET is_valid = 0 WHERE token = ?', (token,))
    conn.commit()
    conn.close()

def get_session(token: str) -> dict:
    """Get session by token"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_sessions WHERE token = ? AND is_valid = 1', (token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# Watch history operations
def save_watch_progress(user_id: int, show_id: str, episode_id: str, 
                        position_seconds: int, duration_seconds: int,
                        show_title: str = None, episode_title: str = None):
    """Save or update watch progress"""
    conn = get_db()
    cursor = conn.cursor()
    
    progress_percent = (position_seconds / duration_seconds * 100) if duration_seconds > 0 else 0
    
    cursor.execute('''
        INSERT INTO watch_history (user_id, show_id, episode_id, episode_title, show_title, 
                                   position_seconds, duration_seconds, progress_percent, watched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, episode_id) DO UPDATE SET
            position_seconds = excluded.position_seconds,
            duration_seconds = excluded.duration_seconds,
            progress_percent = excluded.progress_percent,
            watched_at = excluded.watched_at,
            episode_title = COALESCE(excluded.episode_title, episode_title),
            show_title = COALESCE(excluded.show_title, show_title)
    ''', (user_id, show_id, episode_id, episode_title, show_title,
          position_seconds, duration_seconds, progress_percent, datetime.utcnow()))
    
    conn.commit()
    conn.close()

def get_watch_progress(user_id: int, episode_id: str) -> dict:
    """Get watch progress for a specific episode"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM watch_history WHERE user_id = ? AND episode_id = ?',
        (user_id, episode_id)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_continue_watching(user_id: int, limit: int = 10) -> list:
    """Get user's continue watching list (recently watched, not completed)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM watch_history 
        WHERE user_id = ? AND progress_percent < 95
        ORDER BY watched_at DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_watch_history(user_id: int, limit: int = 50) -> list:
    """Get user's full watch history"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM watch_history 
        WHERE user_id = ?
        ORDER BY watched_at DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_last_episode_per_show(user_id: int) -> dict:
    """Get the last watched episode for each show
    
    Returns a dictionary mapping show_id to the last watched episode info
    Example: {"friends": {"episode_id": "friends_s01_e05", "progress_percent": 45, ...}}
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT w1.* FROM watch_history w1
        INNER JOIN (
            SELECT show_id, MAX(watched_at) as max_watched
            FROM watch_history
            WHERE user_id = ?
            GROUP BY show_id
        ) w2 ON w1.show_id = w2.show_id AND w1.watched_at = w2.max_watched
        WHERE w1.user_id = ?
    ''', (user_id, user_id))
    rows = cursor.fetchall()
    conn.close()
    
    # Convert to dictionary keyed by show_id
    result = {}
    for row in rows:
        row_dict = dict(row)
        result[row_dict['show_id']] = row_dict
    return result

# IP tracking operations
def log_user_ip(user_id: int, ip_address: str):
    """Log user IP address"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_ips (user_id, ip_address)
        VALUES (?, ?)
        ON CONFLICT(user_id, ip_address) DO UPDATE SET
            last_seen = CURRENT_TIMESTAMP,
            access_count = access_count + 1
    ''', (user_id, ip_address))
    conn.commit()
    conn.close()

def get_user_ips(user_id: int) -> list:
    """Get all IPs associated with a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ip_address, first_seen, last_seen, access_count 
        FROM user_ips 
        WHERE user_id = ?
        ORDER BY last_seen DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Initialize database on import
init_db()

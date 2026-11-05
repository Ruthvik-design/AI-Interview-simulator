import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from config import DB, ADMIN_PASSWORD, KEYS

def connection():
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def add_column(con, table, column, decl):
    """Upgrade an old (v1) database: add a column only if it is missing."""
    existing = [r['name'] for r in con.execute(f'PRAGMA table_info({table})')]
    if column not in existing:
        con.execute(f'ALTER TABLE {table} ADD COLUMN {column} {decl}')


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 200_000).hex()


def create_user(con, username, display_name, password, role):
    salt = secrets.token_hex(16)
    con.execute('INSERT INTO users (username,display_name,password_hash,salt,role,created_at) VALUES (?,?,?,?,?,?)',
                (username, display_name, hash_password(password, salt), salt, role, now()))


def init_db():
    with connection() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin','candidate')), created_at TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS interviews (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
            experience TEXT NOT NULL, kind TEXT NOT NULL, total INTEGER NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, user_id INTEGER)''')
        con.execute('''CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, interview_id TEXT NOT NULL,
            question TEXT NOT NULL, answer TEXT NOT NULL, feedback TEXT NOT NULL,
            scores TEXT NOT NULL, created_at TEXT NOT NULL, is_followup INTEGER NOT NULL DEFAULT 0)''')
        con.execute('''CREATE TABLE IF NOT EXISTS questions (
            interview_id TEXT PRIMARY KEY, current_question TEXT NOT NULL,
            is_followup INTEGER NOT NULL DEFAULT 0)''')
        con.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS training_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, sample_answer TEXT NOT NULL,
            ideal_score REAL NOT NULL, note TEXT NOT NULL DEFAULT '', created_by INTEGER, created_at TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, interview_id TEXT,
            category TEXT NOT NULL, rating INTEGER NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL)''')
        # v1 -> v2 upgrade for an existing database file
        add_column(con, 'interviews', 'user_id', 'INTEGER')
        add_column(con, 'answers', 'is_followup', 'INTEGER NOT NULL DEFAULT 0')
        add_column(con, 'questions', 'is_followup', 'INTEGER NOT NULL DEFAULT 0')
        con.execute('''CREATE TABLE IF NOT EXISTS candidate_progress (
            user_id INTEGER PRIMARY KEY, latest_score REAL NOT NULL DEFAULT 0,
            previous_score REAL, improvement_pct REAL, progress_rating TEXT NOT NULL DEFAULT 'Not rated',
            attempts INTEGER NOT NULL DEFAULT 0, latest_interview_id TEXT, updated_at TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS improvement_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            interview_id TEXT NOT NULL UNIQUE, plan TEXT NOT NULL, created_at TEXT NOT NULL)''')
        if con.execute("SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()['c'] == 0:
            create_user(con, 'admin', 'Administrator', ADMIN_PASSWORD, 'admin')
            print('Created first admin account: username "admin". Change the default password!')


def get_setting(key, default=None):
    with connection() as con:
        row = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    with connection() as con:
        con.execute('INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES (?,?,?)', (key, value, now()))


def delete_setting(key):
    with connection() as con:
        con.execute('DELETE FROM settings WHERE key=?', (key,))

def report(con, interview_id):
    row = con.execute('SELECT * FROM interviews WHERE id=?', (interview_id,)).fetchone()
    if row is None:
        raise ValueError('Interview not found.')
    answers = [dict(x) for x in con.execute('SELECT * FROM answers WHERE interview_id=? ORDER BY id', (interview_id,))]
    for a in answers:
        a['scores'] = json.loads(a['scores'])
    averages = {k: round(sum(a['scores'][k] for a in answers) / len(answers), 1) if answers else 0 for k in KEYS}
    overall = round(sum(averages.values()) / len(KEYS), 1)
    return {'interview': dict(row), 'answers': answers, 'averages': averages, 'overall': overall}

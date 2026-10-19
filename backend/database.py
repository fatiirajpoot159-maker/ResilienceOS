"""
ResilienceOS Database & Multi-Tenant Isolation Engine.
Uses SQLite with PBKDF2-HMAC-SHA256 password hashing, session management,
role-based access control, and complete per-user data isolation.
"""
import sqlite3
import hashlib
import os
import secrets
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "resilienceos.db"

def get_now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_expiry_iso(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations=100000
    ).hex()
    return hashed, salt

def verify_password(password: str, hashed: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(new_hash, hashed)

def init_db():
    conn = get_connection()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user', -- 'admin' or 'user'
            business_name TEXT DEFAULT 'My Bakery',
            created_at TEXT NOT NULL,
            last_sign_in_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS businesses (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            industry TEXT DEFAULT 'Bakery operations',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            duration INTEGER NOT NULL,
            deadline INTEGER NOT NULL,
            missed_penalty INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            scenario_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            savings INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_email TEXT,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_simulations_user ON simulations(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
        """)
    conn.close()

def has_admin_user() -> bool:
    conn = get_connection()
    try:
        cur = conn.cursor()
        count = cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
        return count > 0
    finally:
        conn.close()

# Auth Functions
def register_user(email: str, password: str, full_name: str, business_name: str = "My Bakery", role: str = "user"):
    email = email.strip().lower()
    full_name = full_name.strip()
    business_name = business_name.strip() or "My Bakery"
    
    if not email or "@" not in email:
        raise ValueError("Valid email address is required.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    if len(full_name) < 2:
        raise ValueError("Name must be at least 2 characters.")

    conn = get_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            if cur.fetchone():
                raise ValueError("An account with this email already exists.")

            # Rule: If NO admin exists in the system, this first user becomes the Owner & Administrator!
            # If an admin ALREADY exists, every subsequent user is strictly a standard 'user'.
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            admin_count = cur.fetchone()[0]
            if admin_count == 0:
                assigned_role = 'admin'
            else:
                assigned_role = 'user'

            user_id = "usr_" + secrets.token_hex(8)
            pw_hash, salt = hash_password(password)
            now = get_now_iso()

            cur.execute("""
                INSERT INTO users (id, email, password_hash, salt, full_name, role, business_name, created_at, last_sign_in_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, email, pw_hash, salt, full_name, assigned_role, business_name, now, now))

            biz_id = "biz_" + secrets.token_hex(8)
            cur.execute("""
                INSERT INTO businesses (id, user_id, name, industry, created_at)
                VALUES (?, ?, ?, 'Bakery operations', ?)
            """, (biz_id, user_id, business_name, now))

            token = secrets.token_hex(32)
            expires = get_expiry_iso(7)
            cur.execute("""
                INSERT INTO sessions (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (token, user_id, now, expires))

            cur.execute("""
                INSERT INTO audit_logs (user_id, user_email, action, details, timestamp)
                VALUES (?, ?, 'USER_REGISTERED', ?, ?)
            """, (user_id, email, f"Registered role: {role}", now))

            return {
                "token": token,
                "user": {
                    "id": user_id,
                    "email": email,
                    "full_name": full_name,
                    "role": role,
                    "business_name": business_name,
                    "business_id": biz_id
                }
            }
    finally:
        conn.close()

def login_user(email: str, password: str):
    email = email.strip().lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.email, u.password_hash, u.salt, u.full_name, u.role, u.business_name, b.id as business_id
            FROM users u
            LEFT JOIN businesses b ON b.user_id = u.id
            WHERE u.email = ?
        """, (email,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Invalid email or password.")

        if not verify_password(password, row["password_hash"], row["salt"]):
            raise ValueError("Invalid email or password.")

        user_id = row["id"]
        now = get_now_iso()
        expires = get_expiry_iso(7)
        token = secrets.token_hex(32)

        with conn:
            cur.execute("""
                UPDATE users SET last_sign_in_at = ? WHERE id = ?
            """, (now, user_id))

            cur.execute("""
                INSERT INTO sessions (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (token, user_id, now, expires))

            cur.execute("""
                INSERT INTO audit_logs (user_id, user_email, action, details, timestamp)
                VALUES (?, ?, 'USER_LOGIN', 'Successful login', ?)
            """, (user_id, email, now))

        return {
            "token": token,
            "user": {
                "id": user_id,
                "email": row["email"],
                "full_name": row["full_name"],
                "role": row["role"],
                "business_name": row["business_name"] or "My Bakery",
                "business_id": row["business_id"]
            }
        }
    finally:
        conn.close()

def get_user_from_token(token: str):
    if not token:
        return None
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.email, u.full_name, u.role, u.business_name, u.created_at, u.last_sign_in_at,
                   b.id as business_id, s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN businesses b ON b.user_id = u.id
            WHERE s.token = ?
        """, (token,))
        row = cur.fetchone()
        if not row:
            return None
        
        # Check token expiry
        if row["expires_at"] < get_now_iso():
            with conn:
                cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None

        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "business_name": row["business_name"] or "My Bakery",
            "business_id": row["business_id"],
            "created_at": row["created_at"],
            "last_sign_in_at": row["last_sign_in_at"]
        }
    finally:
        conn.close()

def logout_user(token: str):
    if not token:
        return
    conn = get_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    finally:
        conn.close()

# User Data Isolation Functions
def get_user_orders(user_id: str):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, duration, deadline, missed_penalty
            FROM orders
            WHERE user_id = ?
            ORDER BY id ASC
        """, (user_id,))
        rows = cur.fetchall()
        return [
            {
                "id": r["name"], # Frontend binds job identifier to 'id'
                "duration": r["duration"],
                "deadline": r["deadline"],
                "missed_penalty": r["missed_penalty"]
            }
            for r in rows
        ]
    finally:
        conn.close()

def replace_user_orders(user_id: str, orders_list: list):
    if not isinstance(orders_list, list) or len(orders_list) > 12:
        raise ValueError("Orders must be a list of at most 12 items.")

    conn = get_connection()
    try:
        with conn:
            cur = conn.cursor()
            # Ensure business exists
            cur.execute("SELECT id FROM businesses WHERE user_id = ? LIMIT 1", (user_id,))
            biz = cur.fetchone()
            if not biz:
                biz_id = "biz_" + secrets.token_hex(8)
                cur.execute("INSERT INTO businesses (id, user_id, name, created_at) VALUES (?, ?, 'My Bakery', ?)",
                            (biz_id, user_id, get_now_iso()))
            else:
                biz_id = biz["id"]

            now = get_now_iso()
            # Clear previous user orders
            cur.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))

            for item in orders_list:
                name = str(item.get("id") or item.get("name") or "").strip()
                dur = int(item.get("duration", 1))
                dline = int(item.get("deadline", 1))
                pen = int(item.get("missed_penalty", 0))
                if not name:
                    continue
                cur.execute("""
                    INSERT INTO orders (business_id, user_id, name, duration, deadline, missed_penalty, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (biz_id, user_id, name, dur, dline, pen, now))

            return get_user_orders(user_id)
    finally:
        conn.close()

def save_user_simulation(user_id: str, scenario: dict, result: dict):
    conn = get_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM businesses WHERE user_id = ? LIMIT 1", (user_id,))
            biz = cur.fetchone()
            biz_id = biz["id"] if biz else "default_biz"
            now = get_now_iso()
            savings = int(result.get("savings", 0))

            cur.execute("""
                INSERT INTO simulations (business_id, user_id, scenario_json, result_json, savings, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (biz_id, user_id, json.dumps(scenario), json.dumps(result), savings, now))
            return True
    finally:
        conn.close()

def get_user_simulations(user_id: str, limit: int = 20):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, scenario_json, result_json, savings, created_at
            FROM simulations
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cur.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "scenario": json.loads(r["scenario_json"]),
                "result": json.loads(r["result_json"]),
                "savings": r["savings"],
                "created_at": r["created_at"]
            })
        return results
    finally:
        conn.close()

# Strictly Protected Admin Endpoints
def get_admin_overview(admin_user: dict):
    if admin_user.get("role") != "admin":
        raise PermissionError("Access denied: Administrator privileges required.")
    
    conn = get_connection()
    try:
        cur = conn.cursor()
        user_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        business_count = cur.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
        order_count = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        sim_count = cur.execute("SELECT COUNT(*) FROM simulations").fetchone()[0]
        total_savings = cur.execute("SELECT COALESCE(SUM(savings), 0) FROM simulations").fetchone()[0]

        # Registered users list with details
        cur.execute("""
            SELECT u.id, u.email, u.full_name as name, u.role, u.business_name, u.created_at, u.last_sign_in_at,
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) as order_count,
                   (SELECT COUNT(*) FROM simulations s WHERE s.user_id = u.id) as simulation_count
            FROM users u
            ORDER BY u.created_at DESC
            LIMIT 100
        """)
        users = [dict(r) for r in cur.fetchall()]

        # Recent global simulations
        cur.execute("""
            SELECT s.id, s.user_id, u.email, u.business_name, s.savings, s.created_at, s.scenario_json
            FROM simulations s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.created_at DESC
            LIMIT 15
        """)
        recent_sims = []
        for r in cur.fetchall():
            sc = json.loads(r["scenario_json"])
            recent_sims.append({
                "id": r["id"],
                "user_email": r["email"],
                "business_name": r["business_name"],
                "savings": r["savings"],
                "created_at": r["created_at"],
                "outage_duration": sc.get("outage_duration", 0),
                "backup": sc.get("backup", False)
            })

        # Recent audit logs
        cur.execute("""
            SELECT id, user_email, action, details, timestamp
            FROM audit_logs
            ORDER BY timestamp DESC
            LIMIT 25
        """)
        logs = [dict(r) for r in cur.fetchall()]

        return {
            "user_count": user_count,
            "business_count": business_count,
            "order_count": order_count,
            "simulation_count": sim_count,
            "total_savings_pkr": total_savings,
            "users": users,
            "recent_simulations": recent_sims,
            "audit_logs": logs
        }
    finally:
        conn.close()

def set_user_role(admin_user: dict, target_user_id: str, new_role: str):
    if admin_user.get("role") != "admin":
        raise PermissionError("Access denied: Administrator privileges required.")
    if new_role not in ("admin", "user"):
        raise ValueError("Invalid role specified.")

    conn = get_connection()
    try:
        with conn:
            cur = conn.cursor()
            # Prevent demoting the last admin
            if new_role == "user":
                admin_count = cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                cur.execute("SELECT role FROM users WHERE id = ?", (target_user_id,))
                target_role = cur.fetchone()
                if target_role and target_role[0] == "admin" and admin_count <= 1:
                    raise ValueError("Cannot demote the sole administrator of the system.")

            cur.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, target_user_id))
            now = get_now_iso()
            cur.execute("""
                INSERT INTO audit_logs (user_id, user_email, action, details, timestamp)
                VALUES (?, ?, 'ROLE_CHANGE', ?, ?)
            """, (admin_user["id"], admin_user["email"], f"Updated user {target_user_id} to {new_role}", now))
            return True
    finally:
        conn.close()

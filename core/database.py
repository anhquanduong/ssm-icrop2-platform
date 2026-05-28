import sqlite3
import logging
import os
import sys
import json
import time

logger = logging.getLogger(__name__)

# ---- In-process PostgreSQL reachability cache ----
# Prevents a failed connection attempt from being retried on every
# Streamlit rerun (which can fire 5-10 times per page interaction).
# Format: {"reachable": bool, "checked_at": float (time.time())}
_POSTGRES_CACHE_TTL_SECONDS = 60  # Re-test reachability every 60 seconds
_postgres_reachable_cache: dict = {}

# Placeholder hostnames that indicate the user has not yet configured secrets
_PLACEHOLDER_HOSTNAMES = {
    "your-database-host.com",
    "your-host",
    "localhost",     # uncomment if you want to block local-only too
}


def is_postgres_enabled() -> bool:
    """
    Checks if PostgreSQL is enabled in Streamlit secrets and not in a unit testing context.
    Returns False immediately if the host is still a placeholder value.
    """
    is_testing = 'unittest' in sys.modules or any('unittest' in arg for arg in sys.argv)
    if is_testing:
        return False
    try:
        import streamlit as st
        if "postgres" not in st.secrets:
            return False
        host = st.secrets["postgres"].get("host", "")
        # Reject unconfigured placeholder hostnames
        if not host or host.strip().lower() in _PLACEHOLDER_HOSTNAMES:
            return False
        return True
    except Exception:
        return False

class DialectAgnosticCursor:
    """
    A cursor wrapper that intercepts SQL executions to dynamically translate 
    SQLite-specific syntax and placeholders into PostgreSQL compatible queries.
    """
    def __init__(self, cursor, is_postgres: bool):
        self.cursor = cursor
        self.is_postgres = is_postgres
        self._lastrowid = None

    def execute(self, sql, params=None):
        if self.is_postgres:
            # 1. Translate SQLite '?' parameter placeholder to Postgres '%s'
            sql = sql.replace("?", "%s")
            
            # 2. Translate SQLite-specific PRAGMA queries to system schema queries
            if "PRAGMA table_info" in sql:
                parts = sql.split("table_info(")
                if len(parts) > 1:
                    t_name = parts[1].split(")")[0].strip().replace("'", "").replace('"', "")
                    sql = f"""
                        SELECT 0, column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = '{t_name}'
                    """
            
            # 3. Translate SQLite types and keys to Postgres counterparts
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            sql = sql.replace("DATETIME DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            sql = sql.replace("BLOB", "BYTEA")
            
            # 4. Intercept PRAGMA commands
            if "PRAGMA" in sql:
                return self
            
            # 5. Translate SQLite INSERT OR REPLACE to standard INSERT
            if "INSERT OR REPLACE" in sql:
                sql = sql.replace("INSERT OR REPLACE", "INSERT")
            
            # 6. Append RETURNING clause to INSERT statements to fetch and store self._lastrowid
            sql_upper = sql.upper().strip()
            if sql_upper.startswith("INSERT") and "RETURNING" not in sql_upper:
                sql_clean = sql.strip().rstrip(";")
                sql_clean += " RETURNING id"
                if params is not None:
                    self.cursor.execute(sql_clean, params)
                else:
                    self.cursor.execute(sql_clean)
                try:
                    self._lastrowid = self.cursor.fetchone()[0]
                except Exception:
                    self._lastrowid = None
                return self

        if params is not None:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)
        return self

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchone(self):
        return self.cursor.fetchone()

    @property
    def lastrowid(self):
        if self.is_postgres:
            return self._lastrowid
        return getattr(self.cursor, "lastrowid", None)

    def __getattr__(self, name):
        return getattr(self.cursor, name)

class DialectAgnosticConnection:
    """
    A connection wrapper that implements dialect-agnostic cursors and transaction blocks.
    """
    def __init__(self, conn, is_postgres: bool):
        self.conn = conn
        self.is_postgres = is_postgres

    def cursor(self):
        return DialectAgnosticCursor(self.conn.cursor(), self.is_postgres)

    def commit(self):
        return self.conn.commit()

    def rollback(self):
        return self.conn.rollback()

    def close(self):
        return self.conn.close()

    def execute(self, sql, params=None):
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()

def get_database_connection(db_path=None):
    """
    Generates a secure database connection.
    Connects to external persistent PostgreSQL if enabled; otherwise falls back to SQLite.
    Uses an in-process cache to avoid hammering a failing PostgreSQL server on every Streamlit rerun.
    """
    global _postgres_reachable_cache
    if is_postgres_enabled():
        import streamlit as st
        import psycopg2

        # Check the in-process cache first
        now = time.time()
        cached = _postgres_reachable_cache
        last_check = cached.get("checked_at", 0)
        was_reachable = cached.get("reachable", None)

        if was_reachable is False and (now - last_check) < _POSTGRES_CACHE_TTL_SECONDS:
            # Still within the cooldown window — skip to SQLite immediately
            pass
        else:
            try:
                pg_secrets = st.secrets["postgres"]
                conn = psycopg2.connect(
                    host=pg_secrets["host"],
                    port=int(pg_secrets.get("port", 5432)),
                    database=pg_secrets["database"],
                    user=pg_secrets["username"],
                    password=pg_secrets["password"],
                    connect_timeout=10,   # pooler needs more time than direct
                    sslmode="require"     # Supabase mandates SSL on all connections
                )
                _postgres_reachable_cache = {"reachable": True, "checked_at": now}
                return DialectAgnosticConnection(conn, is_postgres=True)
            except Exception as conn_err:
                _postgres_reachable_cache = {"reachable": False, "checked_at": now}
                logger.warning(
                    f"PostgreSQL connection failed ({conn_err}). "
                    "Resiliently falling back to local SQLite app_v2.db!"
                )
            
    if db_path is None:
        db_path = get_persistent_db_path()
    conn = sqlite3.connect(db_path)
    return DialectAgnosticConnection(conn, is_postgres=False)

def get_persistent_db_path() -> str:
    """
    Isolates the SQLite database initialization routing path for fallback/testing.
    """
    import sys
    is_testing = 'unittest' in sys.modules or any('unittest' in arg for arg in sys.argv)
    
    if is_testing:
        db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "app_v2.db")
        )
        return db_path

    persistent_dir = os.environ.get("PERSISTENT_DIR") or os.environ.get("STREAMLIT_APP_DATA_DIR")
    if not persistent_dir:
        home_dir = os.path.expanduser("~")
        persistent_dir = os.path.join(home_dir, ".icrop")
        
    try:
        os.makedirs(persistent_dir, exist_ok=True)
        db_path = os.path.abspath(os.path.join(persistent_dir, "app_v2.db"))
        return db_path
    except Exception as e:
        db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "app_v2.db")
        )
        return db_path

def migrate_database_schema(conn):
    """
    Initializes database tables and verified dynamic schemas for both SQLite and PostgreSQL.
    """
    cursor = conn.cursor()
    
    if getattr(conn, "is_postgres", False):
        logger.info("Initializing persistent PostgreSQL schema and constraints...")
        
        # 1. Create Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email VARCHAR(255) UNIQUE,
                name VARCHAR(255),
                workplace VARCHAR(255),
                is_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                reset_token TEXT,
                token_expiry VARCHAR(255),
                login_attempts INTEGER DEFAULT 0,
                lockout_until VARCHAR(255) NULL,
                last_verification_sent VARCHAR(255) NULL,
                session_token TEXT,
                user_tier VARCHAR(255) DEFAULT 'Researcher',
                run_limit INTEGER DEFAULT 50,
                bio_name VARCHAR(255),
                bio_organization VARCHAR(255),
                bio_text TEXT
            )
        """)
        
        # Robust migrations for users table if it already exists from baseline
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255) UNIQUE")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS workplace VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_expiry VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS login_attempts INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lockout_until VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_verification_sent VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_token TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS user_tier VARCHAR(255) DEFAULT 'Researcher'")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS run_limit INTEGER DEFAULT 50")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio_name VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio_organization VARCHAR(255)")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio_text TEXT")
        except Exception as e:
            logger.warning(f"Postgres users migration bypassed: {e}")
            
        # Promote Admin email automatically
        try:
            cursor.execute("UPDATE users SET user_tier = 'Admin' WHERE email = 'duonganhquan@humg.edu.vn'")
        except Exception as e:
            logger.warning(f"Postgres admin promotion bypassed: {e}")
            
        # 2. Create Crops Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crops (
                id SERIAL PRIMARY KEY,
                crop_name VARCHAR(255) NOT NULL,
                cultivar VARCHAR(255),
                parameters_json TEXT,
                crop_produce_type VARCHAR(255),
                lifecycle_strategy VARCHAR(255),
                t_dormancy_trigger DOUBLE PRECISION,
                t_base_winter DOUBLE PRECISION,
                is_public INTEGER DEFAULT 1,
                created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        
        # Robust migrations for crops table
        try:
            cursor.execute("ALTER TABLE crops ADD COLUMN IF NOT EXISTS crop_produce_type VARCHAR(255)")
            cursor.execute("ALTER TABLE crops ADD COLUMN IF NOT EXISTS lifecycle_strategy VARCHAR(255)")
            cursor.execute("ALTER TABLE crops ADD COLUMN IF NOT EXISTS t_dormancy_trigger DOUBLE PRECISION")
            cursor.execute("ALTER TABLE crops ADD COLUMN IF NOT EXISTS t_base_winter DOUBLE PRECISION")
            cursor.execute("ALTER TABLE crops ADD COLUMN IF NOT EXISTS is_public INTEGER DEFAULT 1")
            cursor.execute("ALTER TABLE crops ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        except Exception as e:
            logger.warning(f"Postgres crops migration bypassed: {e}")
        
        # 3. Create Simulation History Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulation_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                scenario_name TEXT NOT NULL,
                timestamp VARCHAR(255) NOT NULL,
                results_json TEXT NOT NULL
            )
        """)
        
        # 4. Create Simulation Runs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulation_runs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                run_name TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                crop_id INTEGER REFERENCES crops(id) ON DELETE SET NULL,
                summary_metrics TEXT,
                raw_data_blob BYTEA
            )
        """)
        
        # 5. Create Crop Profiles Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crop_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                crop_name VARCHAR(255) NOT NULL,
                is_public INTEGER NOT NULL CHECK (is_public IN (0, 1)),
                parameters_json TEXT NOT NULL,
                crop_produce_type VARCHAR(255),
                lifecycle_strategy VARCHAR(255),
                t_dormancy_trigger DOUBLE PRECISION,
                t_base_winter DOUBLE PRECISION
            )
        """)
        
        # Robust migrations for crop_profiles table
        try:
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN IF NOT EXISTS crop_produce_type VARCHAR(255)")
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN IF NOT EXISTS lifecycle_strategy VARCHAR(255)")
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN IF NOT EXISTS t_dormancy_trigger DOUBLE PRECISION")
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN IF NOT EXISTS t_base_winter DOUBLE PRECISION")
        except Exception as e:
            logger.warning(f"Postgres crop_profiles migration bypassed: {e}")
        
        # 6. Create Security Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(255) NOT NULL,
                ip_address VARCHAR(255),
                timestamp VARCHAR(255) NOT NULL
            )
        """)
        
        conn.commit()
        logger.info("Persistent PostgreSQL schema verified successfully.")
        return
        
    # Standard SQLite Fallback Schema and Migrations
    logger.info("Initializing fallback SQLite schema and migrations...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE,
            name TEXT,
            workplace TEXT,
            is_verified INTEGER DEFAULT 0,
            verification_token TEXT,
            reset_token TEXT,
            token_expiry TEXT,
            login_attempts INTEGER DEFAULT 0,
            lockout_until TEXT NULL,
            last_verification_sent TEXT NULL,
            session_token TEXT,
            user_tier TEXT DEFAULT 'Researcher',
            run_limit INTEGER DEFAULT 50,
            bio_name TEXT,
            bio_organization TEXT,
            bio_text TEXT
        )
    """)
    
    cursor.execute("PRAGMA table_info(users)")
    users_cols = {col[1] for col in cursor.fetchall()}
    users_migrations = [
        ("user_tier", "TEXT DEFAULT 'Researcher'"),
        ("run_limit", "INTEGER DEFAULT 50"),
        ("bio_name", "TEXT"),
        ("bio_organization", "TEXT"),
        ("bio_text", "TEXT")
    ]
    for col_name, col_type in users_migrations:
        if col_name not in users_cols:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                logger.error(f"SQLite migration failed adding {col_name} to users: {e}")
                
    try:
        cursor.execute("UPDATE users SET user_tier = 'Admin' WHERE email = 'duonganhquan@humg.edu.vn'")
        conn.commit()
    except Exception as e:
        logger.warning(f"SQLite admin promotion check bypassed: {e}")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            scenario_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            results_json TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            run_name TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            crop_id INTEGER,
            summary_metrics TEXT,
            raw_data_blob BLOB,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("PRAGMA table_info(crop_profiles)")
    cols = {col[1] for col in cursor.fetchall()}
    if "crop_produce_type" not in cols:
        cursor.execute("ALTER TABLE crop_profiles ADD COLUMN crop_produce_type TEXT")
    if "lifecycle_strategy" not in cols:
        cursor.execute("ALTER TABLE crop_profiles ADD COLUMN lifecycle_strategy TEXT")
    if "t_dormancy_trigger" not in cols:
        cursor.execute("ALTER TABLE crop_profiles ADD COLUMN t_dormancy_trigger REAL")
    if "t_base_winter" not in cols:
        cursor.execute("ALTER TABLE crop_profiles ADD COLUMN t_base_winter REAL")
        
    try:
        cursor.execute("UPDATE crop_profiles SET crop_produce_type = 'Fruit/Seed' WHERE crop_produce_type IS NULL")
        cursor.execute("UPDATE crop_profiles SET lifecycle_strategy = 'Annual (Single-Season)' WHERE lifecycle_strategy IS NULL")
        cursor.execute("UPDATE crop_profiles SET t_dormancy_trigger = 5.0 WHERE t_dormancy_trigger IS NULL")
        cursor.execute("UPDATE crop_profiles SET t_base_winter = 0.0 WHERE t_base_winter IS NULL")
    except Exception as e:
        logger.error(f"SQLite migration failed applying defaults to crop_profiles: {e}")

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crops'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(crops)")
            crops_cols = {col[1] for col in cursor.fetchall()}
            if "crop_produce_type" not in crops_cols:
                cursor.execute("ALTER TABLE crops ADD COLUMN crop_produce_type TEXT")
            if "lifecycle_strategy" not in crops_cols:
                cursor.execute("ALTER TABLE crops ADD COLUMN lifecycle_strategy TEXT")
            if "t_dormancy_trigger" not in crops_cols:
                cursor.execute("ALTER TABLE crops ADD COLUMN t_dormancy_trigger REAL")
            if "t_base_winter" not in crops_cols:
                cursor.execute("ALTER TABLE crops ADD COLUMN t_base_winter REAL")
            if "is_public" not in crops_cols:
                cursor.execute("ALTER TABLE crops ADD COLUMN is_public INTEGER DEFAULT 1")
            if "created_by_user_id" not in crops_cols:
                cursor.execute("ALTER TABLE crops ADD COLUMN created_by_user_id INTEGER")
                
            cursor.execute("UPDATE crops SET crop_produce_type = 'Fruit/Seed' WHERE crop_produce_type IS NULL")
            cursor.execute("UPDATE crops SET lifecycle_strategy = 'Annual (Single-Season)' WHERE lifecycle_strategy IS NULL")
            cursor.execute("UPDATE crops SET t_dormancy_trigger = 5.0 WHERE t_dormancy_trigger IS NULL")
            cursor.execute("UPDATE crops SET t_base_winter = 0.0 WHERE t_base_winter IS NULL")
            cursor.execute("UPDATE crops SET is_public = 1 WHERE is_public IS NULL")
    except Exception as e:
        logger.warning(f"SQLite crops table check/migration skipped: {e}")
    
    conn.commit()
    logger.info("SQLite database schema and secure migrations verified successfully.")

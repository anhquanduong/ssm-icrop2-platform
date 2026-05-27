import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

def get_persistent_db_path() -> str:
    """
    Isolates the SQLite database initialization routing path.
    Checks environment variables (PERSISTENT_DIR, STREAMLIT_APP_DATA_DIR),
    and falls back to a hidden folder in the user's home directory (~/.icrop/)
    to ensure data persistence across ephemeral container restarts.
    """
    # Safeguard for unit test isolation: if executing unit tests, strictly force local db path
    import sys
    is_testing = 'unittest' in sys.modules or any('unittest' in arg for arg in sys.argv)
    
    if is_testing:
        db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "app_v2.db")
        )
        logger.info(f"Unit test environment detected. Forcing isolated local database path: {db_path}")
        return db_path

    persistent_dir = os.environ.get("PERSISTENT_DIR") or os.environ.get("STREAMLIT_APP_DATA_DIR")
    if not persistent_dir:
        home_dir = os.path.expanduser("~")
        persistent_dir = os.path.join(home_dir, ".icrop")
        
    try:
        os.makedirs(persistent_dir, exist_ok=True)
        db_path = os.path.abspath(os.path.join(persistent_dir, "app_v2.db"))
        logger.info(f"Resolved database path to persistent storage: {db_path}")
        return db_path
    except Exception as e:
        # Ultimate fallback to local repo root
        db_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "app_v2.db")
        )
        logger.warning(f"Could not initialize persistent directory ({e}). Falling back to local db: {db_path}")
        return db_path

def migrate_database_schema(conn: sqlite3.Connection):
    """
    Executes a structural check on the crop_profiles (crops) table.
    If the columns crop_produce_type, lifecycle_strategy, t_dormancy_trigger, 
    and t_base_winter do not exist, appends them and applies safe defaults.
    """
    cursor = conn.cursor()
    
    # 0. Permanent User Accounts & History Tables IF NOT EXISTS check
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
            session_token TEXT
        )
    """)
    
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
    logger.info("Database Schema: Verified users and simulation_history tables with IF NOT EXISTS.")
    
    # 1. Structural check on crop_profiles
    cursor.execute("PRAGMA table_info(crop_profiles)")
    cols = {col[1] for col in cursor.fetchall()}
    
    if "crop_produce_type" not in cols:
        try:
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN crop_produce_type TEXT")
            logger.info("Database Migration: Added column 'crop_produce_type' to 'crop_profiles' table.")
        except Exception as e:
            logger.error(f"Migration failed adding crop_produce_type: {e}")
            
    if "lifecycle_strategy" not in cols:
        try:
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN lifecycle_strategy TEXT")
            logger.info("Database Migration: Added column 'lifecycle_strategy' to 'crop_profiles' table.")
        except Exception as e:
            logger.error(f"Migration failed adding lifecycle_strategy: {e}")
            
    if "t_dormancy_trigger" not in cols:
        try:
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN t_dormancy_trigger REAL")
            logger.info("Database Migration: Added column 't_dormancy_trigger' to 'crop_profiles' table.")
        except Exception as e:
            logger.error(f"Migration failed adding t_dormancy_trigger: {e}")
            
    if "t_base_winter" not in cols:
        try:
            cursor.execute("ALTER TABLE crop_profiles ADD COLUMN t_base_winter REAL")
            logger.info("Database Migration: Added column 't_base_winter' to 'crop_profiles' table.")
        except Exception as e:
            logger.error(f"Migration failed adding t_base_winter: {e}")
            
    # Apply defaults for pre-existing rows in crop_profiles
    try:
        cursor.execute("""
            UPDATE crop_profiles 
            SET crop_produce_type = 'Fruit/Seed' 
            WHERE crop_produce_type IS NULL
        """)
        cursor.execute("""
            UPDATE crop_profiles 
            SET lifecycle_strategy = 'Annual (Single-Season)' 
            WHERE lifecycle_strategy IS NULL
        """)
        cursor.execute("""
            UPDATE crop_profiles 
            SET t_dormancy_trigger = 5.0 
            WHERE t_dormancy_trigger IS NULL
        """)
        cursor.execute("""
            UPDATE crop_profiles 
            SET t_base_winter = 0.0 
            WHERE t_base_winter IS NULL
        """)
    except Exception as e:
        logger.error(f"Migration failed applying defaults to crop_profiles: {e}")

    # 2. Structural check on optional crops table (for strict prompt compliance)
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
                
            cursor.execute("""
                UPDATE crops 
                SET crop_produce_type = 'Fruit/Seed' 
                WHERE crop_produce_type IS NULL
            """)
            cursor.execute("""
                UPDATE crops 
                SET lifecycle_strategy = 'Annual (Single-Season)' 
                WHERE lifecycle_strategy IS NULL
            """)
            cursor.execute("""
                UPDATE crops 
                SET t_dormancy_trigger = 5.0 
                WHERE t_dormancy_trigger IS NULL
            """)
            cursor.execute("""
                UPDATE crops 
                SET t_base_winter = 0.0 
                WHERE t_base_winter IS NULL
            """)
    except Exception as e:
        logger.warning(f"Optional crops table check skipped: {e}")

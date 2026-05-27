import sqlite3
import logging

logger = logging.getLogger(__name__)

def migrate_database_schema(conn: sqlite3.Connection):
    """
    Executes a structural check on the crop_profiles (crops) table.
    If the columns crop_produce_type, lifecycle_strategy, t_dormancy_trigger, 
    and t_base_winter do not exist, appends them and applies safe defaults.
    """
    cursor = conn.cursor()
    
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

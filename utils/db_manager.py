import sqlite3
import os
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Database Engineer module that manages the SQLite relational schema and 
    strictly routes data privacy access boundaries.
    """
    def __init__(self, db_path: Optional[str] = None):
        """
        Initializes the database connection and guarantees parent folder existence.
        """
        if db_path is None:
            # Default database location inside icrop2 structure
            self.db_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "app_v2.db")
            )
        else:
            self.db_path = db_path
            
        # Ensure that the parent directory (app/data) exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.initialize_schema()

    @contextmanager
    def get_connection(self) -> sqlite3.Connection:
        """
        Yields a secure connection to the SQLite database and guarantees its clean closure on exit.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;") # Enforce FK constraints
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize_schema(self):
        """
        Initializes the relational tables for users and custom crop physiological profiles.
        Performs dynamic schema migrations (ALTER TABLE) to append columns if upgrading.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Create Users Table (Baseline)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)
            
            # 2. Dynamic Schema Expansion for Users Table (ALTER TABLE checks)
            # Fetch current columns in users table
            cursor.execute("PRAGMA table_info(users)")
            existing_cols = {col[1] for col in cursor.fetchall()}
            
            migrations = [
                ("email", "TEXT UNIQUE"),
                ("name", "TEXT"),
                ("workplace", "TEXT"),
                ("is_verified", "INTEGER DEFAULT 0"),
                ("verification_token", "TEXT"),
                ("reset_token", "TEXT"),
                ("token_expiry", "TEXT"),
                ("login_attempts", "INTEGER DEFAULT 0"),
                ("lockout_until", "TEXT NULL"),
                ("last_verification_sent", "TEXT NULL"),
                ("session_token", "TEXT")
            ]
            
            for col_name, col_type in migrations:
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Database Migration: Added column '{col_name}' ({col_type}) to 'users' table.")
                    except Exception as migration_err:
                        # Fallback for older SQLite versions on direct ALTER UNIQUE additions
                        if "UNIQUE" in col_type:
                            try:
                                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} TEXT")
                                cursor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_users_{col_name} ON users({col_name})")
                                logger.info(f"Database Migration (Index fallback): Added column '{col_name}' (TEXT) and unique index to 'users'.")
                            except Exception as fallback_err:
                                logger.error(f"Migration fallback failed for '{col_name}': {fallback_err}")
                        else:
                            logger.error(f"Failed to add column '{col_name}': {migration_err}")
            
            # 3. Create Crop Profiles Table (with data privacy bounds)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crop_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    crop_name TEXT NOT NULL,
                    is_public INTEGER NOT NULL CHECK (is_public IN (0, 1)),
                    parameters_json TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # 4. Create Security Logs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    ip_address TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            
            # Perform dynamic schema migrations for new crop lifecycle features
            try:
                from core.database import migrate_database_schema
                migrate_database_schema(conn)
            except Exception as migrate_err:
                logger.error(f"Failed to execute core database schema migrations: {migrate_err}")
            
            conn.commit()
            logger.info("SQLite database schema and secure migrations verified successfully.")

    def save_crop_profile(
        self, 
        user_id: int, 
        crop_name: str, 
        is_public: int, 
        param_dict: Dict[str, Any], 
        session_key: Optional[str] = None
    ) -> int:
        """
        Saves a custom crop physiological parameter profile to the relational database.
        If marked 'Private', encrypts the parameter payload using AES-256 before writing to SQLite.
        """
        from utils.crypto_vault import CropCryptoVault
        
        param_json = json.dumps(param_dict)
        
        if is_public == 0:
            if not session_key:
                raise ValueError("Session key is required to encrypt and save private crop profiles.")
            # Encrypt parameters
            cipher_bytes = CropCryptoVault.encrypt_parameters(param_json, session_key)
            param_payload = cipher_bytes.decode('utf-8')
        else:
            param_payload = param_json
            
        crop_produce_type = param_dict.get("crop_produce_type", "Fruit/Seed")
        lifecycle_strategy = param_dict.get("lifecycle_strategy", "Annual (Single-Season)")
        t_dormancy_trigger = param_dict.get("t_dormancy_trigger", 5.0)
        t_base_winter = param_dict.get("t_base_winter", 0.0)
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO crop_profiles (user_id, crop_name, is_public, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, crop_name.strip(), is_public, param_payload, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter))
            conn.commit()
            profile_id = cursor.lastrowid
            logger.info(f"Crop profile '{crop_name}' (ID: {profile_id}) saved by User {user_id}. Public={is_public}")
            return profile_id

    def get_available_profiles(self, current_user_id: int, session_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Strict Data Privacy Access Router.
        Retrieves a combined list of ALL crop profiles that are marked 'Public' (is_public = 1)
        AND those that belong strictly to the current user (user_id = current_user_id).
        Private profiles are transparently decrypted on the fly using AES-256 Fernet.
        """
        from utils.crypto_vault import CropCryptoVault
        
        profiles = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
             # Perform a LEFT JOIN on users to fetch the creator's username
            cursor.execute("""
                SELECT cp.id, cp.user_id, cp.crop_name, cp.is_public, cp.parameters_json, u.username, cp.crop_produce_type, cp.lifecycle_strategy, cp.t_dormancy_trigger, cp.t_base_winter
                FROM crop_profiles cp
                LEFT JOIN users u ON cp.user_id = u.id
                WHERE cp.is_public = 1 OR cp.user_id = ?
            """, (current_user_id,))
            
            rows = cursor.fetchall()
            for r in rows:
                profile_id = r[0]
                uid = r[1]
                crop_name = r[2]
                is_public = r[3]
                raw_params = r[4]
                creator = r[5] or "System"
                db_produce_type = r[6]
                db_lifecycle_strategy = r[7]
                db_dormancy_trigger = r[8]
                db_base_winter = r[9]
                
                # Transparent decryption for private profiles
                if is_public == 0:
                    try:
                        if not session_key:
                            raise ValueError("Session key required to access private crop profiles.")
                        decrypted_str = CropCryptoVault.decrypt_parameters(raw_params.encode('utf-8'), session_key)
                        params = json.loads(decrypted_str)
                    except Exception as e:
                        logger.error(f"Cryptographic failure decrypting private profile ID {profile_id}: {e}")
                        # Strict security exception blocks corrupted or unauthorized data loading
                        raise PermissionError(f"Data Protection Error: Unauthorized or corrupted key. Decryption failed: {str(e)}")
                else:
                    params = json.loads(raw_params)
                
                # Merge columns into params dictionary as fallback/overwrite
                params["crop_produce_type"] = db_produce_type or params.get("crop_produce_type", "Fruit/Seed")
                params["lifecycle_strategy"] = db_lifecycle_strategy or params.get("lifecycle_strategy", "Annual (Single-Season)")
                params["t_dormancy_trigger"] = db_dormancy_trigger if db_dormancy_trigger is not None else params.get("t_dormancy_trigger", 5.0)
                params["t_base_winter"] = db_base_winter if db_base_winter is not None else params.get("t_base_winter", 0.0)
                    
                profiles.append({
                    "id": profile_id,
                    "user_id": uid,
                    "crop_name": crop_name,
                    "is_public": is_public,
                    "parameters": params,
                    "creator": creator
                })
        return profiles

    def increment_failed_attempts(self, username: str) -> int:
        """
        Increments failed login attempts for a username and returns the current total.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET login_attempts = login_attempts + 1 
                WHERE username = ?
            """, (username.strip(),))
            conn.commit()
            
            cursor.execute("SELECT login_attempts FROM users WHERE username = ?", (username.strip(),))
            row = cursor.fetchone()
            return row[0] if row else 0

    def lock_user_account(self, username: str, lockout_minutes: int = 15):
        """
        Locks a user account until a timestamp in the future.
        """
        from datetime import datetime, timedelta
        lockout_time = (datetime.now() + timedelta(minutes=lockout_minutes)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET lockout_until = ? 
                WHERE username = ?
            """, (lockout_time, username.strip()))
            conn.commit()
            logger.info(f"User '{username}' locked out until {lockout_time}.")

    def reset_failed_attempts(self, username: str):
        """
        Resets failed login attempts and unlocks account for a user.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET login_attempts = 0, lockout_until = NULL 
                WHERE username = ?
            """, (username.strip(),))
            conn.commit()
            logger.info(f"Reset login attempts and unlocked account for '{username}'.")

    def log_security_event(self, user_id: Optional[int], action: str, ip_address: str):
        """
        Logs a security/suspicious event into security_logs table.
        """
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO security_logs (user_id, action, ip_address, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, ip_address, timestamp))
            conn.commit()
            logger.warning(f"Security event logged: User {user_id} | Action: {action} | IP: {ip_address}")

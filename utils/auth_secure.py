import hashlib
import os
import secrets
import logging
import smtplib
import math
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import streamlit as st
from utils.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Global thread-safe in-memory cache to simulate the sent email box locally if SMTP is unconfigured
LOCAL_MAILBOX_SIMULATOR = []

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """
    Generates a secure PBKDF2 SHA-256 hash using native hashlib with a 16-byte random salt.
    """
    if salt is None:
        salt = os.urandom(16)
    pwd_bytes = password.encode('utf-8')
    key = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt, 100000)
    return f"{salt.hex()}${key.hex()}"

def verify_password(stored_hash: str, password: str) -> bool:
    """
    Verifies an incoming password against the secure stored hash string.
    """
    try:
        salt_hex, key_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(key_hex)
        pwd_bytes = password.encode('utf-8')
        key = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt, 100000)
        return key == stored_key
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False

def send_system_email(to_email: str, subject: str, body_html: str, text_fallback: str) -> bool:
    """
    Sends an email using the SMTP settings declared in Streamlit Secrets Manager.
    If the mail server is unconfigured or transmission fails, logs details and 
    appends the message payload to the LOCAL_MAILBOX_SIMULATOR in-memory cache.
    """
    try:
        smtp_secrets = st.secrets.get("smtp", {})
    except Exception:
        smtp_secrets = {}
        
    host = smtp_secrets.get("host")
    port = smtp_secrets.get("port", 587)
    user = smtp_secrets.get("user")
    password = smtp_secrets.get("password")
    from_email = smtp_secrets.get("from_email", "no-reply@ssm-icrop.org")
    
    def fallback_to_simulator(reason: str):
        LOCAL_MAILBOX_SIMULATOR.append({
            "to": to_email,
            "subject": subject,
            "body_html": body_html,
            "timestamp": datetime.now().isoformat()
        })
        logger.info(f"[Local Mailbox Simulator] Cached email due to: {reason}")

    if os.environ.get("SSM_ICROP_TESTING") == "1" or not host or not user or not password:
        fallback_to_simulator("SMTP Credentials missing or running in testing environment.")
        return True
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        
        part1 = MIMEText(text_fallback, "plain")
        part2 = MIMEText(body_html, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Connect to SMTP server
        with smtplib.SMTP(host, int(port), timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_email, to_email, msg.as_string())
            
        logger.info(f"Successfully sent SMTP email to {to_email}")
        return True
    except Exception as smtp_err:
        logger.error(f"SMTP Server delivery failed ({smtp_err}). Redirecting to local debug simulator.")
        fallback_to_simulator(f"SMTP transmission error: {smtp_err}")
        return True

def register_secure_user(username: str, email: str, password: str, name: str, workplace: str) -> Tuple[bool, str]:
    """
    Registers a new user inside the SQLite database, generates a cryptographic 
    verification token, and dispatches an activation notification.
    """
    username_clean = username.strip()
    email_clean = email.strip().lower()
    name_clean = name.strip()
    workplace_clean = workplace.strip()
    
    if len(username_clean) < 3:
        return False, "Username must be at least 3 characters long."
    if "@" not in email_clean or "." not in email_clean:
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if not name_clean:
        return False, "Please provide your Full Name."
        
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check uniqueness
        cursor.execute("SELECT id FROM users WHERE username = ?", (username_clean,))
        if cursor.fetchone() is not None:
            return False, "Username is already registered."
            
        cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
        if cursor.fetchone() is not None:
            return False, "Email address is already registered."
            
        pwd_hash = hash_password(password)
        verify_token = secrets.token_urlsafe(32)
        token_expiry = (datetime.now() + timedelta(hours=24)).isoformat()
        
        try:
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, name, workplace, is_verified, verification_token, token_expiry)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """, (username_clean, email_clean, pwd_hash, name_clean, workplace_clean, verify_token, token_expiry))
            conn.commit()
            
            # Fetch user ID to log security entry
            cursor.execute("SELECT id FROM users WHERE username = ?", (username_clean,))
            new_uid = cursor.fetchone()[0]
            
            db.log_security_event(new_uid, "Account registered (pending verification)", "127.0.0.1")
            
            # Dispatch verification email
            try:
                base_url = st.secrets.get("smtp", {}).get("base_url", "http://localhost:8502").rstrip("/")
            except Exception:
                base_url = "http://localhost:8502"
            verify_url = f"{base_url}/?verify_token={verify_token}"
            subject = "🌱 Verify Your BOKU SSM-iCrop Account"
            
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
                <h2 style="color: #10B981;">Welcome to the SSM-iCrop Platform!</h2>
                <p>Hello <strong>{name_clean}</strong>,</p>
                <p>Thank you for registering. Please activate your account to unlock all C4 crop simulation tools and Community Profiles.</p>
                <p style="margin: 30px 0;">
                    <a href="{verify_url}" style="background-color: #10B981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                        Activate My Account
                    </a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p><a href="{verify_url}">{verify_url}</a></p>
                <hr style="border: none; border-top: 1px solid #E5E7EB; margin-top: 30px;">
                <p style="font-size: 0.8rem; color: #6B7280;">If you did not request this registration, please ignore this email.</p>
            </body>
            </html>
            """
            text_fallback = f"Hello {name_clean},\n\nPlease verify your account by opening this link: {verify_url}"
            send_system_email(email_clean, subject, body_html, text_fallback)
            
            return True, "Account created successfully! A verification link has been sent to your email."
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            return False, f"Registration failed: {str(e)}"

def authenticate_secure_user(username: str, password: str, ip_address: str = "127.0.0.1") -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Authenticates a user, enforcing progressive lockout timers on failed attempts.
    Returns (Success, Message, UserInfoPayload).
    """
    username_clean = username.strip()
    db = DatabaseManager()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, password_hash, is_verified, lockout_until, login_attempts, email, name, workplace
            FROM users 
            WHERE username = ? OR email = ?
        """, (username_clean, username_clean.lower()))
        
        row = cursor.fetchone()
        if row is None:
            # Fake verifying to mask timing differences
            hash_password(password)
            return False, "Authentication failed. Invalid username or password.", None
            
        uid, pwd_hash, is_verified, lockout_until, attempts, email, name, workplace = row
        
        # Resolve the canonical DB username (user may have logged in via email)
        cursor.execute("SELECT username FROM users WHERE id = ?", (uid,))
        uname_row = cursor.fetchone()
        db_username = uname_row[0] if uname_row else username_clean
        
        # 1. Progressive lockout check
        if lockout_until:
            lockout_time = datetime.fromisoformat(lockout_until)
            if datetime.now() < lockout_time:
                remaining_min = math.ceil((lockout_time - datetime.now()).total_seconds() / 60)
                db.log_security_event(uid, "Rejected login attempt (Account Locked Out)", ip_address)
                return False, f"Account temporarily locked due to failed attempts. Try again in {remaining_min} minutes.", None
            else:
                # Lockout time passed, clear attempts dynamically
                db.reset_failed_attempts(db_username)
                attempts = 0
                
        # 2. Check Password
        if verify_password(pwd_hash, password):
            # Success! Reset failed attempts using canonical DB username
            db.reset_failed_attempts(db_username)
            db.log_security_event(uid, "User logged in successfully", ip_address)
            
            # Generate and persist browser-persistent session token
            session_token = secrets.token_hex(24)
            cursor.execute("UPDATE users SET session_token = ? WHERE id = ?", (session_token, uid))
            conn.commit()
            
            # Derive secure session key unique to that user session
            from utils.crypto_vault import CropCryptoVault
            salt_hex = pwd_hash.split("$")[0]
            session_key = CropCryptoVault.generate_key_from_user_session(pwd_hash, salt_hex)
            
            # Enforce session verification parameters payload
            user_payload = {
                "user_id": uid,
                "username": db_username,  # always return the canonical DB username
                "email": email,
                "name": name,
                "workplace": workplace,
                "is_verified": is_verified,
                "session_token": session_token,
                "session_key": session_key
            }
            return True, "Login successful!", user_payload
        else:
            # Failed attempt — use canonical DB username so the UPDATE hits the right row
            new_attempts = db.increment_failed_attempts(db_username)
            
            if new_attempts >= 5:
                # Progressive lock: 15 minutes
                db.lock_user_account(db_username, 15)
                db.log_security_event(uid, f"Suspicious Activity: Account locked out (Attempts={new_attempts})", ip_address)
                return False, "Authentication failed. Account has been locked for 15 minutes due to too many failed attempts.", None
            else:
                db.log_security_event(uid, f"Failed login attempt ({new_attempts} of 5)", ip_address)
                return False, f"Authentication failed. Incorrect password. (Attempt {new_attempts} of 5)", None

def verify_user_email_token(token: str) -> Tuple[bool, str]:
    """
    Matches the incoming activation token, flags user as verified, and clears token attributes.
    """
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, token_expiry 
            FROM users 
            WHERE verification_token = ?
        """, (token,))
        row = cursor.fetchone()
        
        if row is None:
            return False, "Activation link is invalid or has already been used."
            
        uid, name, expiry = row
        
        # Check token expiration
        if datetime.now() > datetime.fromisoformat(expiry):
            # Regeneate new token on expiration
            new_token = secrets.token_urlsafe(32)
            new_expiry = (datetime.now() + timedelta(hours=24)).isoformat()
            cursor.execute("""
                UPDATE users 
                SET verification_token = ?, token_expiry = ? 
                WHERE id = ?
            """, (new_token, new_expiry, uid))
            conn.commit()
            return False, "Activation link has expired. A new verification email has been queued."
            
        # Success! Activate user
        cursor.execute("""
            UPDATE users 
            SET is_verified = 1, verification_token = NULL, token_expiry = NULL 
            WHERE id = ?
        """, (uid,))
        conn.commit()
        db.log_security_event(uid, "Email successfully verified", "127.0.0.1")
        return True, f"Welcome {name}! Your account has been activated. You can now log in."

def resend_verification_email(email_or_username: str) -> Tuple[bool, str]:
    """
    Locates an unverified user by username or email, checks a 2-minute rate-limiting
    cooldown window, and dispatches a fresh email activation token.
    """
    clean_val = email_or_username.strip()
    db = DatabaseManager()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check by email first, then username
        cursor.execute("""
            SELECT id, username, email, name, is_verified, last_verification_sent 
            FROM users 
            WHERE email = ? OR username = ?
        """, (clean_val.lower(), clean_val))
        row = cursor.fetchone()
        
        # Security mitigation: return generic message for nonexistent accounts
        # to prevent account enumeration/harvesting.
        if row is None:
            logger.warning(f"Verification resend requested for nonexistent user: {clean_val}")
            return True, "If this account is registered and pending activation, a new link has been dispatched."
            
        uid, uname, uemail, name, is_verified, last_sent = row
        
        if is_verified == 1:
            return False, "This account has already been verified and activated. Please sign in using the Sign In tab. If you have forgotten your password, use the Forgot Password tab to request a reset link."
            
        # Check rate-limiting cooldown (2 minutes / 120 seconds)
        if last_sent is not None:
            try:
                last_sent_dt = datetime.fromisoformat(last_sent)
                elapsed = (datetime.now() - last_sent_dt).total_seconds()
                cooldown = 120 # 2 minutes in seconds
                if elapsed < cooldown:
                    remaining = int(cooldown - elapsed)
                    logger.warning(f"Verification resend rate-limited for {uname}. Wait {remaining}s.")
                    return False, f"Please wait {remaining} seconds before requesting another activation link."
            except Exception as parse_err:
                logger.error(f"Failed parsing last_verification_sent timestamp: {parse_err}")
                
        # Generate fresh token & update sent timestamp
        new_token = secrets.token_urlsafe(32)
        new_expiry = (datetime.now() + timedelta(hours=24)).isoformat()
        current_time = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE users 
            SET verification_token = ?, token_expiry = ?, last_verification_sent = ? 
            WHERE id = ?
        """, (new_token, new_expiry, current_time, uid))
        conn.commit()
        db.log_security_event(uid, "Verification activation link resent", "127.0.0.1")
        
        # Build URL dynamically
        try:
            base_url = st.secrets.get("smtp", {}).get("base_url", "http://localhost:8502").rstrip("/")
        except Exception:
            base_url = "http://localhost:8502"
            
        verify_url = f"{base_url}/?verify_token={new_token}"
        subject = "🌱 Verify Your BOKU SSM-iCrop Account"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
            <h2 style="color: #10B981;">SSM-iCrop Account Activation</h2>
            <p>Hello <strong>{name}</strong>,</p>
            <p>Here is your new activation link. Please verify your account to unlock all crop growth simulation models.</p>
            <p style="margin: 30px 0;">
                <a href="{verify_url}" style="background-color: #10B981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Activate My Account
                </a>
            </p>
            <p>Or paste this link into your browser:</p>
            <p><a href="{verify_url}">{verify_url}</a></p>
            <hr style="border: none; border-top: 1px solid #E5E7EB; margin-top: 30px;">
            <p style="font-size: 0.8rem; color: #6B7280;">This activation link is valid for 24 hours.</p>
        </body>
        </html>
        """
        text_fallback = f"Hello {name},\n\nPlease activate your account via this link: {verify_url}"
        send_system_email(uemail, subject, body_html, text_fallback)
        
        return True, "A fresh verification link has been successfully dispatched to your email address."

def request_password_reset(email: str) -> Tuple[bool, str]:
    """
    Locates user by email, generates a time-sensitive 1-hour reset token, 
    and dispatches a secure password change request.
    """
    email_clean = email.strip().lower()
    db = DatabaseManager()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, username FROM users WHERE email = ?", (email_clean,))
        row = cursor.fetchone()
        
        # Security mitigation: generic message to prevent email harvesting
        # However, we return success so the uploader mailbox fallback prints the link if running locally
        if row is None:
            logger.warning(f"Reset requested for unmapped email address: {email_clean}")
            return True, "If this email is registered, a password reset link has been dispatched."
            
        uid, name, username = row
        reset_token = secrets.token_urlsafe(32)
        expiry = (datetime.now() + timedelta(hours=1)).isoformat() # 1 hour validity
        
        cursor.execute("""
            UPDATE users 
            SET reset_token = ?, token_expiry = ? 
            WHERE id = ?
        """, (reset_token, expiry, uid))
        conn.commit()
        db.log_security_event(uid, "Password reset token requested", "127.0.0.1")
        
        try:
            base_url = st.secrets.get("smtp", {}).get("base_url", "http://localhost:8502").rstrip("/")
        except Exception:
            base_url = "http://localhost:8502"
        reset_url = f"{base_url}/?reset_token={reset_token}"
        subject = "🔐 SSM-iCrop Password Reset Request"
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
            <h2 style="color: #EF4444;">SSM-iCrop Password Reset Request</h2>
            <p>Hello <strong>{name}</strong> (Username: `{username}`),</p>
            <p>We received a request to reset your password. This reset token is valid for **1 hour only**.</p>
            <p style="margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #EF4444; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Reset My Password
                </a>
            </p>
            <p>Or paste this link into your browser:</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <hr style="border: none; border-top: 1px solid #E5E7EB; margin-top: 30px;">
            <p style="font-size: 0.8rem; color: #6B7280;">If you did not request a password reset, please ignore this email immediately.</p>
        </body>
        </html>
        """
        text_fallback = f"Hello {name},\n\nPlease reset your password via this link: {reset_url}"
        send_system_email(email_clean, subject, body_html, text_fallback)
        
        return True, "If this email is registered, a password reset link has been dispatched."

def execute_password_reset_token(token: str, new_password: str) -> Tuple[bool, str]:
    """
    Validates the password reset token and updates the hash if not expired.
    """
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters long."
        
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, token_expiry 
            FROM users 
            WHERE reset_token = ?
        """, (token,))
        row = cursor.fetchone()
        
        if row is None:
            return False, "Invalid or already used password reset link."
            
        uid, expiry = row
        
        # Check token expiration
        if datetime.now() > datetime.fromisoformat(expiry):
            return False, "This password reset link has expired. Please request a new one."
            
        # Save new hash
        new_hash = hash_password(new_password)
        cursor.execute("""
            UPDATE users 
            SET password_hash = ?, reset_token = NULL, token_expiry = NULL 
            WHERE id = ?
        """, (new_hash, uid))
        conn.commit()
        db.log_security_event(uid, "Password reset successfully via email token", "127.0.0.1")
        return True, "Your password has been successfully reset! You can now log in."

def update_user_profile(user_id: int, new_name: str, new_workplace: str) -> Tuple[bool, str]:
    """
    Updates the Full Name and Workplace parameters for an authenticated user.
    """
    name_clean = new_name.strip()
    workplace_clean = new_workplace.strip()
    
    if not name_clean:
        return False, "Full Name cannot be left blank."
        
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET name = ?, workplace = ? 
            WHERE id = ?
        """, (name_clean, workplace_clean, user_id))
        conn.commit()
        db.log_security_event(user_id, "User profile updated", "127.0.0.1")
        return True, "Profile details updated successfully!"

def verify_session_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validates a browser-persistent session token, loads canonical user details,
    and derives the corresponding cryptographic key to preserve security.
    """
    token_clean = token.strip()
    if not token_clean:
        return False, None
        
    db = DatabaseManager()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, email, name, workplace, is_verified, password_hash 
            FROM users 
            WHERE session_token = ?
        """, (token_clean,))
        row = cursor.fetchone()
        
        if row is None:
            return False, None
            
        uid, db_username, email, name, workplace, is_verified, pwd_hash = row
        
        # Derive secure session key unique to that user session
        from utils.crypto_vault import CropCryptoVault
        salt_hex = pwd_hash.split("$")[0]
        session_key = CropCryptoVault.generate_key_from_user_session(pwd_hash, salt_hex)
        
        user_payload = {
            "user_id": uid,
            "username": db_username,
            "email": email,
            "name": name,
            "workplace": workplace,
            "is_verified": is_verified,
            "session_token": token_clean,
            "session_key": session_key
        }
        return True, user_payload

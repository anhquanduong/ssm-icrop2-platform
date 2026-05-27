import hashlib
import base64
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

class SecurityError(Exception):
    """
    Custom exception representing unauthorized cryptographic access or key verification failure.
    """
    pass

class CropCryptoVault:
    """
    Cryptographic vault managing AES-256 symmetric encryption and key derivations
    to secure private crop physiological parameter configurations.
    """
    @staticmethod
    def generate_key_from_user_session(user_password_hash: str, user_salt: str) -> str:
        """
        Derives a stable, cryptographically secure 32-byte Fernet key from the
        user's password hash and salt using PBKDF2 with SHA-256.
        
        Parameters:
            user_password_hash (str): The secure password hash string stored in SQLite.
            user_salt (str): The user's unique password salt hex.
            
        Returns:
            str: URL-safe base64-encoded key compatible with Fernet.
        """
        pwd_bytes = user_password_hash.encode('utf-8')
        salt_bytes = user_salt.encode('utf-8')
        
        # Key stretching via PBKDF2 SHA-256 (32 bytes)
        derived_key = hashlib.pbkdf2_hmac(
            hash_name='sha256',
            password=pwd_bytes,
            salt=salt_bytes,
            iterations=100000,
            dklen=32
        )
        
        # Base64 encoding compatible with cryptography.fernet
        return base64.urlsafe_b64encode(derived_key).decode('utf-8')

    @staticmethod
    def encrypt_parameters(plain_text_json: str, key: str) -> bytes:
        """
        Encrypts standard plain-text JSON parameters using AES-256.
        
        Parameters:
            plain_text_json (str): Raw string of JSON-formatted parameters.
            key (str): base64 URL-safe key derived from session.
            
        Returns:
            bytes: Encrypted ciphertext bytes.
        """
        try:
            fernet = Fernet(key.encode('utf-8'))
            return fernet.encrypt(plain_text_json.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to encrypt parameters: {e}")
            raise SecurityError(f"Cryptographic encryption failed: {str(e)}")

    @staticmethod
    def decrypt_parameters(cipher_text_bytes: bytes, key: str) -> str:
        """
        Decrypts AES-256 ciphertext back to plain-text JSON.
        
        Parameters:
            cipher_text_bytes (bytes): Fernet ciphertext bytes.
            key (str): base64 URL-safe key derived from session.
            
        Returns:
            str: Plain-text JSON parameters.
        """
        try:
            fernet = Fernet(key.encode('utf-8'))
            return fernet.decrypt(cipher_text_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed. Invalid session key or corrupted payload: {e}")
            raise SecurityError(f"Data Protection Error: Decryption failed. Unauthorized access or invalid key: {str(e)}")

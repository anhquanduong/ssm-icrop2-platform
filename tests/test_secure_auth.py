import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

# Add parent directory of tests (which is 'icrop2') to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
icrop2_dir = os.path.abspath(os.path.join(current_dir, ".."))
if icrop2_dir not in sys.path:
    sys.path.insert(0, icrop2_dir)

from utils.db_manager import DatabaseManager
import utils.auth_secure as auth_secure

class TestSecureAuthentication8502(unittest.TestCase):
    def setUp(self):
        # Create a temporary database for testing
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        
        # Patch DatabaseManager instantiation
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.original_init = DatabaseManager.__init__
        temp_path = self.temp_db_path
        def patched_init(inner_self, db_path=None):
            self.original_init(inner_self, db_path=temp_path)
        DatabaseManager.__init__ = patched_init
        
        # Clear simulator mailbox
        auth_secure.LOCAL_MAILBOX_SIMULATOR.clear()

    def tearDown(self):
        DatabaseManager.__init__ = self.original_init
        import gc
        gc.collect()
        try:
            os.close(self.temp_db_fd)
        except Exception:
            pass
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception as teardown_err:
                print(f"Teardown clean-up warning: {teardown_err}")

    def test_registration_link_contains_8502(self):
        """Assert registration activation links are routed to port 8502 for icrop2 sandbox."""
        success, msg = auth_secure.register_secure_user(
            username="user_8502", email="test8502@test.com", password="password123", name="Sandbox User", workplace="BOKU"
        )
        self.assertTrue(success)
        self.assertIn("verification link", msg.lower())
        
        self.assertEqual(len(auth_secure.LOCAL_MAILBOX_SIMULATOR), 1)
        sent_mail = auth_secure.LOCAL_MAILBOX_SIMULATOR[0]
        self.assertEqual(sent_mail["to"], "test8502@test.com")
        self.assertIn("http://localhost:8502/?verify_token=", sent_mail["body_html"])

    def test_resend_email_link_contains_8502(self):
        """Assert resent verification links are routed to port 8502 for icrop2 sandbox."""
        # Register a pending user
        auth_secure.register_secure_user(
            username="resend_8502", email="resend8502@test.com", password="password123", name="Resend User", workplace="BOKU"
        )
        auth_secure.LOCAL_MAILBOX_SIMULATOR.clear()
        
        # Resend email
        success, msg = auth_secure.resend_verification_email("resend_8502")
        self.assertTrue(success)
        self.assertEqual(len(auth_secure.LOCAL_MAILBOX_SIMULATOR), 1)
        sent_mail = auth_secure.LOCAL_MAILBOX_SIMULATOR[0]
        self.assertIn("http://localhost:8502/?verify_token=", sent_mail["body_html"])

    def test_password_reset_link_contains_8502(self):
        """Assert password reset links are routed to port 8502 for icrop2 sandbox."""
        # Register and verify account
        auth_secure.register_secure_user(
            username="reset_8502", email="reset8502@test.com", password="password123", name="Reset User", workplace="BOKU"
        )
        with self.db.get_connection() as conn:
            conn.execute("UPDATE users SET is_verified = 1 WHERE username = 'reset_8502'")
            conn.commit()
            
        auth_secure.LOCAL_MAILBOX_SIMULATOR.clear()
        
        # Request password reset
        success, msg = auth_secure.request_password_reset("reset8502@test.com")
        self.assertTrue(success)
        self.assertEqual(len(auth_secure.LOCAL_MAILBOX_SIMULATOR), 1)
        sent_mail = auth_secure.LOCAL_MAILBOX_SIMULATOR[0]
        self.assertIn("http://localhost:8502/?reset_token=", sent_mail["body_html"])

    def test_session_token_persistence_verification(self):
        """Assert session tokens are written on login and can be verified to load canonical payloads."""
        username = "token_tester"
        email = "tok@test.com"
        password = "secret_password_123"
        
        # Register and verify account
        auth_secure.register_secure_user(
            username=username, email=email, password=password, name="Token Tester", workplace="BOKU"
        )
        with self.db.get_connection() as conn:
            conn.execute("UPDATE users SET is_verified = 1 WHERE username = ?", (username,))
            conn.commit()
            
        # Log in to generate token
        success, msg, payload = auth_secure.authenticate_secure_user(username, password)
        self.assertTrue(success)
        self.assertIsNotNone(payload)
        
        session_token = payload.get("session_token")
        self.assertIsNotNone(session_token)
        self.assertEqual(len(session_token), 48)  # secrets.token_hex(24) returns 48 chars
        
        # Verify the session token in database
        verify_success, verify_payload = auth_secure.verify_session_token(session_token)
        self.assertTrue(verify_success)
        self.assertIsNotNone(verify_payload)
        self.assertEqual(verify_payload["user_id"], payload["user_id"])
        self.assertEqual(verify_payload["username"], username)
        self.assertEqual(verify_payload["email"], email)
        self.assertEqual(verify_payload["session_key"], payload["session_key"])
        
        # Test verification of unregistered/invalid token
        fail_success, fail_payload = auth_secure.verify_session_token("fake_token_hex_123")
        self.assertFalse(fail_success)
        self.assertIsNone(fail_payload)

if __name__ == "__main__":
    unittest.main()

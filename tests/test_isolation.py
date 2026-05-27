import unittest
import os
import sys

# Add icrop2 folder to sys.path to resolve imports cleanly
current_dir = os.path.dirname(os.path.abspath(__file__))
icrop2_dir = os.path.abspath(os.path.join(current_dir, ".."))
if icrop2_dir not in sys.path:
    sys.path.insert(0, icrop2_dir)

from core.model_engine import SSMiCropEngine
from utils.db_manager import DatabaseManager

class TestIsolation(unittest.TestCase):
    """
    Asserts complete system isolation of iCrop 2.
    """

    def test_database_routing(self):
        """
        Verify that database connections strictly route to app_v2.db inside icrop2 folder,
        ensuring zero crossovers or writing to the original app.db.
        """
        db = DatabaseManager()
        
        # Assert database path resolves to app_v2.db
        self.assertTrue(db.db_path.endswith("app_v2.db"))
        
        # Assert database path is inside icrop2 directory
        normalized_path = os.path.normpath(db.db_path)
        normalized_icrop2 = os.path.normpath(icrop2_dir)
        self.assertIn(normalized_icrop2, normalized_path)
        
        # Verify it does not mix with old app.db
        self.assertNotIn("app.db", normalized_path)

if __name__ == "__main__":
    unittest.main()

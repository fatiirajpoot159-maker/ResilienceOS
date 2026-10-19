import sys, unittest
import uuid
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
import database

class BackendSecurityAndIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_db()

    def test_owner_first_admin_rule(self):
        # Verify has_admin_user works
        has_admin = database.has_admin_user()
        # If no admin, registering an account makes it admin
        if not has_admin:
            owner_res = database.register_user('owner@test.com', 'Owner@123', 'Owner Account', 'Master Bakery')
            self.assertEqual(owner_res['user']['role'], 'admin')
            self.assertTrue(database.has_admin_user())

            # Second user must be strictly 'user'
            subsequent = database.register_user('subsequent@test.com', 'Pass@123', 'Regular User', 'Second Bakery')
            self.assertEqual(subsequent['user']['role'], 'user')

    def test_user_data_isolation(self):
        uid = uuid.uuid4().hex[:6]
        # Create User Alpha
        alpha_email = f'alpha_{uid}@test.com'
        alpha_res = database.register_user(alpha_email, 'Pass1234!', 'Alpha Baker', 'Alpha Bakery')
        alpha_user = alpha_res['user']

        # Create User Beta
        beta_email = f'beta_{uid}@test.com'
        beta_res = database.register_user(beta_email, 'Pass1234!', 'Beta Baker', 'Beta Bakery')
        beta_user = beta_res['user']

        # Alpha saves unique orders
        alpha_orders = [
            {'id': 'Alpha Croissants', 'duration': 3, 'deadline': 10, 'missed_penalty': 5000},
            {'id': 'Alpha Baguettes', 'duration': 4, 'deadline': 12, 'missed_penalty': 3000}
        ]
        database.replace_user_orders(alpha_user['id'], alpha_orders)

        # Beta saves different orders
        beta_orders = [
            {'id': 'Beta Cookies', 'duration': 2, 'deadline': 8, 'missed_penalty': 1500}
        ]
        database.replace_user_orders(beta_user['id'], beta_orders)

        # Verify Alpha orders
        loaded_alpha = database.get_user_orders(alpha_user['id'])
        self.assertEqual(len(loaded_alpha), 2)
        self.assertEqual(loaded_alpha[0]['id'], 'Alpha Croissants')

        # Verify Beta orders
        loaded_beta = database.get_user_orders(beta_user['id'])
        self.assertEqual(len(loaded_beta), 1)
        self.assertEqual(loaded_beta[0]['id'], 'Beta Cookies')

        # Verify cross-check: Alpha NEVER sees Beta's data
        self.assertNotIn('Beta Cookies', [o['id'] for o in loaded_alpha])
        self.assertNotIn('Alpha Croissants', [o['id'] for o in loaded_beta])

    def test_admin_access_control(self):
        uid = uuid.uuid4().hex[:6]
        regular = database.register_user(f'reg_{uid}@test.com', 'Pass123!', 'Regular Guy', 'Reg Biz')
        with self.assertRaises(PermissionError):
            database.get_admin_overview(regular['user'])

    def test_invalid_login(self):
        with self.assertRaises(ValueError):
            database.login_user('nonexistent_user_xyz@test.com', 'WrongPass')

if __name__ == '__main__':
    unittest.main()

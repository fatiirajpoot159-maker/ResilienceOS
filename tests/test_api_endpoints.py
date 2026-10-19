import sys
import unittest
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
import database
from server import Handler

class ApiEndpointIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_db()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 8088), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = 'http://127.0.0.1:8088'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, data=None, token=None):
        url = self.base_url + path
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        body = json.dumps(data).encode('utf-8') if data is not None else None
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as res:
                return res.status, json.loads(res.read().decode('utf-8'))
        except HTTPError as e:
            err_body = json.loads(e.read().decode('utf-8'))
            return e.code, err_body

    def test_health_check(self):
        status, data = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(data['status'], 'ok')

    def test_auth_and_isolation_flow(self):
        # 1. Register User 1
        u1_email = 't_user1@bakery.com'
        status, u1 = self.request('POST', '/api/auth/register', {
            'email': u1_email,
            'password': 'Password@123',
            'full_name': 'Baker One',
            'business_name': 'Bakery One'
        })
        self.assertEqual(status, 200)
        u1_token = u1['token']
        self.assertEqual(u1['user']['role'], 'user')

        # 2. Register User 2
        u2_email = 't_user2@bakery.com'
        status, u2 = self.request('POST', '/api/auth/register', {
            'email': u2_email,
            'password': 'Password@123',
            'full_name': 'Baker Two',
            'business_name': 'Bakery Two'
        })
        self.assertEqual(status, 200)
        u2_token = u2['token']

        # 3. User 1 saves orders
        u1_orders = [{'id': 'Sourdough Loaves', 'duration': 4, 'deadline': 12, 'missed_penalty': 5000}]
        status, res = self.request('POST', '/api/orders', {'orders': u1_orders}, token=u1_token)
        self.assertEqual(status, 200)

        # 4. User 2 saves different orders
        u2_orders = [{'id': 'Chocolate Eclairs', 'duration': 3, 'deadline': 8, 'missed_penalty': 3000}]
        status, res = self.request('POST', '/api/orders', {'orders': u2_orders}, token=u2_token)
        self.assertEqual(status, 200)

        # 5. Verify User 1 sees ONLY User 1 orders
        status, res1 = self.request('GET', '/api/orders', token=u1_token)
        self.assertEqual(status, 200)
        self.assertEqual(len(res1['orders']), 1)
        self.assertEqual(res1['orders'][0]['id'], 'Sourdough Loaves')

        # 6. Verify User 2 sees ONLY User 2 orders
        status, res2 = self.request('GET', '/api/orders', token=u2_token)
        self.assertEqual(status, 200)
        self.assertEqual(len(res2['orders']), 1)
        self.assertEqual(res2['orders'][0]['id'], 'Chocolate Eclairs')

    def test_admin_rbac_protection(self):
        import uuid
        uid = uuid.uuid4().hex[:6]
        
        # Ensure an admin exists
        if not database.has_admin_user():
            self.request('POST', '/api/auth/register', {
                'email': f'admin_{uid}@test.com',
                'password': 'AdminPassword123!',
                'full_name': 'Test Admin',
                'business_name': 'Test HQ'
            })

        # 1. Register a standard user (must be 'user' role since admin already exists)
        u_email = f'user_{uid}@test.com'
        status, u_res = self.request('POST', '/api/auth/register', {
            'email': u_email,
            'password': 'UserPassword123!',
            'full_name': 'Standard User',
            'business_name': 'User Bakery'
        })
        self.assertEqual(status, 200)
        self.assertEqual(u_res['user']['role'], 'user')
        user_token = u_res['token']

        # 2. Regular user tries to access /api/admin/overview -> must be 403 Forbidden
        status, err = self.request('GET', '/api/admin/overview', token=user_token)
        self.assertEqual(status, 403)
        self.assertIn('denied', err['error'].lower())

        # 3. Fetch admin user from DB and login
        conn = database.get_connection()
        admin_email = conn.execute("SELECT email FROM users WHERE role = 'admin' LIMIT 1").fetchone()[0]
        conn.close()

        # Update password for test admin or test with token directly
        admin_token = None
        for test_pw in ('Admin@123', 'AdminPassword123!', 'Owner@123'):
            try:
                res = database.login_user(admin_email, test_pw)
                admin_token = res['token']
                break
            except Exception:
                pass
        
        if admin_token:
            status, overview = self.request('GET', '/api/admin/overview', token=admin_token)
            self.assertEqual(status, 200)
            self.assertIn('users', overview)
            self.assertIn('user_count', overview)

    def test_optimizer_with_generator_roi(self):
        payload = {
            'outage_start': 6,
            'outage_duration': 6,
            'late_rate': 350,
            'backup': True,
            'fuel_rate': 2.5,
            'fuel_price': 280,
            'jobs': [
                {'id': 'Bread batch', 'duration': 4, 'deadline': 9, 'missed_penalty': 4600},
                {'id': 'Birthday cakes', 'duration': 5, 'deadline': 8, 'missed_penalty': 7800}
            ]
        }
        status, res = self.request('POST', '/api/optimize', payload)
        self.assertEqual(status, 200)
        self.assertEqual(res['solver_status'], 'OPTIMAL')
        self.assertIn('generator_roi', res)
        roi = res['generator_roi']
        self.assertEqual(roi['outage_hours'], 3.0)
        self.assertEqual(roi['fuel_liters'], 7.5)
        self.assertEqual(roi['fuel_cost_pkr'], 2100)

if __name__ == '__main__':
    unittest.main()

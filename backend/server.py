"""
ResilienceOS Enterprise Server.
Provides:
1. Exact DP single-machine optimization engine with optional generator ROI analysis.
2. Complete local SQL authentication & session management (PBKDF2-HMAC-SHA256).
3. Strict multi-tenant user data isolation (orders & simulations).
4. Protected Administrator control endpoints (RBAC).
5. Static frontend asset delivery.
"""
import json
import traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from engine import calculate
import database

ROOT = Path(__file__).resolve().parent.parent / 'frontend'

# Initialize SQLite database and seed defaults on startup
database.init_db()

class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for local workflows
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def reply(self, status, body, typ='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', typ)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def get_auth_user(self):
        auth_header = self.headers.get('Authorization', '')
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()
        
        if not token:
            # Fallback check query params or cookies if needed
            return None
        return database.get_user_from_token(token)

    def read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length < 1 or length > 500000:
            raise ValueError('Invalid payload length')
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8'))

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path

        # 1. API Health Check
        if path == '/api/health':
            return self.reply(200, {
                'status': 'ok',
                'app': 'ResilienceOS Enterprise',
                'database': 'SQLite Connected',
                'auth': 'Integrated RBAC'
            })

        # 1.1 System Admin Status Check
        if path == '/api/system/status':
            return self.reply(200, {
                'has_admin': database.has_admin_user()
            })

        # 2. Authenticated user profile: GET /api/auth/me
        if path == '/api/auth/me':
            user = self.get_auth_user()
            if not user:
                return self.reply(401, {'error': 'Not authenticated'})
            return self.reply(200, {'user': user})

        # 3. User isolated orders: GET /api/orders
        if path == '/api/orders':
            user = self.get_auth_user()
            if not user:
                return self.reply(401, {'error': 'Sign in to access your orders.'})
            orders = database.get_user_orders(user['id'])
            return self.reply(200, {'orders': orders})

        # 4. User isolated simulations: GET /api/simulations
        if path == '/api/simulations':
            user = self.get_auth_user()
            if not user:
                return self.reply(401, {'error': 'Sign in to access your simulations.'})
            sims = database.get_user_simulations(user['id'], limit=30)
            return self.reply(200, {'simulations': sims})

        # 5. Admin Overview: GET /api/admin/overview
        if path == '/api/admin/overview':
            user = self.get_auth_user()
            if not user:
                return self.reply(401, {'error': 'Authentication required.'})
            try:
                overview = database.get_admin_overview(user)
                return self.reply(200, overview)
            except PermissionError as pe:
                return self.reply(403, {'error': str(pe)})
            except Exception as e:
                return self.reply(500, {'error': str(e)})

        # 6. Admin Audit Logs: GET /api/admin/audit-logs
        if path == '/api/admin/audit-logs':
            user = self.get_auth_user()
            if not user:
                return self.reply(401, {'error': 'Authentication required.'})
            try:
                overview = database.get_admin_overview(user)
                return self.reply(200, {'audit_logs': overview.get('audit_logs', [])})
            except PermissionError as pe:
                return self.reply(403, {'error': str(pe)})

        # 7. Static file delivery
        file_map = {
            '/': 'index.html',
            '/index.html': 'index.html',
            '/app.js': 'app.js',
            '/auth.js': 'auth.js',
            '/config.js': 'Config.js',
            '/Config.js': 'Config.js',
            '/styles.css': 'styles.css',
            '/ui-extra.css': 'ui-extra.css',
            '/bakery-hero.jpg': 'bakery-hero.jpg'
        }
        filename = file_map.get(path)
        if filename is None:
            return self.reply(404, {'error': 'File not found'})

        target = ROOT / filename
        if not target.exists():
            return self.reply(404, {'error': f'{filename} not found'})

        typ = 'image/jpeg' if filename.endswith('.jpg') else (
            'text/html; charset=utf-8' if filename.endswith('.html') else (
                'text/css; charset=utf-8' if filename.endswith('.css') else 'application/javascript; charset=utf-8'
            )
        )
        return self.reply(200, target.read_bytes(), typ)

    def do_POST(self):
        parsed = urlsplit(self.path)
        path = parsed.path

        try:
            # 1. Optimizer endpoint
            if path == '/api/optimize':
                payload = self.read_json_body()
                result = calculate(payload)

                # Optional Generator ROI calculation
                fuel_rate = float(payload.get('fuel_rate', 0))
                fuel_price = float(payload.get('fuel_price', 0))
                if payload.get('backup') and fuel_rate > 0 and fuel_price > 0:
                    outage_duration_slots = int(payload.get('outage_duration', 0))
                    hours = (outage_duration_slots * 30.0) / 60.0
                    liters = round(hours * fuel_rate, 2)
                    fuel_cost = round(liters * fuel_price)
                    net_savings = result['savings'] - fuel_cost
                    result['generator_roi'] = {
                        'outage_hours': hours,
                        'fuel_liters': liters,
                        'fuel_cost_pkr': fuel_cost,
                        'net_benefit_pkr': net_savings,
                        'is_beneficial': net_savings > 0
                    }

                return self.reply(200, result)

            # 2. Auth: Register
            if path == '/api/auth/register':
                body = self.read_json_body()
                email = body.get('email', '')
                password = body.get('password', '')
                full_name = body.get('full_name', '')
                business_name = body.get('business_name', 'My Bakery')
                role = body.get('role', 'user')

                res = database.register_user(email, password, full_name, business_name, role)
                return self.reply(200, res)

            # 3. Auth: Login
            if path == '/api/auth/login':
                body = self.read_json_body()
                email = body.get('email', '')
                password = body.get('password', '')
                res = database.login_user(email, password)
                return self.reply(200, res)

            # 4. Auth: Logout
            if path == '/api/auth/logout':
                auth_header = self.headers.get('Authorization', '')
                token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else auth_header.strip()
                database.logout_user(token)
                return self.reply(200, {'status': 'logged_out'})

            # 5. Orders: Replace / Save
            if path == '/api/orders':
                user = self.get_auth_user()
                if not user:
                    return self.reply(401, {'error': 'Sign in to save orders.'})
                body = self.read_json_body()
                orders_list = body.get('orders', [])
                updated = database.replace_user_orders(user['id'], orders_list)
                return self.reply(200, {'status': 'success', 'orders': updated})

            # 6. Simulations: Save
            if path == '/api/simulations':
                user = self.get_auth_user()
                if not user:
                    return self.reply(401, {'error': 'Sign in to record simulation.'})
                body = self.read_json_body()
                scenario = body.get('scenario', {})
                result = body.get('result', {})
                database.save_user_simulation(user['id'], scenario, result)
                return self.reply(200, {'status': 'simulation_recorded'})

            # 7. Admin: Change User Role
            if path == '/api/admin/user/role':
                user = self.get_auth_user()
                if not user:
                    return self.reply(401, {'error': 'Authentication required.'})
                body = self.read_json_body()
                target_user_id = body.get('user_id')
                new_role = body.get('role')
                try:
                    database.set_user_role(user, target_user_id, new_role)
                    return self.reply(200, {'status': 'role_updated'})
                except PermissionError as pe:
                    return self.reply(403, {'error': str(pe)})
                except ValueError as ve:
                    return self.reply(400, {'error': str(ve)})

            return self.reply(404, {'error': f'Endpoint not found: {path}'})

        except ValueError as ve:
            return self.reply(400, {'error': str(ve)})
        except Exception as e:
            return self.reply(500, {'error': f'Server error: {str(e)}'})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8000))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f'ResilienceOS Enterprise running on port {port}...')
    ThreadingHTTPServer((host, port), Handler).serve_forever()

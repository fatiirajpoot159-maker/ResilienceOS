# ResilienceOS — Industrial Operations & Disruption Intelligence

**Team Innovatrix | Exact DP Optimizer + Multi-Tenant User Isolation + Protected Admin Control Center**

ResilienceOS is a production-grade web application designed for bakeries and manufacturing facilities that face frequent power outages and load shedding. It uses mathematical single-machine dynamic programming to re-order production schedules, minimize late delivery penalties, and evaluate backup generator ROI in real time.

---

## 🚀 Key Highlights & Architectural Features

1. **Strict Multi-Tenant User Isolation**:
   - Each registered account receives an isolated, private workspace.
   - Orders and simulations saved by User A are **never accessible** to User B.
   - Data is stored in a transactional SQLite engine with foreign keys, indexes, and full relational integrity.

2. **Role-Based Admin Governance (RBAC)**:
   - **Admin Access Only**: The Admin Control Center is strictly hidden from regular operators and enforced with server-side HTTP 403 authorization.
   - Pre-seeded System Administrator: `admin@resilienceos.com` / `Admin@123`.
   - Admins can monitor system KPIs (Total Users, Businesses, Orders, Simulations, Modeled Rupee Savings), inspect registered users, toggle user roles, examine global outage simulation trends, and review security audit logs.

3. **Authentic Security & Cryptography**:
   - Passwords securely hashed with **PBKDF2-HMAC-SHA256** and unique cryptographic salt per user.
   - Cryptographically random session tokens (64-character hex) with automatic expiration and token validation.
   - Password visibility toggles, input validation, and real-time error reporting.

4. **Advanced Industrial Capabilities**:
   - **Generator & Fuel ROI Calculator**: Automatically computes diesel fuel expense vs prevented penalties to evaluate whether running a generator is economically profitable.
   - **Outage Presets**: 1-click presets for common load shedding windows (Summer Peak 2.5h, Severe Grid Outage 4h, Morning Feeder Trip 1.5h, Normal Shift).
   - **Printable Kitchen Work Order**: Clean dispatch schedule ready for physical bakery kitchen staff.
   - **CSV Import & Export**: Download order books to CSV or upload CSV files directly.
   - **Scenario JSON Backup**: Complete state serialization and export.

---

## ⚡ Quick Start

### 1. Launch the Server
Open a terminal in the project directory and run:
```bash
python backend/server.py
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## 🔑 Pre-Configured Test Accounts (1-Click Login Available)

On the login screen, you can click the quick demo buttons or enter credentials manually:

| Account Type | Email | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin@resilienceos.com` | `Admin@123` | Full Admin Console, User Governance, Audit Trail, Optimizer |
| **Bakery Operator** | `demo@bakery.com` | `Bakery@123` | Private Workspace, Custom Orders, Personal Simulations, Optimizer |
| **New Accounts** | *Any email via "Create account"* | *Your password* | Brand new private workspace with strict user isolation |

---

## 🧪 Automated Test Suite

Run the full suite of unit and integration tests (12 tests covering optimization DP, user isolation, RBAC, and REST API):
```bash
python -m unittest discover -s tests -v
```

---

## 📁 Project Architecture

- **`backend/server.py`**: Multi-threaded HTTP server delivering REST endpoints, RBAC checks, and static frontend assets.
- **`backend/database.py`**: SQLite relational engine with PBKDF2 hashing, session management, user isolation, and admin operations.
- **`backend/engine.py`**: Exact single-machine scheduling optimizer using memoized dynamic programming.
- **`frontend/index.html`**: Responsive UI with Welcome view, Authentication card, Command Center, and Admin Control Panel.
- **`frontend/auth.js`**: Client-side authentication manager, session state, user isolation CRUD, and admin dashboard rendering.
- **`frontend/app.js`**: Order management, timeline visualization, generator ROI engine, presets, and CSV handling.
- **`frontend/styles.css` & `frontend/ui-extra.css`**: Professional dark theme styling, responsive layouts, badges, and print stylesheets.
- **`tests/test_api_endpoints.py`**: End-to-end integration tests for all REST API endpoints and isolation.
- **`tests/test_backend.py`**: Security, PBKDF2 hashing, and multi-tenant isolation unit tests.
- **`tests/test_engine.py`**: Exact solver mathematical verification and schedule constraints tests.

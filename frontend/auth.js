/* ResilienceOS Authentication & Multi-Tenant Isolation Controller.
 * Supports integrated zero-dependency local SQLite RBAC engine with complete user data isolation.
 */
(() => {
  const el = id => document.getElementById(id);
  
  let currentUser = null;
  let authToken = localStorage.getItem('resilience_auth_token') || null;
  let signupMode = false;
  let adminDataCache = null;
  let systemHasAdmin = true;

  async function checkAdminStatus() {
    try {
      const res = await fetch('/api/system/status');
      const data = await res.json();
      systemHasAdmin = !!data.has_admin;
      if (el('ownerSetupNotice')) {
        el('ownerSetupNotice').hidden = systemHasAdmin;
      }
    } catch (_) {}
  }

  const errorText = e => e?.message || String(e);

  function setMessage(msg, isError = false) {
    const box = el('authMessage');
    if (!box) return;
    box.textContent = msg;
    box.style.display = msg ? 'block' : 'none';
    box.style.color = isError ? '#ff8585' : '#73d13d';
    box.style.background = isError ? 'rgba(255, 77, 79, 0.12)' : 'rgba(82, 196, 26, 0.12)';
    box.style.border = isError ? '1px solid rgba(255, 77, 79, 0.3)' : '1px solid rgba(82, 196, 26, 0.3)';
  }

  function show(view) {
    el('welcome').hidden = view !== 'welcome';
    el('authView').hidden = view !== 'auth';
    el('workspace').hidden = view !== 'app';
    if (view === 'app') window.scrollTo(0, 0);
  }

  function changeMode(isSignup) {
    signupMode = isSignup;
    el('authTitle').textContent = isSignup ? 'Create your account' : 'Welcome back';
    el('authSub').textContent = isSignup 
      ? 'Start with your own private, isolated workspace.' 
      : 'Sign in to access your saved orders & simulations.';
    el('authSubmit').textContent = isSignup ? 'Create account →' : 'Sign in →';
    el('authSwitch').textContent = isSignup ? 'Already registered? Sign in' : 'New here? Create account';
    el('signupFields').hidden = !isSignup;
    el('confirmPwdWrap').hidden = !isSignup;
    el('authName').required = isSignup;
    el('authPassword').autocomplete = isSignup ? 'new-password' : 'current-password';
    
    // Always clear input values so no credentials remain pre-filled
    el('authEmail').value = '';
    el('authPassword').value = '';
    if (el('authName')) el('authName').value = '';
    if (el('authBizName')) el('authBizName').value = '';
    if (el('authConfirmPassword')) el('authConfirmPassword').value = '';

    // If no admin exists in the system yet, guide owner through master setup
    if (!systemHasAdmin) {
      signupMode = true;
      el('authTitle').textContent = '👑 Initial Owner Setup';
      el('authSub').textContent = 'Create your Master Administrator account. You will have exclusive full access to the Admin panel.';
      el('authSubmit').textContent = 'Register Master Admin →';
      el('signupFields').hidden = false;
      el('confirmPwdWrap').hidden = false;
      el('authSwitch').hidden = true;
      if (el('ownerSetupNotice')) el('ownerSetupNotice').hidden = false;
    } else {
      el('authSwitch').hidden = false;
      if (el('ownerSetupNotice')) el('ownerSetupNotice').hidden = true;
    }

    setMessage('');
    show('auth');
  }

  // Navigation handlers
  el('showLogin').onclick = async () => { await checkAdminStatus(); changeMode(false); };
  el('showSignup').onclick = async () => { await checkAdminStatus(); changeMode(true); };
  el('startSignup').onclick = async () => { await checkAdminStatus(); changeMode(true); };
  el('backHome').onclick = () => show('welcome');
  el('authSwitch').onclick = () => changeMode(!signupMode);

  // Password visibility toggle
  const pwdInput = el('authPassword');
  const toggleBtn = el('togglePasswordBtn');
  if (toggleBtn && pwdInput) {
    toggleBtn.onclick = () => {
      const isPwd = pwdInput.type === 'password';
      pwdInput.type = isPwd ? 'text' : 'password';
      toggleBtn.textContent = isPwd ? '🔒' : '👁';
    };
  }

  // Demo Preview from welcome screen
  el('tryDemo').onclick = () => {
    currentUser = {
      id: 'demo_session',
      email: 'preview@bakery.com',
      full_name: 'Guest Bakery Operator',
      role: 'user',
      business_name: 'Sample Artisan Bakery'
    };
    authToken = null;
    applyUserContext(currentUser);
    jobs = structuredClone(defaultJobs);
    renderJobs();
    show('app');
    el('cloudStatus').textContent = 'Preview Mode. Click "Save orders to my account" after creating an account to persist in cloud.';
    run();
  };

  // API Request Helper with Bearer Token
  async function apiCall(endpoint, method = 'GET', body = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(endpoint, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `HTTP ${res.status}: ${res.statusText}`);
    }
    return data;
  }

  // Authentication Submission
  async function handleAuth(event) {
    event.preventDefault();
    const email = el('authEmail').value.trim();
    const password = el('authPassword').value;
    const submitBtn = el('authSubmit');

    submitBtn.disabled = true;
    setMessage('Authenticating…');

    try {
      if (signupMode) {
        const full_name = el('authName').value.trim();
        const business_name = el('authBizName').value.trim() || 'My Bakery';
        const confirm = el('authConfirmPassword').value;

        if (password !== confirm) {
          throw new Error('Passwords do not match.');
        }

        const data = await apiCall('/api/auth/register', 'POST', {
          email,
          password,
          full_name,
          business_name
        });

        authToken = data.token;
        localStorage.setItem('resilience_auth_token', authToken);
        await enterApp(data.user);
      } else {
        const data = await apiCall('/api/auth/login', 'POST', {
          email,
          password
        });

        authToken = data.token;
        localStorage.setItem('resilience_auth_token', authToken);
        await enterApp(data.user);
      }
    } catch (e) {
      setMessage(errorText(e), true);
    } finally {
      submitBtn.disabled = false;
    }
  }
  el('authForm').onsubmit = handleAuth;

  // Forgot password handler
  el('forgotPassword').onclick = () => {
    const email = el('authEmail').value.trim();
    if (!email) {
      setMessage('Enter your email address in the field above first.', true);
      return;
    }
    setMessage(`Password recovery instructions sent to ${email} (simulated). You can also log in using the demo pills.`, false);
  };

  // Apply User UI state
  function applyUserContext(user) {
    currentUser = user;
    const isAdmin = user.role === 'admin';

    // Topbar
    el('topUserName').textContent = user.full_name || user.email;
    el('topUserRole').textContent = isAdmin ? 'ADMIN' : 'OPERATOR';
    el('topUserRole').className = `role-badge ${isAdmin ? 'admin' : 'user'}`;
    
    // Avatar initials
    const initials = (user.full_name || user.email)
      .split(' ')
      .map(p => p[0])
      .join('')
      .substring(0, 2)
      .toUpperCase();
    el('topUserAvatar').textContent = initials;
    el('topUserAvatar').className = `user-avatar-circle ${isAdmin ? 'admin' : ''}`;

    // Sidebar
    el('sidebarBizName').textContent = `♨  ${user.business_name || 'My Bakery'}`;
    el('sidebarRoleIndicator').textContent = isAdmin ? '● ADMIN CONSOLE' : '● OPERATOR WORKSPACE';
    el('sidebarRoleIndicator').style.color = isAdmin ? '#ffd666' : '#6adcb3';

    // Role-protected Navigation
    el('adminSidebarNav').hidden = !isAdmin;
    el('adminNav').hidden = !isAdmin;
    if (!isAdmin) {
      el('adminPanel').hidden = true;
    }

    // Cloud panel
    el('cloudUser').textContent = `Signed in as ${user.full_name} (${user.email})`;
    el('cloudBiz').textContent = `Business Workspace: ${user.business_name || 'Artisan Bakery'}`;
    el('accountRoleTag').textContent = isAdmin ? 'SYSTEM ADMINISTRATOR' : 'BUSINESS OPERATOR';
    el('accountRoleTag').className = `role-badge ${isAdmin ? 'admin' : 'user'}`;
    el('cloudStatus').textContent = 'Connected. Multi-tenant database active. Data is strictly isolated to your user ID.';
  }

  // Enter App Session
  async function enterApp(user) {
    applyUserContext(user);
    show('app');

    // Load current user's isolated orders
    try {
      await loadUserOrders();
    } catch (e) {
      console.warn('Orders load:', e);
    }

    // If Admin, pre-fetch admin overview data
    if (user.role === 'admin') {
      try {
        await refreshAdmin();
      } catch (e) {
        console.warn('Admin fetch:', e);
      }
    }
  }

  // Load User Orders
  async function loadUserOrders() {
    if (!authToken) return;
    try {
      const data = await apiCall('/api/orders');
      if (Array.isArray(data.orders) && data.orders.length > 0) {
        jobs = data.orders;
        renderJobs();
        el('cloudStatus').textContent = `Loaded ${jobs.length} private orders from your database.`;
        run();
      } else {
        // If brand new account with 0 orders, load sample bakery orders
        jobs = structuredClone(defaultJobs);
        renderJobs();
        el('cloudStatus').textContent = 'New workspace initialized with sample bakery orders. Click "Save orders to my account" to persist.';
        run();
      }
    } catch (e) {
      el('cloudError').textContent = 'Could not load orders: ' + errorText(e);
    }
  }

  // Save User Orders
  async function saveUserOrders() {
    if (!authToken) {
      el('cloudError').textContent = 'Please sign in or create an account to save orders.';
      return;
    }
    el('cloudError').textContent = '';
    try {
      const res = await apiCall('/api/orders', 'POST', { orders: jobs });
      el('cloudStatus').textContent = `Successfully saved ${jobs.length} orders to your private account.`;
      el('cloudError').textContent = '';
    } catch (e) {
      el('cloudError').textContent = 'Failed to save orders: ' + errorText(e);
    }
  }
  el('cloudSave').onclick = saveUserOrders;
  el('cloudLoad').onclick = loadUserOrders;

  // Save Simulation
  window.persistSimulation = async (scenario, result) => {
    if (!authToken || !currentUser) return;
    try {
      await apiCall('/api/simulations', 'POST', { scenario, result });
      el('cloudStatus').textContent = 'Simulation recorded to your account history.';
    } catch (e) {
      console.warn('Simulation persist error:', e);
    }
  };

  // Load Simulations History
  el('cloudHistory').onclick = async () => {
    if (!authToken) {
      el('cloudError').textContent = 'Sign in to view your simulation history.';
      return;
    }
    const list = el('cloudHistoryList');
    list.replaceChildren();
    try {
      const data = await apiCall('/api/simulations');
      const sims = data.simulations || [];
      if (!sims.length) {
        list.textContent = 'No saved simulations found for this account. Run an optimization to create one.';
        return;
      }

      for (const item of sims) {
        const chip = document.createElement('div');
        chip.className = 'sim-chip';
        chip.title = 'Click to reload this simulation';
        const dateStr = new Date(item.created_at).toLocaleString();
        chip.innerHTML = `<span>⚡ ${dateStr}</span> <strong>Saved Rs ${Number(item.savings).toLocaleString()}</strong>`;
        
        chip.onclick = () => {
          if (item.scenario.jobs) {
            jobs = structuredClone(item.scenario.jobs);
            renderJobs();
          }
          if (item.scenario.outage_start !== undefined) el('outageStart').value = item.scenario.outage_start;
          if (item.scenario.outage_duration !== undefined) el('outageDuration').value = item.scenario.outage_duration;
          if (item.scenario.late_rate !== undefined) el('lateRate').value = item.scenario.late_rate;
          if (item.scenario.backup !== undefined) {
            el('backup').checked = !!item.scenario.backup;
            if (el('generatorBox')) el('generatorBox').hidden = !el('backup').checked;
          }
          renderResult(item.result);
          el('cloudStatus').textContent = `Historical simulation from ${dateStr} restored.`;
        };
        list.append(chip);
      }
    } catch (e) {
      el('cloudError').textContent = 'Could not load simulations: ' + errorText(e);
    }
  };

  // Sign out
  async function logout() {
    try {
      if (authToken) await apiCall('/api/auth/logout', 'POST');
    } catch (_) {}
    authToken = null;
    currentUser = null;
    localStorage.removeItem('resilience_auth_token');
    jobs = [];
    renderJobs();
    el('cloudHistoryList').replaceChildren();
    el('adminPanel').hidden = true;
    el('adminSidebarNav').hidden = true;
    show('welcome');
  }
  el('cloudLogout').onclick = logout;
  el('topLogoutBtn').onclick = logout;

  // ADMIN DASHBOARD CONTROLLER (STRICTLY ADMIN ONLY)
  el('adminNav').onclick = () => {
    if (!currentUser || currentUser.role !== 'admin') {
      alert('Access Denied: Only administrators have permission to access this area.');
      return;
    }
    el('adminPanel').hidden = false;
    el('adminPanel').scrollIntoView({ behavior: 'smooth' });
    refreshAdmin();
  };

  el('adminSidebarNav').onclick = (e) => {
    e.preventDefault();
    if (!currentUser || currentUser.role !== 'admin') {
      alert('Access Denied: Only administrators have permission to access this area.');
      return;
    }
    el('adminPanel').hidden = false;
    el('adminPanel').scrollIntoView({ behavior: 'smooth' });
    refreshAdmin();
  };

  el('refreshAdmin').onclick = () => refreshAdmin();

  // Admin Tab Navigation
  el('tabUsersBtn').onclick = () => switchAdminTab('users');
  el('tabSimsBtn').onclick = () => switchAdminTab('sims');
  el('tabAuditBtn').onclick = () => switchAdminTab('audit');

  function switchAdminTab(tab) {
    el('tabUsersBtn').className = `admin-tab ${tab === 'users' ? 'active' : ''}`;
    el('tabSimsBtn').className = `admin-tab ${tab === 'sims' ? 'active' : ''}`;
    el('tabAuditBtn').className = `admin-tab ${tab === 'audit' ? 'active' : ''}`;

    el('adminUsersTabSection').hidden = tab !== 'users';
    el('adminSimsTabSection').hidden = tab !== 'sims';
    el('adminAuditTabSection').hidden = tab !== 'audit';
  }

  // Refresh and Render Admin Data
  async function refreshAdmin() {
    if (!currentUser || currentUser.role !== 'admin') return;
    el('adminError').textContent = '';

    try {
      const data = await apiCall('/api/admin/overview');
      adminDataCache = data;

      // Update KPI stat counters
      el('adminStatUsers').textContent = data.user_count || 0;
      el('adminStatBiz').textContent = data.business_count || 0;
      el('adminStatOrders').textContent = data.order_count || 0;
      el('adminStatSims').textContent = data.simulation_count || 0;
      el('adminStatSavings').textContent = 'Rs ' + Number(data.total_savings_pkr || 0).toLocaleString('en-PK');

      // Render Users Table
      renderAdminUsers(data.users || []);

      // Render Simulations Table
      renderAdminSimulations(data.recent_simulations || []);

      // Render Audit Logs Table
      renderAdminAuditLogs(data.audit_logs || []);
    } catch (e) {
      el('adminError').textContent = 'Admin data load error: ' + errorText(e);
    }
  }

  // Render Admin Users Table
  function renderAdminUsers(users) {
    const target = el('adminUsers');
    target.replaceChildren();

    const searchTerm = (el('adminUserSearch').value || '').toLowerCase().trim();
    const filtered = users.filter(u => 
      (u.name && u.name.toLowerCase().includes(searchTerm)) ||
      (u.email && u.email.toLowerCase().includes(searchTerm)) ||
      (u.business_name && u.business_name.toLowerCase().includes(searchTerm))
    );

    if (!filtered.length) {
      target.textContent = 'No matching users found.';
      return;
    }

    const table = document.createElement('table');
    table.innerHTML = `
      <thead>
        <tr>
          <th>NAME</th>
          <th>EMAIL</th>
          <th>ROLE</th>
          <th>BUSINESS</th>
          <th>ORDERS</th>
          <th>SIMS</th>
          <th>REGISTERED</th>
          <th>LAST SIGN IN</th>
          <th>ACTIONS</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;

    const tbody = table.querySelector('tbody');

    for (const u of filtered) {
      const tr = document.createElement('tr');
      const isTargetAdmin = u.role === 'admin';
      const isSelf = currentUser && currentUser.id === u.id;

      const regDate = u.created_at ? new Date(u.created_at).toLocaleDateString() : '—';
      const lastLogin = u.last_sign_in_at ? new Date(u.last_sign_in_at).toLocaleString() : 'Never';

      tr.innerHTML = `
        <td><strong>${u.name || '—'}</strong></td>
        <td>${u.email}</td>
        <td><span class="role-badge ${isTargetAdmin ? 'admin' : 'user'}">${u.role}</span></td>
        <td>${u.business_name || 'My Bakery'}</td>
        <td>${u.order_count || 0}</td>
        <td>${u.simulation_count || 0}</td>
        <td>${regDate}</td>
        <td><small>${lastLogin}</small></td>
        <td></td>
      `;

      const actionTd = tr.querySelector('td:last-child');
      if (!isSelf) {
        const toggleBtn = document.createElement('button');
        toggleBtn.className = `action-btn-small ${isTargetAdmin ? 'demote' : ''}`;
        toggleBtn.textContent = isTargetAdmin ? 'Demote to User' : 'Promote to Admin';
        toggleBtn.onclick = async () => {
          const nextRole = isTargetAdmin ? 'user' : 'admin';
          if (!confirm(`Are you sure you want to change ${u.email}'s role to ${nextRole.toUpperCase()}?`)) return;
          try {
            await apiCall('/api/admin/user/role', 'POST', { user_id: u.id, role: nextRole });
            await refreshAdmin();
          } catch (err) {
            alert('Error updating role: ' + errorText(err));
          }
        };
        actionTd.append(toggleBtn);
      } else {
        actionTd.innerHTML = '<span style="color:#8faec9;font-size:11px;">Current Session</span>';
      }

      tbody.append(tr);
    }
    target.append(table);
  }

  // Filter users on typing
  el('adminUserSearch').oninput = () => {
    if (adminDataCache && adminDataCache.users) {
      renderAdminUsers(adminDataCache.users);
    }
  };

  // Render Admin Simulations Table
  function renderAdminSimulations(sims) {
    const target = el('adminSimulationsTable');
    target.replaceChildren();

    if (!sims.length) {
      target.textContent = 'No simulations recorded yet in the network.';
      return;
    }

    const table = document.createElement('table');
    table.innerHTML = `
      <thead>
        <tr>
          <th>USER EMAIL</th>
          <th>BUSINESS</th>
          <th>OUTAGE DURATION</th>
          <th>BACKUP POWER</th>
          <th>PREVENTED LOSS</th>
          <th>TIMESTAMP</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector('tbody');
    for (const s of sims) {
      const tr = document.createElement('tr');
      const backupText = s.backup ? '✅ Generator Active' : '❌ No Backup';
      tr.innerHTML = `
        <td>${s.user_email}</td>
        <td>${s.business_name || 'Bakery'}</td>
        <td>${s.outage_duration * 30} mins (${s.outage_duration} slots)</td>
        <td>${backupText}</td>
        <td><strong style="color:#7ef0dc;">Rs ${Number(s.savings).toLocaleString('en-PK')}</strong></td>
        <td><small>${new Date(s.created_at).toLocaleString()}</small></td>
      `;
      tbody.append(tr);
    }
    target.append(table);
  }

  // Render Admin Audit Logs Table
  function renderAdminAuditLogs(logs) {
    const target = el('adminAuditLogs');
    target.replaceChildren();

    if (!logs.length) {
      target.textContent = 'No audit events recorded yet.';
      return;
    }

    const table = document.createElement('table');
    table.innerHTML = `
      <thead>
        <tr>
          <th>TIMESTAMP</th>
          <th>USER / ACTOR</th>
          <th>ACTION</th>
          <th>DETAILS</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector('tbody');
    for (const l of logs) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><small>${new Date(l.timestamp).toLocaleString()}</small></td>
        <td>${l.user_email || 'System'}</td>
        <td><span style="font-weight:700;color:#ffd666;">${l.action}</span></td>
        <td>${l.details || '—'}</td>
      `;
      tbody.append(tr);
    }
    target.append(table);
  }

  // Auto-login on page load if token is saved in localStorage
  async function initSession() {
    await checkAdminStatus();
    if (!authToken) {
      show('welcome');
      return;
    }
    try {
      const data = await apiCall('/api/auth/me');
      if (data && data.user) {
        await enterApp(data.user);
      } else {
        show('welcome');
      }
    } catch (_) {
      localStorage.removeItem('resilience_auth_token');
      authToken = null;
      show('welcome');
    }
  }

  initSession();
})();

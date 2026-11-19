// DATA CACHE & STATE
let CACHED_STATUS_DATA = {};
let CACHED_LIBRARY_DATA = [];
let CACHED_SPLS = [];
let currentFilterKind = 'all';
let searchQuery = '';
let currentSPL = [];
let currentSPL_TITLE = "";
let currentSPL_UUID = null;
let USE_12H_FORMAT = localStorage.getItem('tms_pref_time_12h') === 'true'; // Load from storage
let CURRENT_LANG = localStorage.getItem('tms_pref_lang') || 'en';
let WS_CONN = null;
const API_BASE = window.location.origin;
let VIEW_DATE = new Date(); // Global for Visual Schedule

const TRANSLATIONS = {
    'en': {
        // NAV
        'nav_dash': 'Cinema Overview',
        'nav_timeline': 'Visual Grid Schedule',
        'nav_content': 'Global Library (LMS)',
        'nav_scheduler': 'Central Scheduler',
        'nav_kdm': 'KDM Manager',
        'nav_auto': 'Cinema Automation',
        'nav_spl': 'SPL Management & Library',
        'nav_config': 'Auditorium Management',
        'nav_system': 'System Settings',
        'nav_about': 'About & System',
        // DESC
        'desc_dash': 'Real-time status of all auditoriums',
        'desc_timeline': 'Visual timeline of shows across all auditoriums',
        'desc_content': 'Global CPL and Asset inventory',
        'desc_scheduler': 'Global show programming',
        'desc_kdm': 'Status of cryptographic keys across screens',
        'desc_auto': 'Facilities and auditorium triggers',
        'desc_spl': 'Build, edit, and distribute show playlists',
        'desc_config': 'Fleet management and server config',
        'desc_system': 'General preferences and localization',
        'desc_about': 'System Information and Legal',
        // GENERAL
        'save': 'Save',
        'saved': 'Saved',
        'loading': 'Loading...',
        'error': 'Error',
        'status_playing': 'Playing',
        'status_stopped': 'Stopped',
        'status_offline': 'Offline',
        'status_online': 'Online',
        'lbl_total_screens': 'Total Screens',
        'lbl_now_playing': 'Now Playing',
        'lbl_alerts': 'Alerts',
        // SETTINGS
        'lbl_time_format': 'Time Format',
        'lbl_language': 'System Language',
        'lbl_theme': 'Theme Preference',
        'lbl_logs': 'Log Retention',
        'hint_time': 'Updates the clock display across the application.',
        'hint_theme': 'Theme switching coming in next release.',
        'opt_24h': '24-Hour (13:00)',
        'opt_12h': '12-Hour (1:00 PM)',
        'opt_dark': 'Cinema Dark (Default)',
        'opt_light': 'Daylight Mode',
        'days_7': '7 Days',
        'days_30': '30 Days',
        'days_90': '90 Days'
    },
    'id': {
        // NAV
        'nav_dash': 'Tinjauan Bioskop',
        'nav_timeline': 'Jadwal Visual',
        'nav_content': 'Pustaka Global (LMS)',
        'nav_scheduler': 'Penjadwalan Pusat',
        'nav_kdm': 'Manajer KDM',
        'nav_auto': 'Otomasi Bioskop',
        'nav_spl': 'Manajemen SPL & Pustaka',
        'nav_config': 'Manajemen Auditorium',
        'nav_system': 'Pengaturan Sistem',
        // DESC
        'desc_dash': 'Status waktu nyata semua auditorium',
        'desc_timeline': 'Garis waktu visual pertunjukan di semua layar',
        'desc_content': 'Inventaris CPL dan Aset Global',
        'desc_scheduler': 'Pemrograman pertunjukan global',
        'desc_kdm': 'Status kunci kriptografis di semua layar',
        'desc_auto': 'Pemicu fasilitas dan auditorium',
        'desc_spl': 'Buat, edit, dan distribusikan daftar putar',
        'desc_config': 'Manajemen armada dan konfigurasi server',
        'desc_system': 'Preferensi umum dan lokalisasi',
        // GENERAL
        'save': 'Simpan',
        'saved': 'Tersimpan',
        'loading': 'Memuat...',
        'error': 'Kesalahan',
        'status_playing': 'Memutar',
        'status_stopped': 'Berhenti',
        'status_offline': 'Offline',
        'status_online': 'Online',
        'lbl_total_screens': 'Total Layar',
        'lbl_now_playing': 'Sedang Tayang',
        'lbl_alerts': 'Peringatan',
        // SETTINGS
        'lbl_time_format': 'Format Waktu',
        'lbl_language': 'Bahasa Sistem',
        'lbl_theme': 'Preferensi Tema',
        'lbl_logs': 'Retensi Log',
        'hint_time': 'Memperbarui tampilan jam di aplikasi.',
        'hint_theme': 'Penggantian tema hadir di rilis berikutnya.',
        'opt_24h': '24-Jam (13:00)',
        'opt_12h': '12-Jam (1:00 PM)',
        'opt_dark': 'Cinema Gelap (Bawaan)',
        'opt_light': 'Mode Terang',
        'days_7': '7 Hari',
        'days_30': '30 Hari',
        'days_90': '90 Hari'
    },
    'es': {
        // NAV
        'nav_dash': 'Resumen de Cine',
        'nav_timeline': 'Horario Visual',
        'nav_content': 'Biblioteca Global (LMS)',
        'nav_scheduler': 'Programador Central',
        'nav_kdm': 'Gestor de KDM',
        'nav_auto': 'Automatización',
        'nav_spl': 'Gestión de SPL',
        'nav_config': 'Gestión de Auditorios',
        'nav_system': 'Configuración del Sistema',
        // DESC
        'desc_dash': 'Estado en tiempo real de todos los auditorios',
        // ... (Truncated for brevity, falling back to English for missing)
    }
};




// THEME MANAGEMENT


function t(key) {
    const lang = TRANSLATIONS[CURRENT_LANG] || TRANSLATIONS['en'];
    return lang[key] || TRANSLATIONS['en'][key] || key;
}


// GLOBAL TOGGLE FUNCTION (MUST BE TOP LEVEL)
window.toggleSidebar = function () {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const COLLAPSE_KEY = 'tms_sidebar_collapsed';

    if (!sidebar) return;

    // Desktop logic (Collapsed)
    if (window.innerWidth > 768) {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem(COLLAPSE_KEY, sidebar.classList.contains('collapsed'));
        // Ensure mobile class is removed if switching from mobile to desktop
        sidebar.classList.remove('mobile-open');
        if (overlay) overlay.classList.remove('active');
    }
    // Mobile logic (Drawer)
    else {
        // First ensure it's not collapsed in mobile mode
        sidebar.classList.remove('collapsed');

        const isOpen = sidebar.classList.toggle('mobile-open');
        if (overlay) {
            if (isOpen) {
                overlay.classList.add('active');
                // Prevent background scrolling when drawer is open
                document.body.style.overflow = 'hidden';
            } else {
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
        }
    }
};

window.logout = async function () {
    showConfirmModal('Logout from Cinema Suite?', async () => {
        try {
            await apiFetch('/api/logout', { method: 'POST' });
        } catch (e) { }
        localStorage.removeItem('tms_token');
        localStorage.removeItem('tms_user');
        window.location.href = 'login.html';
    });
};

function localizeUI() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });
    enforceRBAC();
}

function enforceRBAC() {
    const userStr = localStorage.getItem('tms_user');
    if (!userStr) return;

    try {
        const user = JSON.parse(userStr);
        const priv = user.privilege || 'Operator';
        const levels = { 'Operator': 1, 'Manager': 2, 'Admin': 3 };
        const userLevel = levels[priv] || 1;

        document.querySelectorAll('[data-min-priv]').forEach(el => {
            const minPriv = el.getAttribute('data-min-priv');
            const requiredLevel = levels[minPriv] || 1;

            if (userLevel < requiredLevel) {
                el.style.display = 'none';
            } else {
                el.style.display = ''; // Reset to default
            }
        });
    } catch (e) { console.error("RBAC Error:", e); }
}


const TAB_DESCRIPTIONS = {
    'tms-dash': 'desc_dash',
    'tms-timeline': 'desc_timeline',
    'tms-content': 'desc_content',
    'tms-scheduler': 'desc_scheduler',
    'tms-kdm': 'desc_kdm',
    'tms-auto': 'desc_auto',
    'tms-spl': 'desc_spl',
    'tms-config': 'desc_config',
    'tms-system': 'desc_system',
    'tms-about': 'desc_about'
};

const TAB_TITLES = {
    'tms-dash': 'nav_dash',
    'tms-timeline': 'nav_timeline',
    'tms-content': 'nav_content',
    'tms-scheduler': 'nav_scheduler',
    'tms-kdm': 'nav_kdm',
    'tms-auto': 'nav_auto',
    'tms-spl': 'nav_spl',
    'tms-config': 'nav_config',
    'tms-system': 'nav_system',
    'tms-about': 'nav_about'
};


let syncTimer = null;
const TIMELINE_START_HOUR = 8; // 08:00 AM
const PX_PER_MIN = 5; // 300px per hour
// Globals moved to top




// Auth Guard - Redirect if not logged in
if (!localStorage.getItem('tms_token') && !window.location.pathname.includes('login.html')) {
    window.location.href = '/login.html';
}

async function apiFetch(url, options = {}) {
    const token = localStorage.getItem('tms_token');
    if (!options.headers) options.headers = {};
    if (token) options.headers['Authorization'] = token;

    const res = await fetch(url, options);
    if (res.status === 401) {
        localStorage.removeItem('tms_token');
        localStorage.removeItem('tms_user');
        window.location.href = '/login.html';
        throw new Error('Unauthorized');
    }
    return res;
}

// Redeclarations removed - moved to top

function initWebSocket() {
    if (WS_CONN) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log("🔌 Connecting to TMS Real-Time Stream...");
    WS_CONN = new WebSocket(wsUrl);

    WS_CONN.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'status') {
                handleRealtimeStatus(msg.data);
            }
        } catch (e) { console.error("WS Message Error:", e); }
    };

    WS_CONN.onclose = () => {
        WS_CONN = null;
        console.warn("🔌 WS Disconnected. Retrying in 5s...");
        setTimeout(initWebSocket, 5000);
    };

    WS_CONN.onerror = (err) => {
        console.error("WS Error:", err);
    };
}

function handleRealtimeStatus(newData) {
    if (JSON.stringify(CACHED_STATUS_DATA) === JSON.stringify(newData)) return;

    console.log("📡 Real-time update received - Refreshing View");
    CACHED_STATUS_DATA = newData;
    renderViews(); // Trigger UI Refresh
}

// 1. Digital Clock System
let clockInterval = null;

function initSystemClock() {
    const parent = document.querySelector('.top-actions');
    if (!parent) return;

    // Use existing clock container if present, otherwise create (fallback)
    let clockContainer = document.getElementById('rosetta-clock');

    if (!clockContainer) {
        // Fallback creation logic
        clockContainer = document.createElement('div');
        clockContainer.id = 'rosetta-clock';
        clockContainer.className = 'rosetta-clock-badge';
        clockContainer.innerHTML = `
            <span class="time">00:00:00</span>
            <span class="date">LOADING...</span>
        `;
        parent.prepend(clockContainer);
    }

    // UPDATE FUNCTION
    const updateClock = () => {
        const now = new Date();
        const timeStr = now.toLocaleTimeString(CURRENT_LANG === 'id' ? 'id-ID' : 'en-GB', { hour12: USE_12H_FORMAT });
        const dayStr = now.toLocaleDateString(CURRENT_LANG === 'id' ? 'id-ID' : 'en-GB', { weekday: 'short' }).toUpperCase();
        const dateStr = now.toLocaleDateString(CURRENT_LANG === 'id' ? 'id-ID' : 'en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });

        const timeEl = clockContainer.querySelector('.time');
        const dateEl = clockContainer.querySelector('.date');

        if (timeEl) timeEl.innerText = timeStr; // Use innerText for atomic update

        // Update date plain and simple
        if (dateEl) {
            dateEl.textContent = `${dayStr} ${dateStr}`;
        }
    };

    // Run Immediately
    updateClock();

    // Clear existing to be safe
    if (clockInterval) clearInterval(clockInterval);

    // Start Interval
    clockInterval = setInterval(updateClock, 1000);
}

// CUSTOM DROPDOWN INIT
function initCustomDropdowns(specificSelect = null) {
    const selects = specificSelect ? [specificSelect] : document.querySelectorAll('select:not(.custom-select-processed), .tms-select-refresh');

    selects.forEach(select => {
        // Clean up old wrapper if refreshing
        if (select.classList.contains('custom-select-processed')) {
            const oldWrapper = select.closest('.tms-select');
            if (oldWrapper) {
                oldWrapper.parentNode.insertBefore(select, oldWrapper);
                oldWrapper.remove();
            }
        }

        select.classList.add('custom-select-processed');
        select.classList.remove('tms-select-refresh');
        select.style.display = 'none';

        // Container
        const wrapper = document.createElement('div');
        wrapper.className = 'tms-select';
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);

        // Trigger
        const trigger = document.createElement('div');
        trigger.className = 'tms-select-trigger';
        // HTML arrow
        const arrow = `
            <svg class="tms-select-arrow" viewBox="0 0 24 24">
                <path d="M6 9l6 6 6-6"></path>
            </svg>
        `;
        const selectedOption = select.options[select.selectedIndex];
        trigger.innerHTML = `<span>${selectedOption ? selectedOption.text : 'Select...'}</span> ${arrow}`;
        wrapper.appendChild(trigger);

        // Options List
        const optionsList = document.createElement('div');
        optionsList.className = 'tms-options';
        wrapper.appendChild(optionsList);

        Array.from(select.options).forEach(opt => {
            const optEl = document.createElement('div');
            optEl.className = 'tms-option';
            if (opt.selected) optEl.classList.add('selected');
            optEl.textContent = opt.text;
            optEl.dataset.value = opt.value;

            optEl.addEventListener('click', (e) => {
                e.stopPropagation();
                // Update Select
                select.value = opt.value;
                select.dispatchEvent(new Event('change'));

                // Update UI
                trigger.querySelector('span').textContent = opt.text;
                wrapper.classList.remove('open');

                // Update Selected State
                wrapper.querySelectorAll('.tms-option').forEach(el => el.classList.remove('selected'));
                optEl.classList.add('selected');
            });

            optionsList.appendChild(optEl);
        });

        // Toggle
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            // Close other dropdowns
            document.querySelectorAll('.tms-select').forEach(el => {
                if (el !== wrapper) el.classList.remove('open');
            });
            wrapper.classList.toggle('open');
        });
    });

    // Close on click outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.tms-select')) {
            document.querySelectorAll('.tms-select').forEach(el => el.classList.remove('open'));
        }
    });
}


// --- USER MANAGEMENT LOGIC ---
async function initUserManagement() {
    await fetchUsers();

    // ADD USER FORM
    const addForm = document.getElementById('add-user-form');
    if (addForm) {
        addForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('new-user-name').value;
            const email = document.getElementById('new-user-email').value;
            const password = document.getElementById('new-user-pass').value;
            const privilege = document.getElementById('new-user-role').value;

            try {
                const res = await apiFetch('/api/users/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, password, privilege })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    closeAddUserModal();
                    addForm.reset();
                    fetchUsers();
                } else {
                    alert('Error adding user');
                }
            } catch (err) {
                console.error(err);
                alert('Connection Failed');
            }
        });
    }

    // EDIT USER FORM
    const editForm = document.getElementById('edit-user-form');
    if (editForm) {
        editForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('edit-user-id').value;
            const username = document.getElementById('edit-user-name').value;
            const email = document.getElementById('edit-user-email').value;
            const password = document.getElementById('edit-user-pass').value;
            const privilege = document.getElementById('edit-user-role').value;

            try {
                const res = await apiFetch('/api/users/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id, username, email, password, privilege })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    closeEditUserModal();
                    fetchUsers();
                } else {
                    alert('Error updating user: ' + (data.error || 'Unknown'));
                }
            } catch (err) {
                alert('Connection Failed');
            }
        });
    }
}

// Store users globally for easier access
let GLOBAL_USERS = [];

async function fetchUsers() {
    try {
        const res = await apiFetch('/api/users');
        const data = await res.json();
        const tbody = document.getElementById('user-list-body');
        if (!tbody) return;

        GLOBAL_USERS = data.users || []; // Store data
        console.log('Users fetched:', GLOBAL_USERS);

        tbody.innerHTML = '';
        if (GLOBAL_USERS.length > 0) {
            GLOBAL_USERS.forEach(u => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><code>${u.id}</code></td>
                    <td style="font-weight: 600;">${u.username}</td>
                    <td>${u.email}</td>
                    <td><span class="status-badge" style="background: #e0f2fe; color: #0284c7; border: none;">${u.privilege}</span></td>
                    <td style="text-align: right; display: flex; gap: 8px; justify-content: flex-end;">
                        <button class="btn-action edit" onclick="openEditUserModal('${u.id}')" title="Edit User">
                            <i class="fas fa-pencil-alt"></i>
                        </button>
                        <button class="btn-action delete" onclick="deleteUser('${u.id}')" title="Delete User">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--text-muted);">No users found.</td></tr>';
        }
    } catch (err) {
        console.error(err);
    }
}

async function deleteUser(id) {
    if (!confirm('Are you sure you want to delete this user?')) return;
    try {
        const res = await apiFetch('/api/users/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.status === 'ok') fetchUsers();
        else alert('Failed to delete');
    } catch (err) {
        alert('Connection error');
    }
}

function openAddUserModal() {
    const modal = document.getElementById('modal-add-user');
    if (modal) {
        modal.classList.add('active');
        // Initialize dropdowns locally if needed, or rely on global init
        initCustomDropdowns();
    }
}

function closeAddUserModal() {
    const modal = document.getElementById('modal-add-user');
    if (modal) modal.classList.remove('active');
}

// EDIT MODAL LOGIC
function openEditUserModal(userId) {
    console.log('Attempting to edit user with ID:', userId);
    console.log('Current Global Users:', GLOBAL_USERS);

    // Ensure strict type matching is not the issue by converting both to strings
    const user = GLOBAL_USERS.find(u => String(u.id) === String(userId));

    if (!user) {
        console.error('User not found in global cache!');
        alert('Error: User data not found. Please refresh.');
        return;
    }

    console.log('User found:', user);

    const modal = document.getElementById('modal-edit-user');
    if (modal) {
        document.getElementById('edit-user-id').value = user.id;
        document.getElementById('edit-user-name').value = user.username;
        document.getElementById('edit-user-email').value = user.email;
        document.getElementById('edit-user-role').value = user.privilege;
        document.getElementById('edit-user-pass').value = '';

        modal.classList.add('active');
        initCustomDropdowns();

        // MANUALLY UPDATE DROPDOWN UI
        const roleSelect = document.getElementById('edit-user-role');
        if (roleSelect && roleSelect.nextElementSibling && roleSelect.nextElementSibling.classList.contains('tms-select')) {
            const triggerSpan = roleSelect.nextElementSibling.querySelector('.tms-select-trigger span');
            if (triggerSpan) {
                const selectedText = roleSelect.options[roleSelect.selectedIndex].text;
                triggerSpan.textContent = selectedText;

                // Update selected class in options list
                const wrapper = roleSelect.nextElementSibling;
                wrapper.querySelectorAll('.tms-option').forEach(opt => {
                    if (opt.dataset.value === user.privilege) opt.classList.add('selected');
                    else opt.classList.remove('selected');
                });
            }
        }
    } else {
        console.error('Edit modal not found in DOM');
    }
}

function closeEditUserModal() {
    const modal = document.getElementById('modal-edit-user');
    if (modal) modal.classList.remove('active');
}

// --- INITIALIZATION ---
// Redeclarations removed - moved to top/bottom consolidated block

// Redundant DOMContentLoaded removed - consolidating at the bottom

// PASSWORD TOGGLE
function togglePasswordVisibility(inputId, icon) {
    const input = document.getElementById(inputId);
    if (input) {
        const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
        input.setAttribute('type', type);
        icon.classList.toggle('fa-eye');
        icon.classList.toggle('fa-eye-slash');
    }
}



async function fetchTMSData() {
    try {
        const [statusRes, libraryRes] = await Promise.all([
            apiFetch(`${API_BASE}/api/status`),
            apiFetch(`${API_BASE}/api/library`)
        ]);

        CACHED_STATUS_DATA = await statusRes.json();
        const libData = await libraryRes.json();
        CACHED_LIBRARY_DATA = Array.isArray(libData) ? libData : (libData.data || []);

        renderViews();

        const updateEl = document.getElementById('last-update');
        if (updateEl) updateEl.textContent = new Date().toLocaleTimeString();
    } catch (e) {
        console.error("TMS Sync Error:", e);
    }
}

function renderViews() {
    const activeBtn = document.querySelector('.nav-item.active');
    if (!activeBtn) return;
    const activeTab = activeBtn.dataset.tab;

    if (activeTab === 'tms-dash') {
        renderTheaterGrid(CACHED_STATUS_DATA);
        updateSummary(CACHED_STATUS_DATA);
    } else if (activeTab === 'tms-content') {
        renderGlobalLibrary(CACHED_LIBRARY_DATA);
    } else if (activeTab === 'tms-spl') {
        fetchLocalSPLs(); // Fetch & Render Gallery
        renderSPLEditor();
    } else if (activeTab === 'tms-timeline') {
        // Init Date Nav if missing
        renderDateNavControl();
        // Load data for current view date
        loadScheduleData();
    } else if (activeTab === 'tms-scheduler') {
        renderCentralScheduler(CACHED_STATUS_DATA);
    } else if (activeTab === 'tms-config') {
        renderAuditoriumConfig();
    } else if (activeTab === 'tms-auto') {
        loadAutomationRules();
    }
}

// SMARTER AUTOMATION (Step 5)
async function loadAutomationRules() {
    const container = document.getElementById('view-tms-auto');
    if (!container) return;

    // Show template
    container.innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3><i class="fas fa-bolt"></i> Cinema Automation Rules</h3>
                <button class="btn-primary" onclick="openAddRuleModal()">
                    <i class="fas fa-plus"></i> Add Rule
                </button>
            </div>
            <div class="card-body">
                <div id="automation-list" class="automation-grid">
                    <div class="loading-state">
                        <div class="spinner"></div>
                        <p>Syncing automation engine...</p>
                    </div>
                </div>
            </div>
        </div>
    `;

    try {
        const res = await apiFetch('/api/automation');
        const data = await res.json();
        if (data.status === 'ok') {
            renderAutomationList(data.rules);
        }
    } catch (e) {
        console.error("Failed to load automation rules:", e);
    }
}

function renderAutomationList(rules) {
    const list = document.getElementById('automation-list');
    if (!list) return;

    if (!rules || rules.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-robot fa-3x" style="color: var(--text-muted); opacity: 0.3; margin-bottom: 20px;"></i>
                <p>No automation rules configured yet.</p>
                <small>Rules can be based on schedules or system triggers.</small>
            </div>
        `;
        return;
    }

    list.innerHTML = rules.map(rule => `
        <div class="automation-card ${rule.enabled ? 'enabled' : 'disabled'}">
            <div class="rule-info">
                <div class="rule-icon"><i class="fas ${rule.type === 'schedule' ? 'fa-clock' : 'fa-bolt'}"></i></div>
                <div class="rule-details">
                    <div class="rule-name">${rule.name}</div>
                    <div class="rule-meta">${rule.type === 'schedule' ? rule.time : 'Trigger'} • ${rule.action}</div>
                </div>
            </div>
            <div class="rule-actions">
                <div class="tms-switch" onclick="toggleRule('${rule.id}')">
                    <input type="checkbox" ${rule.enabled ? 'checked' : ''}>
                    <span class="slider round"></span>
                </div>
                <button class="btn-icon" onclick="deleteRule('${rule.id}')"><i class="fas fa-trash"></i></button>
            </div>
        </div>
    `).join('');
}

async function toggleRule(id) {
    try {
        const res = await apiFetch(`/api/automation/toggle?id=${id}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            showNotification(`Rule ${data.enabled ? 'Enabled' : 'Disabled'}`, 'success');
            loadAutomationRules(); // Refresh
        }
    } catch (e) {
        showNotification('Failed to toggle rule', 'error');
    }
}

async function deleteRule(id) {
    if (!confirm('Delete this automation rule?')) return;
    try {
        const res = await apiFetch('/api/automation/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            showNotification('Rule deleted', 'success');
            loadAutomationRules();
        }
    } catch (e) {
        showNotification('Failed to delete rule', 'error');
    }
}

// Placeholder for future development
window.openAddRuleModal = () => {
    showNotification('Automation Rule Builder coming soon!', 'info');
};

// SYSTEM SETTINGS (NEW)
// SYSTEM SETTINGS (NEW)
// Initialize Settings View with values
// Initialize Settings View with values
function renderGeneralPreferences() {
    const timeSel = document.getElementById('sys-time-format');
    const langSel = document.getElementById('sys-language');
    const logSel = document.getElementById('sys-logs');

    // Force values from Global State (initialized from LocalStorage)
    if (timeSel) timeSel.value = USE_12H_FORMAT ? '12' : '24';
    if (langSel) langSel.value = CURRENT_LANG;
    if (logSel) logSel.value = localStorage.getItem('tms_pref_logs') || '30';


    // Apply translations to the Settings Page itself (Labels & Options)
    // This part assumes we will add IDs or data-i18n attributes to the HTML
    // For now, let's just make sure dropdowns stick.
}


function saveSystemSetting(key, elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const value = el.value;

    // Save to LocalStorage
    if (key === 'time_format') {
        localStorage.setItem('tms_pref_time_12h', value === '12');
    } else if (key === 'language') {
        localStorage.setItem('tms_pref_lang', value);
    } else if (key === 'logs') {
        localStorage.setItem('tms_pref_logs', value);
    }



    // Auto Refresh as requested
    // "saat di save auto refres"
    location.reload();
}

// TAB STATE MANAGEMENT
function initTabState() {
    const savedTab = localStorage.getItem('tms_active_tab');
    if (savedTab) {
        // Activation handled by main switchTab call on load
        console.log("Restoring tab state:", savedTab);
    }
}


// AUDITORIUM MANAGEMENT (OLD SYSTEM SETTINGS)
let SELECTED_SCREEN_ID = null;



function updateSummary(data) {
    const screens = Object.values(data);
    const playingCount = screens.filter(s => s.playback === 'Playing').length;

    const totalEl = document.getElementById('stat-total');
    if (totalEl) totalEl.textContent = screens.length;

    const playingEl = document.getElementById('stat-playing');
    if (playingEl) playingEl.textContent = playingCount;

    const alerts = screens.filter(s => s.status === 'Offline').length;
    const alertEl = document.getElementById('stat-alerts');
    if (alertEl) alertEl.textContent = alerts;
}
// 8. Date Navigation Logic
function renderDateNavControl() {
    // New Placement: Inside the .timeline-toolbar
    const toolbar = document.querySelector('.timeline-toolbar');
    if (!toolbar) return;

    // Check if controls already exist
    if (document.getElementById('date-nav-ctrl')) return;

    // Format VIEW_DATE for input value
    const y = VIEW_DATE.getFullYear();
    const m = String(VIEW_DATE.getMonth() + 1).padStart(2, '0');
    const d = String(VIEW_DATE.getDate()).padStart(2, '0');
    const dateStr = `${y}-${m}-${d}`;

    const navDiv = document.createElement('div');
    navDiv.id = 'date-nav-ctrl';
    navDiv.className = 'date-nav-ctrl';
    navDiv.innerHTML = `
        <button class="nav-btn" onclick="changeDate(-1)"><i class="fas fa-chevron-left"></i></button>
        <input type="date" id="date-picker" class="rosetta-date-picker" value="${dateStr}" onchange="onDatePick(this.value)">
        <button class="nav-btn" onclick="changeDate(1)"><i class="fas fa-chevron-right"></i></button>
        <button class="nav-btn today-btn" onclick="goToToday()">Today</button>
    `;

    // Append to toolbar
    toolbar.appendChild(navDiv);
}

function updateDateDisplay() {
    const picker = document.getElementById('date-picker');
    if (!picker) return;

    // Sync picker value with VIEW_DATE
    const y = VIEW_DATE.getFullYear();
    const m = String(VIEW_DATE.getMonth() + 1).padStart(2, '0');
    const d = String(VIEW_DATE.getDate()).padStart(2, '0');
    picker.value = `${y}-${m}-${d}`;
}

function onDatePick(val) {
    if (!val) return;
    VIEW_DATE = new Date(val);
    loadScheduleData();
}

function changeDate(delta) {
    VIEW_DATE.setDate(VIEW_DATE.getDate() + delta);
    updateDateDisplay();
    loadScheduleData();
}

function goToToday() {
    VIEW_DATE = new Date();
    USER_HAS_MANUALLY_SCROLLED = false; // Reset suppression when clicking Today
    updateDateDisplay();
    loadScheduleData();
}

async function loadScheduleData() {
    // 1. Render Skeleton IMMEDIATELY (using cached status/config if available)
    renderGridSchedule({});

    // Format YYYY-MM-DD
    const y = VIEW_DATE.getFullYear();
    const m = String(VIEW_DATE.getMonth() + 1).padStart(2, '0');
    const d = String(VIEW_DATE.getDate()).padStart(2, '0');
    const dateStr = `${y}-${m}-${d}`;

    try {
        const res = await apiFetch(`${API_BASE}/api/schedule?date=${dateStr}`);
        CACHED_SCHEDULE_VIEW = await res.json();
        renderGridSchedule(CACHED_SCHEDULE_VIEW);
    } catch (e) {
        console.error("Schedule Fetch Error:", e);
    }
}

function renderTheaterGrid(data) {
    const container = document.getElementById('theater-grid');
    if (!container) return;

    // Time Format Helper
    const fmt = (secs) => {
        if (!secs) return "00:00:00";
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const s = secs % 60;
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    };

    const screens = Object.values(data);
    // SORT BY ID (Timestamp based) to match creation order
    screens.sort((a, b) => (a.id || '').localeCompare(b.id || ''));

    if (screens.length === 0) {
        container.innerHTML = '<div class="loading-state"><p>No auditoriums configured.</p></div>';
        return;
    }

    container.innerHTML = screens.map(s => `
        <div class="theater-card ${s.status === 'Offline' ? 'offline' : ''}" data-id="${s.id}">
            <div class="card-header">
                <h3>${s.name}</h3>
                <span class="status-badge ${s.status.toLowerCase()}">${s.status}</span>
            </div>
            <div class="card-body">
                <div class="theater-ip">${s.ims_ip || s.ip || '0.0.0.0'}</div>
                <div class="major-stat">
                    <div class="stat-box">
                        <label>Lamp Power</label>
                        <div class="val" style="color:${s.lamp === 'ON' ? 'var(--success)' : 'inherit'}">${s.lamp}</div>
                    </div>
                    <div class="stat-box">
                        <label>Playback</label>
                        <div class="val">${s.playback === 'Playing' ? t('status_playing') : (s.playback === 'Stopped' ? t('status_stopped') : s.playback)}</div>
                    </div>
                </div>
                <div class="now-playing">
                    <div class="spl-name"><i class="fas fa-list-ul"></i> <span>${s.spl || '-'}</span></div>
                    <div class="cpl-name"><i class="fas fa-film ${s.playback === 'Playing' ? 'fa-spin' : ''}"></i> <span>${s.content || t('desc_dash')}</span></div>
                </div>

                <div class="progress-bar-container">
                    <div class="progress-bar" style="width: ${s.progress_pct || 0}%"></div>
                </div>
                <div class="time-meta">
                    <span>${fmt(s.progress)} / ${s.remaining || '--:--'}</span>
                </div>
            </div>
        </div>
    `).join('');

    // Attach Event Listeners
    container.querySelectorAll('.theater-card').forEach(card => {
        card.addEventListener('click', () => {
            const id = card.getAttribute('data-id');
            console.log("Card Clicked:", id);
            openTheaterControl(id);
        });
    });
}

function openTheaterControl(id) {
    // Loose equality for ID matching
    const screen = Object.values(CACHED_STATUS_DATA).find(s => s.id == id);
    if (!screen) {
        console.error("Screen not found for ID:", id);
        return;
    }

    const targetIp = screen.ims_ip || screen.ip;

    // TRACK OPEN MODAL FOR REALTIME UPDATES
    openControlId = id;

    document.getElementById('th-ctrl-title').innerHTML = `<i class="fas fa-desktop"></i> ${screen.name}`;

    const body = document.getElementById('th-ctrl-body');

    // Define splOptions BEFORE use
    let splOptions = '<option value="">Loading playlists...</option>';

    // First Render Structure
    body.innerHTML = `
        <div class="ctrl-split-layout">
            <!-- LEFT COLUMN: CONTROLS -->
            <div class="ctrl-left-col">
                <div class="ctrl-panel action-panel">
                    <h4>Playback Control</h4>
                    <div class="transport-controls" style="display:flex; justify-content:center; gap:8px; margin-bottom:12px;">
                        <button class="btn-ctrl" onclick="theaterAction('${id}', 'SkipBackward')" title="Previous Clip"><i class="fas fa-step-backward"></i></button>
                        <button class="btn-ctrl stop" onclick="theaterAction('${id}', 'Stop')" title="Stop"><i class="fas fa-stop"></i></button>
                        <button class="btn-ctrl play" onclick="theaterAction('${id}', 'Play')" title="Play"><i class="fas fa-play"></i></button>
                        <button class="btn-ctrl pause" onclick="theaterAction('${id}', 'Pause')" title="Pause"><i class="fas fa-pause"></i></button>
                        <button class="btn-ctrl" onclick="theaterAction('${id}', 'SkipForward')" title="Next Clip"><i class="fas fa-step-forward"></i></button>
                    </div>
                    
                    <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #e2e8f0; padding-top:12px; margin-top:12px;">
                         <button class="btn-ctrl" onclick="theaterAction('${id}', 'Eject')" style="width:auto; color:var(--danger); border-color:var(--danger);"><i class="fas fa-eject"></i> Eject SPL</button>
                    </div>

                    <h4 style="margin-top:16px">Automation</h4>
                    <div class="automation-grid" style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                        <button class="btn-ctrl" onclick="theaterAction('${id}', 'dowser_open')"><i class="fas fa-sun"></i> Open Dows.</button>
                        <button class="btn-ctrl" onclick="theaterAction('${id}', 'dowser_close')"><i class="fas fa-moon"></i> Close Dows.</button>
                        <button class="btn-ctrl" onclick="theaterAction('${id}', 'lamp_on')"><i class="fas fa-lightbulb"></i> Lamp ON</button>
                        <button class="btn-ctrl" onclick="theaterAction('${id}', 'lamp_off')"><i class="far fa-lightbulb"></i> Lamp OFF</button>
                    </div>

                    <button class="btn-remote" onclick="openRemoteInterface('${id}')">
                        <i class="fas fa-external-link-alt"></i> REMOTE ACCESS (UI / VNC)
                    </button>
                </div>

                <div class="ctrl-load-section">
                    <h4>Load Playlist</h4>
                    <div class="load-row">
                        <select id="ctrl-load-select">
                            ${splOptions}
                        </select>
                        <button class="btn-primary" onclick="loadSPLToTheater('${id}')"><i class="fas fa-upload"></i> Load</button>
                    </div>
                </div>
            </div>

            <!-- RIGHT COLUMN: PLAYLIST PROCESS -->
            <div class="ctrl-right-col">
                <div class="ctrl-playlist-section">
                    <h4><i class="fas fa-list-ol"></i> Server Process (Playlist Content)</h4>
                    <div id="ctrl-playlist-items" class="playlist-container">
                        <div style="text-align:center; padding:40px; color:var(--text-muted);">
                            <i class="fas fa-spinner fa-spin fa-2x"></i><br><br>
                            Fetching playlist material...
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const modal = document.getElementById('modal-theater-control');
    modal.querySelector('.modal').classList.add('theater-control');
    modal.classList.add('active');

    // Async Fetch Logic (Restored)
    console.log(`fetching SPLs for ${targetIp}...`);
    apiFetch(`/api/spls?host=${targetIp}`)
        .then(res => res.json())
        .then(spls => {
            console.log("SPL Data:", spls);
            const select = document.getElementById('ctrl-load-select');
            if (select) {
                // Ensure spls is an array
                const items = Array.isArray(spls) ? spls : [];

                if (items.length === 0) {
                    select.innerHTML = '<option value="">No playlists found on server</option>';
                } else {
                    select.innerHTML = '<option value="">Select a playlist...</option>' +
                        items.map(s => `<option value="${s.uuid}" data-title="${s.title}">${s.title}${s.duration ? ' (' + s.duration + ')' : ''}</option>`).join('');

                    // PRE-SELECT the currently loaded SPL if available
                    const currentSplId = screen.splId;
                    if (currentSplId && select.querySelector(`option[value="${currentSplId}"]`)) {
                        select.value = currentSplId;
                    }
                }
            }
        })
        .catch(e => {
            console.error("Fetch Error:", e);
            const select = document.getElementById('ctrl-load-select');
            if (select) select.innerHTML = `<option value="">Error: ${e.message || e}</option>`;
        });

    // START REALTIME PLAYLIST POLLING
    renderRealtimePlaylist(id);
    startPlaylistPolling(id);
}

let playlistPollTimer = null;
let lastKnownActiveCplId = null;

function startPlaylistPolling(id) {
    if (playlistPollTimer) clearInterval(playlistPollTimer);
    playlistPollTimer = setInterval(() => {
        if (!document.getElementById('modal-theater-control').classList.contains('active')) {
            clearInterval(playlistPollTimer);
            playlistPollTimer = null;
            return;
        }
        renderRealtimePlaylist(id);
    }, 2000); // Poll every 2 seconds
}

async function renderRealtimePlaylist(id) {
    const container = document.getElementById('ctrl-playlist-items');
    if (!container) return;

    try {
        const res = await apiFetch(`/api/theater/playlist?id=${id}`);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<div style="padding:10px; color:var(--danger); font-size:12px;">${data.error}</div>`;
            return;
        }

        if (!data.items || data.items.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--text-muted);">No items in currently loaded playlist.</div>`;
            return;
        }

        if (data.activeCplId) console.log(`🔍 Active CPL Sync: searching for ${data.activeCplId}`);
        let html = "";
        let foundActive = false;

        data.items.forEach((item, index) => {
            // Use precise element index if available from backend
            let isActive = false;
            if (data.activeElementIndex !== undefined && data.activeElementIndex !== null) {
                isActive = (index === data.activeElementIndex);
            } else {
                isActive = data.activeCplId && (item.uuid.toLowerCase() === data.activeCplId.toLowerCase());
            }

            const isPlayed = data.activeCplId && !foundActive && !isActive;
            if (isActive) foundActive = true;

            const catClass = item.category ? `cat-${item.category.toLowerCase()}` : '';

            html += `
                <div class="playlist-item ${isActive ? 'active' : ''} ${isPlayed ? 'played' : ''} ${catClass}" data-uuid="${item.uuid}">
                    <div class="cpl-icon">
                        <i class="fas ${isActive ? 'fa-compact-disc' :
                    (item.type === 'Automation' ? 'fa-bolt' :
                        (item.type === 'Cue' ? 'fa-flag' : 'fa-film'))
                }"></i>
                    </div>
                    <div class="cpl-title">
                        ${item.title}
                        ${item.type && item.type !== 'CPL' ? `<small style="display:block; font-size:10px; opacity:0.6;">${item.type}</small>` : ''}
                    </div>
                    ${isActive ? '<div class="active-tag" style="background:var(--primary); color:white; font-size:9px; padding:2px 6px; border-radius:4px; font-weight:800;">PLAYING</div>' : ''}
                </div>
            `;
        });

        container.innerHTML = html;

        // Auto Scroll to Active Item if changed
        if (data.activeCplId !== lastKnownActiveCplId) {
            lastKnownActiveCplId = data.activeCplId;
            const activeEl = container.querySelector('.playlist-item.active');
            if (activeEl) {
                activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

    } catch (e) {
        console.error("Playlist Render Error:", e);
    }
}

async function loadSPLToTheater(id) {
    const select = document.getElementById('ctrl-load-select');
    if (!select || !select.value) {
        showAlertModal("Please select a playlist first.");
        return;
    }

    const splUuid = select.value;
    const splTitle = select.options[select.selectedIndex].getAttribute('data-title') || select.options[select.selectedIndex].text;

    const screen = Object.values(CACHED_STATUS_DATA).find(s => s.id == id);
    if (!screen) return;

    try {
        const res = await apiFetch(`/api/theater/load?id=${id}&spl=${splUuid}`, { method: 'POST' });
        const data = await res.json();

        if (data.status === 'ok') {
            showAlertModal(`✓ Loading "${splTitle}" to ${screen.name}...\n\nCard will update automatically within 10 seconds.`);
        } else {
            showAlertModal(`✗ Load Failed: ${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        showAlertModal(`✗ Network Error: ${e.message}`);
    }
}

let rfb = null;

function openRemoteInterface(id) {
    const screen = Object.values(CACHED_STATUS_DATA).find(s => s.id == id || s.id === id.toString());
    if (!screen) return;

    const ip = screen.ims_ip || screen.ip;
    const model = (screen.server_model || "").toUpperCase();

    // Determine Mode: 'vnc' or 'web'
    let useVNC = false;

    if (screen.remote_mode === 'vnc') {
        useVNC = true;
    } else if (screen.remote_mode === 'web') {
        useVNC = false;
    } else {
        // Auto Mode
        useVNC = model.includes("SX3000");
    }

    // Disconnect old VNC if any
    if (rfb) {
        try { rfb.disconnect(); } catch (e) { }
        rfb = null;
    }

    // UI Updates
    document.getElementById('remote-viewer-title').innerHTML = `<i class="fas fa-desktop"></i> Remote Interface: ${screen.name} <span style="font-size:0.7em; opacity:0.6">(${ip})</span>`;
    const iframe = document.getElementById('remote-iframe');
    const vncCont = document.getElementById('vnc-container');
    const btnExternal = document.getElementById('btn-open-external');
    const statusDiv = vncCont.querySelector('p'); // FIX: Define statusDiv

    // Reset UI
    iframe.style.display = 'none';
    vncCont.style.display = 'none';
    iframe.src = 'about:blank';
    if (statusDiv) {
        statusDiv.innerText = "Connecting to Remote Display...";
        statusDiv.style.color = "";
    }
    vncCont.querySelector('i').style.color = "var(--primary)";

    // External Link setup (including Port)
    const serverPort = screen.server_port || 80;
    btnExternal.onclick = () => window.open(useVNC ? `vnc://${ip}` : `http://${ip}:${serverPort}`, '_blank');

    if (useVNC) {
        // VNC Mode
        vncCont.style.display = 'flex';
        const vncTarget = document.getElementById('noVNC_container');
        vncTarget.innerHTML = ''; // Clear

        const wsPort = 43730;
        const vncPort = screen.vnc_port || 5900;

        // Dynamic Proxy URL
        const refinedProxyUrl = `ws://${window.location.hostname}:${wsPort}/vnc?host=${ip}&port=${vncPort}`;

        console.log("Initializing noVNC to:", refinedProxyUrl);

        if (statusDiv) {
            statusDiv.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> Connecting to VNC at ${ip}:${vncPort}...`;
        }

        try {
            // @ts-ignore - RFB comes from CDN
            rfb = new RFB(vncTarget, refinedProxyUrl, {
                credentials: { password: '' }
            });

            rfb.scaleViewport = true;
            rfb.resizeSession = true;

            rfb.addEventListener("connect", () => {
                console.log("✅ VNC Connected to", ip);
                if (statusDiv) {
                    statusDiv.innerText = "CONNECTED (Remote Control Active)";
                    statusDiv.style.color = "#10b981"; // Green
                }
                vncCont.querySelector('i').style.color = "#10b981";
            });

            rfb.addEventListener("disconnect", (e) => {
                console.log("🔌 VNC Disconnected", e);
                if (statusDiv) {
                    statusDiv.innerText = "DISCONNECTED";
                    statusDiv.style.color = "var(--danger)";
                }
                vncCont.querySelector('i').style.color = "var(--danger)";
            });

        } catch (err) {
            console.error("noVNC Error:", err);
            if (statusDiv) statusDiv.innerText = "VNC Initialization Error";
        }
    } else {
        // Chrome Iframe Mode
        iframe.style.display = 'block';
        iframe.src = `http://${ip}:${serverPort}`;
        console.log(`Chrome Mode for ${ip} on port ${serverPort}`);

        // Add error handler for iframe
        iframe.onerror = () => {
            showAlertModal("Failed to load Web UI. Check network or Browser Security (Mixed Content).");
        };
    }

    document.getElementById('modal-remote-viewer').classList.add('active');
}

function refreshRemoteFrame() {
    const iframe = document.getElementById('remote-iframe');
    if (iframe && iframe.style.display !== 'none') {
        const oldSrc = iframe.src;
        iframe.src = 'about:blank';
        setTimeout(() => { iframe.src = oldSrc; }, 100);
    } else {
        // Refresh VNC means reconnecting
        const activeModal = document.getElementById('modal-remote-viewer');
        if (activeModal.classList.contains('active')) {
            openRemoteInterface(openControlId);
        }
    }
}

async function theaterAction(id, action) {
    const screen = Object.values(CACHED_STATUS_DATA).find(s => s.id === id);
    showConfirmModal(`Execute '${action}' on ${screen.name}?`, async () => {
        try {
            const res = await apiFetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: id,
                    command: action
                })
            });
            const data = await res.json();
            if (data.status === 'ok') showAlertModal("Command Sent!");
            else showAlertModal("Command Failed: " + data.error);
        } catch (e) {
            showAlertModal("Network Error: " + e);
        }
    });
}

async function loadSPLToTheater(id) {
    const select = document.getElementById('ctrl-load-select');
    const uuid = select.value;
    if (!uuid) return;

    const title = select.options[select.selectedIndex].getAttribute('data-title') || "Selected Playlist";

    showConfirmModal(`Load '${title}' to this theater?`, async () => {
        try {
            const res = await apiFetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: id,
                    command: 'load_spl',
                    uuid: uuid
                })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                // Force quick UI update
                const btn = document.querySelector('#ctrl-load-select + button');
                if (btn) {
                    const icon = btn.querySelector('i');
                    const oldClass = icon.className;
                    icon.className = 'fas fa-check';
                    setTimeout(() => icon.className = oldClass, 2000);
                }
            } else {
                showAlertModal("Load Failed: " + data.error);
            }
        } catch (e) {
            showAlertModal("Error: " + e);
        }
    });
}

function openCommander(ip) {
    const url = ip ? `http://localhost:43729/?host=${ip}` : 'http://localhost:43729/';
    window.open(url, '_blank');
}

// Timeline Drag to Scroll (X and Y)
// SPLIT PANE SCROLL SYNC
function initTimelineInteractions() {
    const leftBody = document.getElementById('left-body');
    const rightBody = document.getElementById('right-body');
    const rightHeader = document.getElementById('right-header');

    if (!leftBody || !rightBody || !rightHeader) return;

    // MASTER SCROLL HANDLER (Right Body controls everything)
    const onScroll = () => {
        // Vertical Sync -> Left Body
        leftBody.scrollTop = rightBody.scrollTop;

        // Horizontal Sync -> Right Header
        rightHeader.scrollLeft = rightBody.scrollLeft;

        // DETECT MANUAL SCROLL (Scrollbar or programmatic)
        if (!IS_PROGRAMMATIC_SCROLL) {
            USER_HAS_MANUALLY_SCROLLED = true;
        }
    };

    rightBody.addEventListener('scroll', onScroll);

    // WHEEL & TOUCH (Direct manual interaction)
    const onManualInteraction = () => {
        USER_HAS_MANUALLY_SCROLLED = true;
    };

    rightBody.addEventListener('wheel', onManualInteraction, { passive: true });
    rightBody.addEventListener('touchstart', onManualInteraction, { passive: true });
    rightHeader.addEventListener('wheel', onManualInteraction, { passive: true });


    // DRAG-TO-SCROLL (Applied to Right Body)
    let isDown = false;
    let startX, startY, scrollLeft, scrollTop;

    rightBody.addEventListener('mousedown', (e) => {
        isDown = true;
        USER_HAS_MANUALLY_SCROLLED = true; // User is manually interacting
        rightBody.classList.add('active');
        startX = e.pageX - rightBody.offsetLeft;
        startY = e.pageY - rightBody.offsetTop;
        scrollLeft = rightBody.scrollLeft;
        scrollTop = rightBody.scrollTop;
    });

    const stopDrag = () => {
        isDown = false;
        rightBody.classList.remove('active');
    };

    rightBody.addEventListener('mouseleave', stopDrag);
    rightBody.addEventListener('mouseup', stopDrag);

    rightBody.addEventListener('mousemove', (e) => {
        if (!isDown) return;
        e.preventDefault();
        const x = e.pageX - rightBody.offsetLeft;
        const y = e.pageY - rightBody.offsetTop;
        const walkX = (x - startX) * 1.5;
        const walkY = (y - startY) * 1.5;

        rightBody.scrollLeft = scrollLeft - walkX;
        rightBody.scrollTop = scrollTop - walkY;
    });

    // Allow dragging Header to scroll horizontally
    rightHeader.addEventListener('mousedown', (e) => {
        // Simple horizontal drag for header
        isDown = true;
        USER_HAS_MANUALLY_SCROLLED = true; // User is manually interacting
        startX = e.pageX - rightHeader.offsetLeft;
        scrollLeft = rightBody.scrollLeft;

        const onHeaderMove = (em) => {
            if (!isDown) return;
            em.preventDefault();
            const x = em.pageX - rightHeader.offsetLeft;
            const walk = (x - startX) * 1.5;
            rightBody.scrollLeft = scrollLeft - walk;
        };

        const onHeaderUp = () => {
            isDown = false;
            window.removeEventListener('mousemove', onHeaderMove);
            window.removeEventListener('mouseup', onHeaderUp);
        };

        window.addEventListener('mousemove', onHeaderMove);
        window.addEventListener('mouseup', onHeaderUp);
    });
}

function renderGridSchedule(data) {
    // TARGET THE VIEW CONTAINER DIRECTLY to replace legacy HTML
    const viewContainer = document.getElementById('view-tms-timeline');
    if (!viewContainer) return;

    // 1. INJECT SKELETON IF MISSING (Full Replacement)
    if (!document.querySelector('.timeline-wrapper')) {
        viewContainer.innerHTML = `
            <div class="timeline-wrapper">
                <!-- ROW 1: TOOLBAR (Date Nav & Legend) -->
                <div class="timeline-toolbar">
                    <!-- Date Nav will be injected here -->
                    <div class="timeline-legend">
                        <div class="legend-item"><div class="dot playing"></div><span>Playing</span></div>
                        <div class="legend-item"><div class="dot scheduled"></div><span>Scheduled</span></div>
                        <div class="legend-item"><div class="dot error"></div><span>Issue</span></div>
                    </div>
                </div>
                
                <!-- ROW 2: SPLIT VIEW -->
                <div class="timeline-split-view">
                    <!-- Fixed Left Panel -->
                    <div class="left-panel">
                        <div class="left-header">AUDITORIUM</div>
                        <div class="left-body" id="left-body"></div>
                    </div>
                    
                    <!-- Scrollable Right Panel -->
                    <div class="right-panel">
                        <div class="right-header" id="right-header">
                            <div class="time-axis" id="time-axis"></div>
                            <div id="now-label-container" class="now-label-container"></div>
                        </div>
                        <div class="right-body" id="right-body">
                            <!-- Rows injected here -->
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Init interactions immediately after DOM creation
        setTimeout(initTimelineInteractions, 100);

        // CRITICAL: Render Time Axis Immediately so it's not "removed"
        requestAnimationFrame(() => renderTimeAxis());
    }

    // Initialize Controls
    renderDateNavControl();

    // Always Ensure Axis is present (idempotent)
    const axis = document.getElementById('time-axis');
    if (axis && axis.childNodes.length === 0) renderTimeAxis();

    let screens = [];

    // 1. USE REAL DATA (If Available)
    if (data && Object.keys(data).length > 0) {
        screens = Object.values(data);
    }
    // 2. SKELETON MODE (If No Real Data, Use Configured Screens)
    else if (typeof CACHED_STATUS_DATA !== 'undefined' && Object.keys(CACHED_STATUS_DATA).length > 0) {
        screens = Object.values(CACHED_STATUS_DATA).map(t => ({
            id: t.id,
            name: t.name || `Screen ${t.id}`,
            status: 'Loading...',
            schedules: [] // Empty schedules for skeleton
        }));
    } else {
        // EVEN IF NO DATA, we should show the configured screens as skeleton
        if (typeof CACHED_STATUS_DATA !== 'undefined' && Object.keys(CACHED_STATUS_DATA).length > 0) {
            screens = Object.values(CACHED_STATUS_DATA).map(t => ({
                id: t.id,
                name: t.name || `Screen ${t.id}`,
                status: 'Offline',
                schedules: []
            }));
        } else {
            return; // No screens at all
        }
    }

    // RENDER START
    // const screens = Object.values(data); <--- REMOVED

    // Render Left and Right Rows
    const leftBodyContainer = document.getElementById('left-body');
    const rightBodyContainer = document.getElementById('right-body');

    let leftHTML = "";
    let rightHTML = "";

    const now = new Date(); // Define now here for use in showBlocks

    screens.forEach((s, idx) => {
        let showBlocks = "";
        if (s.schedules && s.schedules.length > 0) {
            // ... (keep usage of createShowBlock same as before, just inline the logic or reuse helper)
            s.schedules.forEach(sch => {
                try {
                    // Logic restored from original robust implementation
                    const startTime = new Date(sch.start);
                    const startMins = startTime.getHours() * 60 + startTime.getMinutes();
                    // Duration is likely in seconds based on previous usage (duration * 1000 for endTime)
                    // If duration is missing, default to 2 hours (7200s)
                    const durationSecs = sch.duration || 7200;
                    const durationMins = durationSecs / 60;

                    const width = durationMins * PX_PER_MIN;
                    const left = startMins * PX_PER_MIN;

                    const endTime = new Date(startTime.getTime() + (durationSecs * 1000));

                    // We need to use valid date comparisons. 
                    // Note: 'now' variable should be defined in outer scope or here.
                    // Assuming 'now' is defined in renderGridSchedule.

                    const title = (sch.title || 'Show').toUpperCase();

                    // Determine Ribbon Class
                    let ribbonClass = 'default';
                    let catClass = 'cat-ftr'; // Default to feature for blocks
                    if (title.includes('ADV')) {
                        ribbonClass = 'adv';
                        catClass = 'cat-adv';
                    }
                    else if (title.includes('TLR') || title.includes('TRAILER')) {
                        ribbonClass = 'trailer';
                        catClass = 'cat-tlr';
                    }
                    else {
                        ribbonClass = 'feature';
                        catClass = 'cat-ftr';
                    }

                    // Meta Generation
                    // Check properties safely
                    const is3d = (sch.is3d === true || (sch.attributes && sch.attributes.includes('3D')));
                    const audio = sch.audio || sch.audio_format || '';

                    const icons = [
                        is3d ? '<i class="fas fa-cube"></i> 3D' : '<i class="fas fa-film"></i> 2D',
                        audio ? `<i class="fas fa-volume-up"></i> ${audio}` : ''
                    ].filter(Boolean).join(' ');

                    const timeRange = `${startTime.getHours().toString().padStart(2, '0')}:${startTime.getMinutes().toString().padStart(2, '0')} - ${endTime.getHours().toString().padStart(2, '0')}:${endTime.getMinutes().toString().padStart(2, '0')}`;

                    showBlocks += `
                        <div class="show-block ${catClass}" style="left: ${left}px; width: ${width}px;">
                            <div class="show-header-ribbon ${ribbonClass}"></div>
                            <div class="show-content">
                                <div class="show-meta-top">
                                    <div class="show-title-row">${title}</div>
                                    <div class="show-duration-tag">${Math.floor(durationMins)}m</div>
                                </div>
                                <div class="show-time-range">${timeRange}</div>
                                <div class="show-meta-bottom">
                                    <span class="meta-label">ID-ID</span>
                                    <span class="meta-icons">${icons}</span>
                                </div>
                            </div>
                        </div>
                    `;
                } catch (e) { console.error("Error rendering block", e); }
            });
        }

        // STATUS LOGIC
        let badgeClass = 'status-offline'; // Default Grey

        if (s.status === 'Online') {
            // Check for issues in schedules
            // Logic: 
            // - RED (Critical) if Missing FTR or KDM Expired (Logic for KDM not fully here, assuming missing schedule = critical if expected)
            // - YELLOW (Warning) if Missing TLR/ADV but has FTR
            // - GREEN (OK) if has FTR+TLR+ADV or just "Good"

            // Simplified logic based on provided text:
            // "Abu Offline, Hijau Normal, Kuning Alert (missing trailer/adv), Merah (Missing FTR or KDM)"

            let hasFTR = false;
            let hasTLR = false;
            let hasADV = false;

            if (s.schedules && s.schedules.length > 0) {
                s.schedules.forEach(sch => {
                    const t = (sch.title || "").toUpperCase();
                    if (t.includes('FTR') || t.includes('FEATURE')) hasFTR = true;
                    if (t.includes('TLR') || t.includes('TRAILER')) hasTLR = true;
                    if (t.includes('ADV') || t.includes('ADVERT')) hasADV = true;
                });

                if (hasFTR) {
                    if (hasTLR && hasADV) badgeClass = 'status-ok'; // Green
                    else badgeClass = 'status-warning'; // Yellow (Missiong components)
                } else {
                    badgeClass = 'status-critical'; // Red (Missing Feature)
                }
            } else {
                // Online but no schedules? Critical or Warning? 
                // Let's say Warning (Empty Playlist)
                badgeClass = 'status-warning';
            }
        }

        // Left Row: Badge (Status Indicator) + Name (Styled Box)
        leftHTML += `
            <div class="left-row">
                 <div class="auditorium-label-box ${badgeClass}">
                     <span class="status-dot ${badgeClass}"></span>
                     <span class="aud-name">${s.name}</span>
                 </div>
            </div>
        `;

        // Right Row: Show Blocks
        rightHTML += `
            <div class="right-row">
                <div class="show-blocks-container">
                    ${showBlocks}
                </div>
            </div>
        `;
    });

    leftBodyContainer.innerHTML = leftHTML;

    // Add NOW indicator ONLY if viewing TODAY
    const today = new Date();
    const isViewingToday = VIEW_DATE.toDateString() === today.toDateString();

    if (isViewingToday) {
        rightHTML += `<div id="now-indicator" class="now-indicator"></div>`;
    }
    rightBodyContainer.innerHTML = rightHTML;

    // Inject Label into header if today
    const labelContainer = document.getElementById('now-label-container');
    if (labelContainer) {
        labelContainer.innerHTML = isViewingToday ? `<div id="now-label" class="now-label">--:--:--</div>` : '';
    }

    if (isViewingToday) {
        updateNowIndicator();
        // AUTO SCROLL TO NOW (CENTERED) - ONLY IF NOT MANUALLY SCROLLED
        if (!USER_HAS_MANUALLY_SCROLLED) {
            setTimeout(() => {
                const rightBody = document.getElementById('right-body');
                if (rightBody) {
                    const now = new Date();
                    const currentMins = now.getHours() * 60 + now.getMinutes();
                    const pxPos = currentMins * PX_PER_MIN;

                    // Calculate center: Pixel Position - Half of Viewport Width
                    // Viewport width of right-body is roughly window width - sidebar (180) - padding
                    const viewWidth = rightBody.clientWidth;
                    const scrollTarget = pxPos - (viewWidth / 2);

                    IS_PROGRAMMATIC_SCROLL = true;
                    rightBody.scrollTo({ left: scrollTarget, behavior: 'smooth' });
                    // Reset flag after animation roughly finishes
                    setTimeout(() => { IS_PROGRAMMATIC_SCROLL = false; }, 1000);
                }
            }, 500);
        }
    }
}

// RENDER START
function renderTimeAxis() {
    const axis = document.getElementById('time-axis');
    if (!axis) return;

    // 1. Clear ALL existing children manually to avoid any stacking
    while (axis.firstChild) {
        axis.removeChild(axis.firstChild);
    }

    // 2. Generate clean marks
    const fragment = document.createDocumentFragment();

    for (let h = 0; h <= 24; h++) {
        // Major Hour Mark
        const hDiv = document.createElement('div');
        hDiv.className = 'time-mark major';
        const xPos = h * 60 * PX_PER_MIN;
        hDiv.style.left = `${xPos}px`;

        const hLabel = document.createElement('span');
        hLabel.className = 'time-label';

        // Format based on preference
        if (USE_12H_FORMAT) {
            let hour = h % 24;
            const ampm = hour >= 12 ? 'PM' : 'AM';
            hour = hour % 12;
            hour = hour ? hour : 12;
            hLabel.textContent = `${hour.toString().padStart(2, '0')}:00 ${ampm}`;
        } else {
            hLabel.textContent = `${h.toString().padStart(2, '0')}:00`;
        }
        hDiv.appendChild(hLabel);
        fragment.appendChild(hDiv);

        // Minor 30-min Mark
        if (h < 24) {
            const mDiv = document.createElement('div');
            mDiv.className = 'time-mark minor';
            mDiv.style.left = `${(xPos + (30 * PX_PER_MIN))}px`;

            const mLabel = document.createElement('span');
            mLabel.className = 'time-label';

            // Add :30 label
            if (USE_12H_FORMAT) {
                let hour = h % 12;
                hour = hour ? hour : 12;
                const ampm = h >= 12 ? 'PM' : 'AM';
                mLabel.textContent = `${hour.toString().padStart(2, '0')}:30 ${ampm}`;
            } else {
                mLabel.textContent = `${h.toString().padStart(2, '0')}:30`;
            }
            mDiv.appendChild(mLabel);
            fragment.appendChild(mDiv);
        }
    }
    axis.appendChild(fragment);
}

function updateNowIndicator() {
    const indicator = document.getElementById('now-indicator');
    const label = document.getElementById('now-label');
    if (!indicator && !label) return;

    const now = new Date();
    const currentMins = (now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60);
    const pxPos = currentMins * PX_PER_MIN;

    if (indicator) {
        indicator.style.left = `${pxPos}px`;
    }

    if (label) {
        label.style.left = `${pxPos}px`;
        label.textContent = now.toLocaleTimeString('id-ID', { hour12: false });
    }
}

function scrollToNow() {
    const body = document.getElementById('right-body');
    const indicator = document.getElementById('now-indicator');
    if (body && indicator) {
        const viewWidth = body.clientWidth;
        const target = parseInt(indicator.style.left) - (viewWidth / 2);

        IS_PROGRAMMATIC_SCROLL = true;
        body.scrollTo({ left: target, behavior: 'smooth' });
        setTimeout(() => { IS_PROGRAMMATIC_SCROLL = false; }, 1000);
    }
}

function renderGlobalLibrary(rawData) {
    const tbody = document.getElementById('global-cpl-list');
    if (!tbody) return;

    // 1. Apply Search & Filters locally
    let cpls = [...rawData]; // Copy array

    if (currentFilterKind !== 'all') {
        cpls = cpls.filter(c => (c.kind || 'Unknown') === currentFilterKind);
    }

    if (searchQuery) {
        const q = searchQuery.toLowerCase();
        cpls = cpls.filter(c => c.title.toLowerCase().includes(q) || c.uuid.toLowerCase().includes(q));
    }

    if (cpls.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty">No matching content found.</td></tr>`;
        return;
    }

    // 2. Sort by Kind then Title
    cpls.sort((a, b) => {
        const kindA = a.kind || 'Unknown';
        const kindB = b.kind || 'Unknown';
        if (kindA.localeCompare(kindB) !== 0) return kindA.localeCompare(kindB);
        return a.title.localeCompare(b.title);
    });

    // 3. Render with Group Headers
    let lastKind = null;
    tbody.innerHTML = cpls.map(c => {
        let html = '';
        const currentKind = c.kind || 'Unknown';

        // Inject Header if Kind changes (only in 'All' view or if grouped)
        if (currentFilterKind === 'all' && currentKind !== lastKind) {
            html += `<tr class="group-header"><td colspan="7">${currentKind}s</td></tr>`;
            lastKind = currentKind;
        }

        html += `
        <tr>
            <td class="cpl-title">
                <div class="cpl-title-top">
                    <i class="fas fa-file-video"></i>
                    <span title="${c.uuid}">${c.title}</span>
                </div>
                <div class="cpl-title-bottom">
                    <span class="tech-badge std">${c.standard || 'SMPTE'}</span>
                    ${c.resolution !== '?' ? `<span class="tech-badge res-${c.resolution.toLowerCase()}">${c.resolution}</span>` : ''}
                    ${c.is3d ? `<span class="tech-badge is-3d">3D</span>` : `<span class="tech-badge">2D</span>`}
                    ${c.audio ? `<span class="tech-badge audio">${c.audio}</span>` : ''}
                    ${c.atmos ? `<span class="tech-badge atmos">ATMOS</span>` : ''}
                    ${c.subtitles ? `<span class="tech-badge sub">SUB</span>` : ''}
                    ${c.encrypted ? `<span class="tech-badge enc"><i class="fas fa-lock"></i> Encrypted</span>` : ''}
                </div>
            </td>
            <td><span class="kind-badge ${c.kind || 'Unknown'}">${c.kind || 'Unknown'}</span></td>
            <td><span class="kdm-badge ${c.kdm || 'Missing'}">${c.kdm || 'Missing'}</span></td>
            <td>${c.duration || '-'}</td>
            <td>${c.screens ? c.screens.join(', ') : '-'}</td>
            <td><span class="status-badge available">${c.size || 'Ready'}</span></td>
            <td>
                <button class="action-icon" title="Ingest Everywhere"><i class="fas fa-broadcast-tower"></i></button>
                <button class="action-icon" title="Delete Content"><i class="fas fa-trash-alt"></i></button>
            </td>
        </tr>`;
        return html;
    }).join('');
}


function renderCentralSchedule(data) {
    const tbody = document.getElementById('central-schedule-list');
    if (!tbody) return;

    const screens = Object.values(data);
    let allSchedules = [];

    screens.forEach(s => {
        if (s.schedules) {
            s.schedules.forEach(sched => {
                allSchedules.push({ ...sched, screenName: s.name });
            });
        }
    });

    if (allSchedules.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty">No upcoming shows scheduled in any auditorium.</td></tr>`;
        return;
    }

    // Sort by start time
    allSchedules.sort((a, b) => new Date(a.start) - new Date(b.start));

    tbody.innerHTML = allSchedules.map(s => {
        const startTime = new Date(s.start);
        const now = new Date();
        const endTime = new Date(startTime.getTime() + (s.duration * 1000));

        let statusClass = "pending";
        let statusText = "Scheduled";

        if (now >= startTime && now <= endTime) {
            statusClass = "playing";
            statusText = t('status_playing');
        } else if (now > endTime) {
            statusClass = "available";
            statusText = t('status_stopped'); // Or "Completed" mapped
        } else {
            statusText = t('saved'); // Placeholder for "Scheduled"
        }


        const h = Math.floor(s.duration / 3600);
        const m = Math.floor((s.duration % 3600) / 60);
        const durStr = `${h}h ${m}m`;

        return `
            <tr>
                <td class="time-col">
                    <strong>${startTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</strong>
                    <div class="date-sub">${startTime.toLocaleDateString()}</div>
                </td>
                <td><span class="auditorium-badge">${s.screenName}</span></td>
                <td class="spl-title">${s.title || 'Untitled Playlist'}</td>
                <td>${durStr}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>
                    <button class="action-icon" title="Remove"><i class="fas fa-trash-alt"></i></button>
                    <button class="action-icon" title="Edit"><i class="fas fa-edit"></i></button>
                </td>
            </tr>
        `;
    }).join('');
}

const renderCentralScheduler = renderCentralSchedule; // Alias

function openSchedulerModal() {
    console.log("DEBUG: Opening Scheduler Modal...");
    const modal = document.getElementById('modal-scheduler');
    if (!modal) {
        console.error("ERROR: modal-scheduler not found!");
        return;
    }

    // 1. Populate Screen Select (Instant from Cache)
    const screenSelect = document.getElementById('sch-screen');
    if (screenSelect) {
        // Handle both Object {id: data} and Array [{id: ...}]
        let screens = [];
        if (Array.isArray(CACHED_STATUS_DATA)) {
            screens = CACHED_STATUS_DATA;
        } else if (typeof CACHED_STATUS_DATA === 'object' && CACHED_STATUS_DATA !== null) {
            screens = Object.values(CACHED_STATUS_DATA);
        }

        console.log(`DEBUG: Found ${screens.length} screens in cache`);

        if (screens.length > 0) {
            screenSelect.innerHTML = screens.map(s => {
                const id = s.id || s.uuid;
                const name = s.name || s.auditorium_name || `Screen ${id}`;
                return `<option value="${id}">${name}</option>`;
            }).join('');

            // Restore Custom Dropdown Init to sync UI
            initCustomDropdowns(screenSelect);

            // Add change listener to refresh SPLs when theater changes
            screenSelect.onchange = () => refreshSchedulerSPLs();
        } else {
            screenSelect.innerHTML = `<option value="">No screens registered</option>`;
            // initCustomDropdowns(screenSelect); // Removed

            // Fallback: search status if cache somehow empty
            apiFetch('/api/status').then(res => res.json()).then(data => {
                CACHED_STATUS_DATA = data;
                let fallbackScreens = Array.isArray(data) ? data : Object.values(data);
                if (fallbackScreens.length > 0) {
                    screenSelect.innerHTML = fallbackScreens.map(s => {
                        const id = s.id || s.uuid;
                        const name = s.name || s.auditorium_name || `Screen ${id}`;
                        return `<option value="${id}">${name}</option>`;
                    }).join('');
                    initCustomDropdowns(screenSelect);
                    refreshSchedulerSPLs();
                }
            });
        }
    } else {
        console.warn("WARNING: sch-screen select element not found in modal");
    }

    // 2. Initial SPL Fetch
    refreshSchedulerSPLs();

    modal.classList.add('active');
}

/**
 * Dynamic SPL Fetching for Scheduler
 */
function refreshSchedulerSPLs() {
    const screenSelect = document.getElementById('sch-screen');
    const splSelect = document.getElementById('sch-spl');
    if (!splSelect) return;

    const screenId = screenSelect?.value;
    const screenData = Array.isArray(CACHED_STATUS_DATA)
        ? CACHED_STATUS_DATA.find(s => (s.id || s.uuid) == screenId)
        : CACHED_STATUS_DATA[screenId];

    splSelect.innerHTML = `<option value="">🔍 Searching Playlists...</option>`;
    initCustomDropdowns(splSelect); // Show "Searching" state in Custom UI

    console.log(`DEBUG: Fetching SPLs for screen ${screenId} (${screenData?.ims_ip || 'Local Only'})`);

    const renderSPLs = (spls) => {
        if (!spls || spls.length === 0) {
            splSelect.innerHTML = `<option value="">No playlists found</option>`;
            initCustomDropdowns(splSelect); // Refresh Custom UI
            return;
        }
        splSelect.innerHTML = spls.map(s => {
            const uuid = s.uuid || s.uuid_id;
            const title = s.title || s.annotation || 'Untitled SPL';
            return `<option value="${uuid}">${title}</option>`;
        }).join('');
        initCustomDropdowns(splSelect); // Refresh Custom UI
    };

    const fetchLocal = () => {
        console.log("DEBUG: Fetching LOCAL SPLs fallback...");
        return apiFetch('/api/spl/local').then(res => res.json()).catch(() => []);
    };

    if (screenData && screenData.ims_ip) {
        // TIMEOUT WRAPPER
        const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 2000));

        Promise.race([
            apiFetch(`/api/spl?host=${screenData.ims_ip}`).then(res => res.json()),
            timeout
        ])
            .then(remoteSpls => {
                if (remoteSpls && remoteSpls.length > 0) {
                    console.log(`DEBUG: Found ${remoteSpls.length} REMOTE SPLs`);
                    renderSPLs(remoteSpls);
                } else {
                    fetchLocal().then(renderSPLs);
                }
            })
            .catch((err) => {
                console.warn(`REMOTE SPL FETCH FAILED (${err}). Falling back to local.`);
                fetchLocal().then(renderSPLs);
            });
    } else {
        fetchLocal().then(renderSPLs);
    }
}

function closeSchedulerModal() {
    const modal = document.getElementById('modal-scheduler');
    if (modal) modal.classList.remove('active');
}

function switchTab(tabId) {
    // UI Update
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tms-view').forEach(v => v.classList.remove('active'));

    const targetBtn = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
    const targetView = document.getElementById(`view-${tabId}`);

    if (targetBtn) targetBtn.classList.add('active');
    if (targetView) targetView.classList.add('active');

    // Header Update
    document.getElementById('current-tab-title').textContent = t(TAB_TITLES[tabId]);
    document.getElementById('current-tab-desc').textContent = t(TAB_DESCRIPTIONS[tabId]);


    // Special Layout for SPL (Remove Padding)
    const container = document.querySelector('.view-container');
    if (container) {
        if (tabId === 'tms-spl') {
            container.classList.add('spl-active-container');
        } else {
            container.classList.remove('spl-active-container');
        }
    }

    fetchTMSData();

    // Init Logic for Specific Tabs
    if (tabId === 'tms-timeline') {
        setTimeout(scrollToNow, 100);
    } else if (tabId === 'tms-system') {
        renderGeneralPreferences();
        initUserManagement();
    } else if (tabId === 'tms-config') {
        renderConfigScreenList();
    }


    // Save State
    localStorage.setItem('tms_active_tab', tabId);

    // Close sidebar on mobile after navigation
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (window.innerWidth <= 768) {
        if (sidebar) sidebar.classList.remove('mobile-open');
        if (overlay) overlay.classList.remove('active');
        document.body.style.overflow = ''; // Release scroll lock
    } else {
        // Ensure overlay never stays active in desktop view
        if (overlay) overlay.classList.remove('active');
    }
}

// Event Listeners set in consolidated load below

// Initialization
// --- AUTHENTICATION ---
// Authentication check handled in consolidated load

document.addEventListener('DOMContentLoaded', () => {
    // 1. Auth Guard & User Info
    const userStr = localStorage.getItem('tms_user');
    if (!userStr) {
        window.location.href = '/login.html';
        return;
    }

    try {
        const user = JSON.parse(userStr);
        const nameEl = document.getElementById('current-user-name');
        const avatarEl = document.getElementById('current-user-avatar');
        if (nameEl) nameEl.textContent = user.username;
        if (avatarEl) avatarEl.textContent = user.username.substring(0, 2).toUpperCase();

        const profileBtn = document.getElementById('user-profile-btn');
        if (profileBtn) profileBtn.onclick = window.logout;
    } catch (e) { window.logout(); }

    // 2. Sidebar State
    const sidebar = document.querySelector('.sidebar');
    const COLLAPSE_KEY = 'tms_sidebar_collapsed';
    if (sidebar && localStorage.getItem(COLLAPSE_KEY) === 'true') {
        sidebar.classList.add('collapsed');
    }

    // 3. System Initialization
    localizeUI();
    initSystemClock();
    initCustomDropdowns();
    initUserManagement();
    initTabState();
    initTimelineInteractions();

    // 4. Data & Real-Time
    fetchTMSData(); // Initial Fetch
    initWebSocket(); // Start Real-Time Stream

    // 5. Views & Navigation
    const savedTab = localStorage.getItem('tms_active_tab');
    switchTab(savedTab || 'tms-dash');

    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // 6. Form Handlers
    const schForm = document.getElementById('scheduler-form');
    if (schForm) {
        schForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                screen_id: document.getElementById('sch-screen').value,
                spl_uuid: document.getElementById('sch-spl').value,
                start_time: document.getElementById('sch-time').value
            };
            try {
                const res = await apiFetch('/api/schedule/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                if (result.status === 'ok') {
                    showAlertModal('Show scheduled successfully!');
                    closeSchedulerModal();
                    fetchTMSData();
                } else { showAlertModal('Error: ' + result.error); }
            } catch (err) { showAlertModal('Connection error.'); }
        });
    }

    // 7. Filter & Search
    const searchInput = document.querySelector('#view-tms-content .search-bar input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value.toLowerCase();
            renderViews();
        });
    }

    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilterKind = btn.getAttribute('data-kind');
            renderViews();
        });
    });

    const splSearch = document.getElementById('spl-source-search');
    if (splSearch) splSearch.addEventListener('input', () => renderSPLEditor());

    const gallerySearch = document.getElementById('spl-gallery-search');
    if (gallerySearch) gallerySearch.addEventListener('input', () => renderSPLGallery());

    // 8. Background Jobs (Local UI Only)
    setInterval(updateNowIndicator, 5000);
});

async function fetchLocalSPLs() {
    try {
        const res = await apiFetch('/api/spl/local');
        CACHED_SPLS = await res.json();
        renderSPLGallery();
    } catch (e) {
        console.error("Failed to fetch local SPLs:", e);
    }
}

function renderSPLGallery() {
    const gallery = document.getElementById('saved-spl-gallery');
    if (!gallery) return;

    if (!CACHED_SPLS || CACHED_SPLS.length === 0) {
        gallery.innerHTML = `<div class="empty-placeholder" style="padding:10px; font-size:11px;">No saved playlists</div>`;
        return;
    }

    const term = (document.getElementById('spl-gallery-search')?.value || '').toLowerCase();
    const filtered = CACHED_SPLS.filter(s => (s.title || '').toLowerCase().includes(term) || (s.uuid && s.uuid.toLowerCase().includes(term)));

    if (filtered.length === 0) {
        gallery.innerHTML = `<div class="empty-placeholder" style="padding:10px; font-size:11px;">No matching playlists</div>`;
        return;
    }

    gallery.innerHTML = filtered.map(s => `
        <div class="spl-gallery-item" onclick="openSPLPreview('${s.uuid}')">
            <div class="info-group">
                <div class="spl-name">${s.title}</div>
                <div class="spl-duration"><i class="far fa-clock"></i> ${s.duration || '00:00:00'}</div>
            </div>
            <div class="action-group">
                <button class="btn-icon-action" onclick="event.stopPropagation(); loadSPLForEditing('${s.uuid}')" title="Edit Playlist">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon-action danger" onclick="event.stopPropagation(); deleteSPL('${s.uuid}')" title="Delete Playlist">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// PREMIUM SPL PREVIEW & DISTRIBUTE FLOW
let CURRENT_PREVIEW_SPL = null;

function openSPLPreview(uuid) {
    const spl = CACHED_SPLS.find(s => s.uuid === uuid);
    if (!spl) return;

    CURRENT_PREVIEW_SPL = spl;

    // header title
    const titleEl = document.getElementById('preview-spl-title');
    if (titleEl) titleEl.innerHTML = `<i class="fas fa-film"></i> ${spl.title}`;

    // header badge (duration)
    const durEl = document.getElementById('preview-spl-duration');
    if (durEl) {
        durEl.innerText = spl.duration || '00:00:00';
        durEl.className = 'modal-badge'; // switch to new class
    }

    // --- Body Construction ---
    // We'll replace the innerHTML of .modal-body to include the info-panel + list-container
    const modalBody = document.querySelector('#spl-preview-modal .modal-body');

    // Safety check if modal structure matches what we expect
    if (modalBody) {
        modalBody.innerHTML = `
            <div class="spl-info-panel">
                 <div class="info-item">
                    <label>Playlist UUID</label>
                    <span style="font-size:11px">${spl.uuid}</span>
                </div>
                <div class="info-item">
                    <label>Total Duration</label>
                    <span style="font-size:11px">${spl.duration}</span>
                </div>
            </div>
            <div id="preview-spl-list"></div>
        `;
    }

    const listContainer = document.getElementById('preview-spl-list');
    listContainer.className = ''; // Remove old classes
    listContainer.innerHTML = '';

    if (spl.cpls && spl.cpls.length > 0) {
        spl.cpls.forEach((cpl, idx) => {
            const item = document.createElement('div');
            item.className = 'spl-preview-item'; // New Class

            // Format duration if needed, assuming cpl.duration is HH:MM:SS
            const dur = cpl.duration || '--:--:--';

            // Determine icon based on kind (optional, falling back to simple number)

            item.innerHTML = `
                <div class="left-sect">
                    <div class="idx-badge">${idx + 1}</div>
                    <div class="content-info">
                        <div class="content-title">${cpl.title}</div>
                        <div class="content-meta">
                            <span><i class="fas fa-file-video"></i> ${cpl.kind || 'Clip'}</span>
                            <span>•</span>
                            <span>${cpl.editRate || '24'} fps</span>
                        </div>
                    </div>
                </div>
                <div class="right-sect">
                    ${dur}
                </div>
            `;
            listContainer.appendChild(item);
        });
    } else {
        listContainer.innerHTML = `
            <div class="spl-preview-empty">
                <i class="fas fa-film"></i>
                <p>This playlist is empty.</p>
            </div>
        `;
    }

    document.getElementById('spl-preview-modal').classList.add('active');
}

function closeSPLPreview() {
    document.getElementById('spl-preview-modal').classList.remove('active');
    // Don't clear CURRENT_PREVIEW_SPL immediately if we might need it for distribution
}

function distributePreviewSPL() {
    if (!CURRENT_PREVIEW_SPL) return;

    // Set global target for the distribute modal
    window.DISTRIBUTE_TARGET = CURRENT_PREVIEW_SPL;

    closeSPLPreview();

    // Small delay to allow modal transition
    setTimeout(() => {
        openDistributeModal();
    }, 300);
}

async function loadSPLFromList(uuid, title) {
    const spl = CACHED_SPLS.find(s => s.uuid === uuid);
    if (!spl) {
        alert("SPL not found in cache.");
        return;
    }

    currentSPL = spl.cpls || [];
    document.getElementById('new-spl-title').value = spl.title;
    closeModal('modal-spl-load');
    renderSPLEditor();
}

function closeSPLPreview() {
    document.getElementById('spl-preview-modal').classList.remove('active');
    CURRENT_PREVIEW_SPL = null;
}

function distributePreviewSPL() {
    if (!CURRENT_PREVIEW_SPL) return;

    // Pass the SPL to the distribute modal
    // We assume openDistributeModal can handle this, or we rely on a global
    window.DISTRIBUTE_TARGET = CURRENT_PREVIEW_SPL;

    closeSPLPreview();

    // Determine which openDistributeModal to call. 
    // If it exists in app.js, call it.
    if (typeof openDistributeModal === 'function') {
        openDistributeModal();
    } else {
        showAlertModal("Distribute function not found.");
    }
}

function renderSPLEditor() {
    renderSPLGallery(); // Update gallery whenever editor renders
    const sourceContainer = document.getElementById('spl-source-list');
    const targetContainer = document.getElementById('spl-target-list');
    if (!sourceContainer || !targetContainer) return;

    // Ensure the container itself can receive drops
    targetContainer.ondragover = handleDragOver;
    targetContainer.ondrop = (e) => handleDrop(e, -1);

    // 1. Render Source (Grouped & Filtered)
    const term = (document.getElementById('spl-source-search')?.value || '').toLowerCase();
    const filtered = CACHED_LIBRARY_DATA.filter(c => c.title.toLowerCase().includes(term));

    // Group by Kind
    const groups = {};
    filtered.forEach(c => {
        const kind = c.kind || 'Unknown';
        if (!groups[kind]) groups[kind] = [];
        groups[kind].push(c);
    });

    // Sortable order for categories
    const categoryOrder = ['Feature', 'Trailer', 'Teaser', 'Advertisement', 'Psa', 'Rating', 'Policy', 'Test', 'Unknown'];
    const sortedKinds = Object.keys(groups).sort((a, b) => {
        let idxA = categoryOrder.indexOf(a);
        let idxB = categoryOrder.indexOf(b);
        if (idxA === -1) idxA = 99;
        if (idxB === -1) idxB = 99;
        return idxA - idxB;
    });

    let html = "";
    sortedKinds.forEach(kind => {
        html += `<div class="spl-category-header">${kind.toUpperCase()} (${groups[kind].length})</div>`;
        html += groups[kind].map(c => `
            <div class="spl-source-item" draggable="true" ondragstart="handleDragStart(event, '${c.uuid}')" onclick="addToSPL('${c.uuid}')" data-kind="${c.kind || 'Unknown'}">
                <div class="spl-item-icon"><i class="fas fa-film"></i></div>
                <div class="spl-item-info">
                    <div class="title">${c.title}</div>
                    <div class="meta">
                        <span class="tech-badge std">${c.standard || 'SMPTE'}</span>
                        ${c.resolution !== '?' ? `<span class="tech-badge res-${c.resolution.toLowerCase()}">${c.resolution}</span>` : ''}
                        ${c.is3d ? `<span class="tech-badge is-3d">3D</span>` : `<span class="tech-badge">2D</span>`}
                        ${c.audio ? `<span class="tech-badge audio">${c.audio}</span>` : ''}
                        ${c.atmos ? `<span class="tech-badge atmos">ATMOS</span>` : ''}
                        ${c.subtitles ? `<span class="tech-badge sub">SUB</span>` : ''}
                        ${c.encrypted ? `<span class="tech-badge enc"><i class="fas fa-lock"></i></span>` : ''}
                        <span class="dur-label">${c.duration}</span>
                    </div>
                </div>
                <div class="spl-item-add"><i class="fas fa-plus"></i></div>
            </div>
        `).join('');
    });

    sourceContainer.innerHTML = html || `<div class="empty-placeholder">No matching content found</div>`;

    // 2. Render Target Playlist
    if (currentSPL.length === 0) {
        targetContainer.innerHTML = `
            <div class="empty-placeholder" ondragover="handleDragOver(event)" ondrop="handleDrop(event, -1)">
                <i class="fas fa-plus-circle"></i>
                <p>Drag CPLs from library here to start building your show</p>
            </div>`;
        document.getElementById('new-spl-duration').textContent = "00:00:00";
    } else {
        let totalSecs = 0;
        targetContainer.innerHTML = currentSPL.map((c, idx) => {
            // Calculate duration seconds for total
            const parts = c.duration.split(':');
            const sec = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
            totalSecs += sec;

            return `
            <div class="spl-target-item" ondragover="handleDragOver(event)" ondrop="handleDrop(event, ${idx})">
                <div class="idx">${idx + 1}</div>
                <div class="info">
                    <div class="title">${c.title}</div>
                    <div class="dur">${c.duration}</div>
                </div>
                <div class="remove" onclick="event.stopPropagation(); removeFromSPL(${idx})"><i class="fas fa-times"></i></div>
            </div>`;
        }).join('');

        // Global Drop Area (Bottom of list)
        targetContainer.innerHTML += `<div class="drop-zone-end" ondragover="handleDragOver(event)" ondrop="handleDrop(event, -1)">Drop here to append</div>`;

        // Update Total Duration
        const h = Math.floor(totalSecs / 3600);
        const m = Math.floor((totalSecs % 3600) / 60);
        const s = totalSecs % 60;
        document.getElementById('new-spl-duration').textContent =
            `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
}

function addToSPL(uuid) {
    const cpl = CACHED_LIBRARY_DATA.find(c => c.uuid === uuid);
    if (cpl) {
        currentSPL.push({ ...cpl, elId: Date.now() + Math.random() }); // Unique ID for drag order
        renderSPLEditor();
    }
}

function closeCurrentSPL() {
    clearSPL();
    // No longer switching tabs, just staying in the editor with a clean slate
}

function loadSPLForEditing(uuid) {
    const spl = CACHED_SPLS.find(s => s.uuid === uuid);
    if (!spl) return;

    // Deep copy to prevent mutating cache directly during editing
    currentSPL = spl.cpls.map(c => ({ ...c, elId: Date.now() + Math.random() }));

    document.getElementById('new-spl-title').value = spl.title;
    renderSPLEditor();

    // Optional: Visual feedback or scroll to editor
    const targetPanel = document.querySelector('.target-panel');
    if (targetPanel) {
        targetPanel.classList.add('highlight-pulse');
        setTimeout(() => targetPanel.classList.remove('highlight-pulse'), 500);
    }
}

function deleteSPL(uuid) {
    deleteLocalSPL(null, uuid);
}

function showConfirmModal(message, onConfirm) {
    const modal = document.getElementById('modal-custom-confirm');
    const msgEl = document.getElementById('confirm-modal-message');
    const btnOk = document.getElementById('btn-confirm-ok');
    const btnCancel = document.getElementById('btn-confirm-cancel');

    if (!modal || !msgEl || !btnOk || !btnCancel) {
        // Fallback to native if DOM not ready
        if (confirm(message)) onConfirm();
        return;
    }

    msgEl.innerText = message;
    modal.classList.add('active');

    // Clean up previous listeners
    const newBtnOk = btnOk.cloneNode(true);
    const newBtnCancel = btnCancel.cloneNode(true);
    btnOk.parentNode.replaceChild(newBtnOk, btnOk);
    btnCancel.parentNode.replaceChild(newBtnCancel, btnCancel);

    newBtnOk.onclick = () => {
        modal.classList.remove('active');
        if (typeof onConfirm === 'function') onConfirm();
    };

    newBtnCancel.onclick = () => {
        modal.classList.remove('active');
    };
}

function showAlertModal(message, onOk) {
    const modal = document.getElementById('modal-custom-alert');
    const msgEl = document.getElementById('alert-modal-message');
    const btnOk = document.getElementById('btn-alert-ok');

    if (!modal || !msgEl || !btnOk) {
        alert(message);
        if (typeof onOk === 'function') onOk();
        return;
    }

    msgEl.innerText = message;
    modal.classList.add('active');

    const newBtnOk = btnOk.cloneNode(true);
    btnOk.parentNode.replaceChild(newBtnOk, btnOk);

    newBtnOk.onclick = () => {
        modal.classList.remove('active');
        if (typeof onOk === 'function') onOk();
    };
}

// DRAG AND DROP HANDLERS
let draggedUUID = null;

function handleDragStart(e, uuid) {
    draggedUUID = uuid;
    e.target.classList.add('dragging');
    e.dataTransfer.setData('text/plain', uuid);
}

function handleDragOver(e) {
    e.preventDefault(); e.stopPropagation();
    e.target.closest('.spl-target-item')?.classList.add('drag-over');
}

function handleDrop(e, targetIdx) {
    e.preventDefault();
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));

    if (draggedUUID) {
        const cpl = CACHED_LIBRARY_DATA.find(c => c.uuid === draggedUUID);
        if (cpl) {
            if (targetIdx === -1) {
                currentSPL.push({ ...cpl, elId: Date.now() });
            } else {
                currentSPL.splice(targetIdx, 0, { ...cpl, elId: Date.now() });
            }
            renderSPLEditor();
        }
    }
    draggedUUID = null;
}

function removeFromSPL(idx) {
    currentSPL.splice(idx, 1);
    renderSPLEditor();
}

function clearSPL() {
    currentSPL = [];
    document.getElementById('new-spl-title').value = "New Show";
    renderSPLEditor();
}

function saveSPL() {
    if (currentSPL.length === 0) {
        showAlertModal("Cannot save empty playlist.");
        return;
    }
    const currentTitle = document.getElementById('new-spl-title').value;
    document.getElementById('input-spl-save-name').value = currentTitle;

    // Open Custom Modal
    const modal = document.getElementById('modal-spl-save');
    if (modal) {
        modal.classList.add('active');
        document.getElementById('input-spl-save-name').focus();
    }
}

async function confirmSaveSPL() {
    const nameInput = document.getElementById('input-spl-save-name');
    const title = nameInput.value.trim();

    if (!title) {
        showAlertModal("Please enter a playlist name.");
        return;
    }

    // Close Modal
    closeModal('modal-spl-save');
    document.getElementById('new-spl-title').value = title;

    const uuid = "SPL-" + Date.now();

    // Calculate total duration
    let totalSecs = 0;
    currentSPL.forEach(c => {
        const parts = c.duration.split(':');
        totalSecs += parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
    });
    const h = Math.floor(totalSecs / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    const s = totalSecs % 60;
    const duration = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;

    try {
        await apiFetch('/api/spl/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uuid: uuid,
                title: title,
                duration: duration,
                cpls: currentSPL
            })
        });

        // Refresh local gallery immediately
        fetchLocalSPLs();
        renderLoadSPLList(); // Refresh modal list if open

        // Non-intrusive notification
        const btn = document.querySelector('button[onclick="saveSPL()"]');
        if (btn) {
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> Saved';
            btn.style.background = 'var(--success)';
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.style.background = '';
            }, 2000);
        }
        fetchLocalSPLs(); // Update Gallery!

    } catch (e) {
        console.error("Save Error:", e);
        showAlertModal("Save failed: " + e);
    }
}

async function deleteLocalSPL(e, uuid) {
    if (e) e.stopPropagation();
    showConfirmModal("Are you sure you want to delete this saved playlist?", async () => {
        try {
            const res = await apiFetch('/api/spl/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ uuid: uuid })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                // alert("Deleted!"); // Silent success is better for enterprise
                fetchLocalSPLs(); // Update Gallery!
                renderLoadSPLList(); // Refresh modal list if open
            } else {
                showAlertModal("Delete failed: " + data.error);
            }
        } catch (err) {
            showAlertModal("Network Error: " + err);
        }
    });
}

async function openDistributeModal() {
    // Check if we are distributing from Preview or Editor
    const hasDistributeTarget = window.DISTRIBUTE_TARGET && window.DISTRIBUTE_TARGET.cpls && window.DISTRIBUTE_TARGET.cpls.length > 0;
    const hasEditorContent = currentSPL && currentSPL.length > 0;

    if (!hasDistributeTarget && !hasEditorContent) {
        showAlertModal("Playlist is empty! Add content first.");
        return;
    }

    // Fetch latest config for screens
    try {
        const res = await apiFetch(`${API_BASE}/api/config`);
        const config = await res.json();

        const list = document.getElementById('distribute-screen-list');
        list.innerHTML = config.screens.map(s => `
            <div class="checkbox-item">
                <input type="checkbox" id="chk-dist-${s.name}" value="${s.name}" checked>
                <label for="chk-dist-${s.name}">
                    <i class="fas fa-desktop"></i> ${s.name} <small>(${s.ims_ip || s.projector_ip})</small>
                </label>
            </div>
        `).join('');

        document.getElementById('modal-spl-distribute').classList.add('active');
        document.getElementById('distribute-status').textContent = "";
        document.getElementById('btn-confirm-distribute').disabled = false;

    } catch (e) {
        alert("Failed to load screens: " + e);
    }
}

async function confirmDistribute() {
    let title, cpls;

    if (window.DISTRIBUTE_TARGET) {
        // Distributing from Preview
        title = window.DISTRIBUTE_TARGET.title;
        cpls = window.DISTRIBUTE_TARGET.cpls; // Ensure this structure matches
    } else {
        // Distributing from Editor
        title = document.getElementById('new-spl-title').value;
        cpls = currentSPL;
    }

    const checkboxes = document.querySelectorAll('#distribute-screen-list input:checked');
    const targets = Array.from(checkboxes).map(cb => cb.value);

    if (targets.length === 0) {
        alert("Please select at least one screen.");
        return;
    }

    const btn = document.getElementById('btn-confirm-distribute');
    const status = document.getElementById('distribute-status');

    btn.disabled = true;
    status.textContent = "Distributing playlist... please wait...";

    try {
        const payload = {
            title: title,
            cpls: cpls,
            targets: targets
        };

        const res = await apiFetch('/api/spl/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const report = await res.json();

        if (report && report.failed && report.failed.length === 0 && report.status !== 'error') {
            status.textContent = "Success! Playlist sent to all selected screens.";
            status.style.color = "var(--success)";
            setTimeout(() => closeModal('modal-spl-distribute'), 1500);
        } else if (report && report.status === 'error') {
            status.textContent = "Error: " + (report.error || "Unknown Server Error");
            status.style.color = "var(--danger)";
        } else if (report && report.failed) {
            const failDetails = report.failed.map(f => `${f.screen}: ${f.error}`).join(' | ');
            status.textContent = `Failed: ${failDetails}`;
            status.style.color = "var(--danger)";
        } else {
            status.textContent = "Error: Invalid response from server.";
            status.style.color = "var(--danger)";
        }

    } catch (e) {
        status.textContent = "Error: " + e.message;
        status.style.color = "var(--danger)";
    } finally {
        btn.disabled = false;
    }
}

// --- LOAD SPL FEATURE ---
async function openLoadSPLModal() {
    const list = document.getElementById('load-spl-list');
    list.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Fetching playlists...</div>';
    document.getElementById('modal-spl-load').classList.add('active');

    try {
        const res = await apiFetch('/api/spl/local');
        CACHED_SPLS = await res.json();
        renderLoadSPLList();
    } catch (e) {
        list.innerHTML = `<div class="error-msg">Failed to load: ${e}</div>`;
    }
}

function renderLoadSPLList() {
    const list = document.getElementById('load-spl-list');
    if (!list) return;

    const term = (document.getElementById('load-spl-search')?.value || '').toLowerCase();

    // Defensive check
    if (!CACHED_SPLS || !Array.isArray(CACHED_SPLS)) {
        list.innerHTML = '<div class="empty">No playlist data available.</div>';
        return;
    }

    const filtered = CACHED_SPLS.filter(s => (s.title || '').toLowerCase().includes(term));

    if (filtered.length === 0) {
        list.innerHTML = `<div class="empty-placeholder">No playlists found.</div>`;
        return;
    }

    list.innerHTML = filtered.map(s => `
        <div class="spl-load-item">
            <div class="icon" onclick="loadSPLFromList('${s.uuid}', '${s.title}')"><i class="fas fa-list-alt"></i></div>
            <div class="info" onclick="loadSPLFromList('${s.uuid}', '${s.title}')">
                <div class="title">${s.title}</div>
                <div class="uuid">${s.uuid} | ${s.duration || '--:--:--'}</div>
            </div>
            <div class="action">
                <i class="fas fa-trash" style="margin-right:10px; color:#ef4444; cursor:pointer;" 
                   onclick="deleteLocalSPL('${s.uuid}')" title="Delete"></i>
                <i class="fas fa-download" style="cursor:pointer;" 
                   onclick="loadSPLFromList('${s.uuid}', '${s.title}')" title="Load"></i>
            </div>
        </div>
    `).join('');
}

async function loadSPLFromList(uuid, title) {
    const spl = CACHED_SPLS.find(s => s.uuid === uuid);
    if (!spl) {
        alert("SPL not found in cache.");
        return;
    }

    currentSPL = spl.cpls || [];
    document.getElementById('new-spl-title').value = spl.title;
    closeModal('modal-spl-load');
    renderSPLEditor();
}

// Search Listener for Load Modal (Moved to init block below)

// Remote Viewer Cleanup
function closeRemoteViewer() {
    if (rfb) {
        try { rfb.disconnect(); } catch (e) { }
        rfb = null;
    }
    const pc = document.getElementById('noVNC_container');
    if (pc) pc.innerHTML = '';

    const iframe = document.getElementById('remote-iframe');
    if (iframe) iframe.src = 'about:blank';

    document.getElementById('modal-remote-viewer').classList.remove('active');
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
    if (id === 'modal-theater-control') openControlId = null;
}

// IMMEDIATE UI INITIALIZATION (SKELETON)
document.addEventListener('DOMContentLoaded', () => {
    // 1. Search Listener
    const search = document.getElementById('load-spl-search');
    if (search) search.addEventListener('input', () => renderLoadSPLList());

    // --- CONFIG TAB LOGIC INJECTION ---
    const list = document.getElementById('config-screen-list');
    if (list) renderConfigScreenList();

    // 2. Render Timeline Skeleton immediately if active
    const activeBtn = document.querySelector('.nav-item.active');
    if (activeBtn && activeBtn.dataset.tab === 'tms-timeline') {
        renderGridSchedule({});
    }
});

// --- AUDITORIUM MANAGEMENT LOGIC ---
let selectedConfigId = null;

function renderConfigScreenList() {
    const list = document.getElementById('config-screen-list');
    if (!list) return;

    if (!CACHED_STATUS_DATA) {
        list.innerHTML = `<div class="empty">Loading inventory...</div>`;
        return;
    }

    const screens = Object.values(CACHED_STATUS_DATA).sort((a, b) => parseInt(a.id) - parseInt(b.id));

    list.innerHTML = screens.map(s => `
        <div class="inventory-item ${selectedConfigId === s.id ? 'active' : ''}" onclick="loadScreenConfig('${s.id}')">
            <div class="icon"><i class="fas fa-film"></i></div>
            <div class="details">
                <div class="name">${s.name}</div>
                <div class="sub">${s.server_model || s.server_type || 'Unknown Server'}</div>
            </div>
            <div class="actions">
                <button class="btn-delete-tiny" onclick="event.stopPropagation(); deleteCurrentScreen('${s.id}')">
                    <i class="fas fa-trash-alt"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function loadScreenConfig(id) {
    selectedConfigId = id;
    renderConfigScreenList(); // Refresh active state

    const screen = Object.values(CACHED_STATUS_DATA).find(s => s.id == id || s.id === id.toString());
    if (!screen) return;

    // Show Form, Hide Empty State
    document.getElementById('settings-empty-state').style.display = 'none';
    document.getElementById('screen-config-form').style.display = 'block';

    const handleLegacyIp = (ip) => (ip === "0.0.0.0" ? "" : (ip || ""));

    // Populate Fields
    setVal('cfg-auditorium-name', screen.name);
    document.getElementById('detail-screen-id').textContent = `Reference ID: ${screen.id}`;

    // Server
    setVal('cfg-server-type', screen.server_type || 'Dolby');
    setVal('cfg-server-model', screen.server_model || '');
    setVal('cfg-server-name', screen.server_name || '');
    setVal('cfg-server-ip', handleLegacyIp(screen.ims_ip || screen.ip));
    setVal('cfg-server-user', screen.server_user || '');
    setVal('cfg-server-pass', screen.server_pass || '');
    setVal('cfg-server-port', screen.server_port || 80);
    setVal('cfg-server-snmp-port', screen.server_snmp_port || '');
    setVal('cfg-remote-mode', screen.remote_mode || 'auto');
    setVal('cfg-vnc-port', screen.vnc_port || '');

    // Projector
    setVal('cfg-proj-type', screen.proj_type || 'Christie');
    setVal('cfg-proj-name', screen.proj_name || '');
    setVal('cfg-proj-ip', handleLegacyIp(screen.projector_ip));
    setVal('cfg-proj-port', screen.proj_port || 161);
    setVal('cfg-proj-snmp-port', screen.proj_snmp_port || '');

    // Audio
    setVal('cfg-audio-type', screen.audio_type || 'Dolby CP750');
    setVal('cfg-audio-name', screen.audio_name || '');
    setVal('cfg-audio-ip', handleLegacyIp(screen.audio_ip));
    setVal('cfg-audio-port', screen.audio_port || 80);
    setVal('cfg-audio-snmp-port', screen.audio_snmp_port || '');
}

function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val;
}

function cancelScreenConfig() {
    selectedConfigId = null;
    document.getElementById('screen-config-form').style.display = 'none';
    document.getElementById('settings-empty-state').style.display = 'flex';
    renderConfigScreenList();
}

function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
}

async function saveScreenConfig() {
    console.log("DEBUG: saveScreenConfig CALLED");
    if (!selectedConfigId) {
        console.warn("DEBUG: No selectedConfigId, aborting save.");
        return;
    }

    const safeInt = (id, def = 0) => {
        const val = getVal(id);
        if (!val || val.trim() === '') return def;
        const parsed = parseInt(val);
        return isNaN(parsed) ? def : parsed;
    };

    const payload = {
        id: selectedConfigId,
        name: getVal('cfg-auditorium-name'),

        // Server
        server_type: getVal('cfg-server-type'),
        server_model: getVal('cfg-server-model'),
        server_name: getVal('cfg-server-name'),
        ims_ip: getVal('cfg-server-ip'),
        server_user: getVal('cfg-server-user'),
        server_pass: getVal('cfg-server-pass'),
        server_port: safeInt('cfg-server-port', 80),
        server_snmp_port: safeInt('cfg-server-snmp-port', 161),
        remote_mode: getVal('cfg-remote-mode'),
        vnc_port: safeInt('cfg-vnc-port', 5900),

        // Projector
        proj_type: getVal('cfg-proj-type'),
        proj_name: getVal('cfg-proj-name'),
        projector_ip: getVal('cfg-proj-ip'),
        proj_port: safeInt('cfg-proj-port', 161),
        proj_snmp_port: safeInt('cfg-proj-snmp-port', 161),

        // Audio
        audio_type: getVal('cfg-audio-type'),
        audio_name: getVal('cfg-audio-name'),
        audio_ip: getVal('cfg-audio-ip'),
        audio_port: safeInt('cfg-audio-port', 80),
        audio_snmp_port: safeInt('cfg-audio-snmp-port', 161)
    };

    console.log("DEBUG: Sending Payload:", JSON.stringify(payload));

    try {
        const res = await apiFetch('/api/config/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        console.log("DEBUG: Response Status:", res.status);
        const data = await res.json();
        console.log("DEBUG: Response Data:", data);

        if (data.status === 'ok') {
            showAlertModal("Configuration Saved Successfully!");

            // Update Local Cache Optimistically
            if (CACHED_STATUS_DATA[selectedConfigId]) {
                CACHED_STATUS_DATA[selectedConfigId] = { ...CACHED_STATUS_DATA[selectedConfigId], ...payload };
            } else {
                const key = Object.keys(CACHED_STATUS_DATA).find(k => CACHED_STATUS_DATA[k].id == selectedConfigId);
                if (key) CACHED_STATUS_DATA[key] = { ...CACHED_STATUS_DATA[key], ...payload };
            }
            renderConfigScreenList();
        } else {
            showAlertModal("Parameters Error: " + (data.error || "Unknown Error"));
        }
    } catch (e) {
        console.error("DEBUG: Save Exception:", e);
        showAlertModal("Save Failed: " + e);
    }
}

// --- INLINE ADD FUNCTIONS ---
function toggleInlineAdd() {
    const panel = document.getElementById('inline-add-screen');
    const btn = document.querySelector('.inventory-item-add');

    if (panel.style.display === 'none' || !panel.style.display) {
        panel.style.display = 'block';
        btn.style.display = 'none';
        setTimeout(() => document.getElementById('new-screen-input').focus(), 100);
    } else {
        panel.style.display = 'none';
        btn.style.display = 'flex';
        document.getElementById('new-screen-input').value = '';
    }
}

async function confirmInlineAdd() {
    const input = document.getElementById('new-screen-input');
    const name = input.value.trim();

    if (!name) {
        showAlertModal("Please enter a theater name.");
        return;
    }

    try {
        const res = await apiFetch('/api/config/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, ip: '' })
        });
        const data = await res.json();

        if (data.status === 'ok') {
            toggleInlineAdd();

            // FORCE CLEAR CACHE TO PREVENT GHOSTS
            if (typeof CACHED_STATUS_DATA !== 'undefined') CACHED_STATUS_DATA = {};

            // Refresh Inventory - We need to update cache
            if (window.fetchSystemStatus) await fetchSystemStatus();

            // Manual patch if fetchSystemStatus is not blocking or instant
            if (typeof CACHED_STATUS_DATA !== 'undefined' && data.server) {
                CACHED_STATUS_DATA[data.id] = data.server;
            }

            renderConfigScreenList();

            // Auto-select new screen
            loadScreenConfig(data.id);
        } else {
            showAlertModal("Add failed: " + data.error);
        }
    } catch (e) {
        showAlertModal("Add failed: " + e);
    }
}

async function deleteCurrentScreen(id = null) {
    const targetId = id || selectedConfigId;
    if (!targetId) return;

    showConfirmModal("Are you sure you want to decommission (delete) this auditorium?", async () => {
        try {
            const res = await apiFetch('/api/config/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: targetId })
            });
            const data = await res.json();

            if (data.status === 'ok') {
                if (CACHED_STATUS_DATA[targetId]) delete CACHED_STATUS_DATA[targetId];
                else {
                    const key = Object.keys(CACHED_STATUS_DATA).find(k => CACHED_STATUS_DATA[k].id == targetId);
                    if (key) delete CACHED_STATUS_DATA[key];
                }

                if (selectedConfigId == targetId) {
                    selectedConfigId = null;
                    document.getElementById('screen-config-form').style.display = 'none';
                    document.getElementById('settings-empty-state').style.display = 'flex';
                }

                renderConfigScreenList();
            } else {
                showAlertModal("Delete failed: " + data.error);
            }
        } catch (e) {
            showAlertModal("Delete Error: " + e);
        }
    });
}

// ============================================================================
// HTTP POLLING FOR REAL-TIME UPDATES (INDUSTRY STANDARD TMS APPROACH)
// ============================================================================

// Start HTTP polling every 3 seconds (same as reference TMS systems)
// This ensures the UI is always in sync even if WebSocket fails
setInterval(fetchTMSData, 3000);

console.log("✅ HTTP Polling initialized (3-second interval)");

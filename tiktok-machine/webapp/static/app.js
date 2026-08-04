// TikTok Auto-Posting Machine — Frontend App

const API = '';  // Same origin (served by FastAPI)
let refreshInterval;
let products = [];

// ── Initialization ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    loadDashboard();
    loadProducts();
    startAutoRefresh();
});

function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');

            // Load tab-specific data
            const tab = btn.dataset.tab;
            if (tab === 'posts') loadPosts();
            if (tab === 'captions') { loadCaptions(); loadProducts(); }
            if (tab === 'products') loadProductsDetail();
            if (tab === 'config') loadConfig();
            if (tab === 'analytics') loadAnalytics();
            if (tab === 'events') loadEvents();
            if (tab === 'tools') loadCookieStatus();
        });
    });
}

function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
        if (activeTab === 'dashboard') loadDashboard();
    }, 30000);  // 30 seconds
}

// ── API Helper ────────────────────────────────────────────────────────

async function api(method, path, body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${API}${path}`, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
    }
    return res.json();
}

function setConnectionStatus(ok) {
    const dot = document.getElementById('connection-status');
    const text = document.getElementById('connection-text');
    if (ok) {
        dot.className = 'status-dot connected';
        text.textContent = 'Connected';
    } else {
        dot.className = 'status-dot error';
        text.textContent = 'Disconnected';
    }
}

// ── Dashboard ─────────────────────────────────────────────────────────

async function loadDashboard() {
    try {
        const data = await api('GET', '/api/status');
        setConnectionStatus(true);

        // Stats
        document.getElementById('stat-posted-today').textContent = data.posted_today;
        document.getElementById('stat-target').textContent = `/ ${data.daily_target}`;
        document.getElementById('stat-products').textContent = Object.keys(data.stock_counts).length;
        const totalStock = Object.values(data.stock_counts).reduce((a, b) => a + b, 0);
        document.getElementById('stat-stock').textContent = totalStock;

        // Cookie
        const cookie = data.cookie_status;
        document.getElementById('stat-cookie-age').textContent = cookie.exists ? `${cookie.age_days}d` : 'N/A';
        const cookieStatus = document.getElementById('stat-cookie-status');
        if (cookie.needs_refresh) {
            cookieStatus.textContent = ' Needs refresh!';
            cookieStatus.style.color = 'var(--accent)';
        } else if (cookie.exists) {
            cookieStatus.textContent = `Max: ${cookie.max_age_days}d`;
            cookieStatus.style.color = 'var(--accent-green)';
        } else {
            cookieStatus.textContent = 'No cookie file';
            cookieStatus.style.color = 'var(--accent-yellow)';
        }

        // Compact views chart (from /api/analytics)
        renderDashboardChart();

        // Stock list
        const stockList = document.getElementById('stock-list');
        if (Object.keys(data.stock_counts).length === 0) {
            stockList.innerHTML = '<div class="empty-state">No products synced yet</div>';
        } else {
            stockList.innerHTML = Object.entries(data.stock_counts).map(([name, count]) => {
                const warn = count < 5 ? ' ⚠️' : '';
                const color = count < 5 ? 'var(--accent-yellow)' : 'var(--text-primary)';
                return `<div class="list-item">
                    <span class="label">${name}</span>
                    <span class="meta" style="color:${color}">${count} videos${warn}</span>
                </div>`;
            }).join('');
        }

        // Priority list
        const priorityList = document.getElementById('priority-list');
        if (data.products_due.length === 0) {
            priorityList.innerHTML = '<div class="empty-state">No products due</div>';
        } else {
            priorityList.innerHTML = data.products_due.slice(0, 8).map(p => {
                const last = p.last_posted && p.last_posted !== '1970-01-01'
                    ? p.last_posted.slice(0, 10) : 'Never';
                return `<div class="list-item">
                    <span class="label">${p.product_name}</span>
                    <span class="meta">${p.stock_count} stock · Last: ${last}</span>
                </div>`;
            }).join('');
        }

        // Recent posts
        const postsDiv = document.getElementById('recent-posts');
        if (data.recent_posts.length === 0) {
            postsDiv.innerHTML = '<div class="empty-state">No posts yet</div>';
        } else {
            postsDiv.innerHTML = `<table>
                <thead><tr><th>Product</th><th>Status</th><th>Time</th><th>Caption</th></tr></thead>
                <tbody>${data.recent_posts.map(p => `
                    <tr>
                        <td>${p.product_name}</td>
                        <td><span class="badge badge-${p.status.toLowerCase()}">${p.status}</span></td>
                        <td>${formatTime(p.posted_at)}</td>
                        <td>${truncate(p.caption_text, 50)}</td>
                    </tr>`).join('')}
                </tbody></table>`;
        }

        // Recent events
        const eventsDiv = document.getElementById('recent-events');
        if (data.recent_events.length === 0) {
            eventsDiv.innerHTML = '<div class="empty-state">No events</div>';
        } else {
            eventsDiv.innerHTML = data.recent_events.map(e => {
                const emoji = {
                    UPLOAD_SUCCESS: '✅', UPLOAD_FAIL: '❌', COOKIE_WARNING: '⚠️',
                    STOCK_LOW: '⚠️', PROXY_FAIL: '', AI_CALL: '🤖',
                    SCRAPE_COMPLETE: '🔍',
                }[e.event_type] || 'ℹ️';
                return `<div class="list-item">
                    <span class="label">${emoji} ${e.message}</span>
                    <span class="meta">${formatTime(e.occurred_at)}</span>
                </div>`;
            }).join('');
        }

        document.getElementById('last-updated').textContent =
            `Updated: ${new Date().toLocaleTimeString()}`;

    } catch (err) {
        setConnectionStatus(false);
        console.error('Dashboard load failed:', err);
    }
}

// ── Posts ─────────────────────────────────────────────────────────────

async function loadPosts() {
    const product = document.getElementById('post-filter-product').value;
    const status = document.getElementById('post-filter-status').value;

    try {
        const posts = await api('GET', `/api/posts?product=${product}&status=${status}&limit=100`);
        const div = document.getElementById('posts-table');

        if (posts.length === 0) {
            div.innerHTML = '<div class="empty-state">No posts found</div>';
            return;
        }

        div.innerHTML = `<table>
            <thead><tr><th>Product</th><th>Status</th><th>Posted</th><th>Caption</th><th>Proxy IP</th></tr></thead>
            <tbody>${posts.map(p => `
                <tr>
                    <td>${p.product_name}</td>
                    <td><span class="badge badge-${p.status.toLowerCase()}">${p.status}</span></td>
                    <td>${formatTime(p.posted_at)}</td>
                    <td>${truncate(p.caption_text, 60)}</td>
                    <td>${p.proxy_ip_used || '-'}</td>
                </tr>`).join('')}
            </tbody></table>`;

        // Update product filter
        const uniqueProducts = [...new Set(posts.map(p => p.product_name))];
        updateProductFilter('post-filter-product', uniqueProducts);

    } catch (err) {
        console.error('Posts load failed:', err);
    }
}

// ── Captions ──────────────────────────────────────────────────────────

async function loadCaptions() {
    const product = document.getElementById('caption-filter-product').value;
    try {
        const captions = await api('GET', `/api/captions?product=${product}`);
        const div = document.getElementById('captions-list');

        if (captions.length === 0) {
            div.innerHTML = '<div class="empty-state">No captions. Use /growth on Telegram or add manually.</div>';
            return;
        }

        div.innerHTML = captions.map(c => {
            const checked = c.compliance_checked ? '✅' : '⚠️';
            const source = c.source || 'manual';
            return `<div class="list-item">
                <div>
                    <div class="label">${checked} [${source}] ${c.product_name || 'Generic'}</div>
                    <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:4px">"${c.caption_text}"</div>
                </div>
                <div class="meta">Used: ${c.times_used || 0}x</div>
            </div>`;
        }).join('');

        updateProductFilter('caption-filter-product',
            [...new Set(captions.map(c => c.product_name).filter(Boolean))]);
        updateProductFilter('add-caption-product',
            [...new Set(captions.map(c => c.product_name).filter(Boolean))]);

    } catch (err) {
        console.error('Captions load failed:', err);
    }
}

async function addCaption() {
    const product = document.getElementById('add-caption-product').value || null;
    const text = document.getElementById('add-caption-text').value.trim();
    if (!text) return;

    try {
        const result = await api('POST', '/api/captions', {
            product_name: product,
            caption_text: text,
            source: 'manual',
        });
        alert(`✅ Caption added: ${result.caption}`);
        document.getElementById('add-caption-text').value = '';
        loadCaptions();
    } catch (err) {
        alert(`❌ ${err.message}`);
    }
}

// ── Products ──────────────────────────────────────────────────────────

async function loadProducts() {
    try {
        products = await api('GET', '/api/products');
        updateProductFilter('post-filter-product', products.map(p => p.name));
        updateProductFilter('caption-filter-product', products.map(p => p.name));
        updateProductFilter('add-caption-product', products.map(p => p.name));
    } catch (err) {
        console.error('Products load failed:', err);
    }
}

async function loadProductsDetail() {
    try {
        const data = await api('GET', '/api/products');
        const div = document.getElementById('products-list');

        if (data.length === 0) {
            div.innerHTML = '<div class="empty-state">No products configured. Edit content/products.json</div>';
            return;
        }

        div.innerHTML = data.map(p => `
            <div class="list-item">
                <div>
                    <div class="label">${p.name}</div>
                    <div style="color:var(--text-secondary);font-size:0.8rem">${p.product_id} · ${p.description || 'No description'}</div>
                    ${p.keywords && p.keywords.length ? `<div style="color:var(--accent-blue);font-size:0.75rem;margin-top:4px">${p.keywords.join(', ')}</div>` : ''}
                </div>
                <div class="meta">${p.stock} raw videos</div>
            </div>`).join('');

    } catch (err) {
        console.error('Products detail failed:', err);
    }
}

// ── Config ────────────────────────────────────────────────────────────

async function loadConfig() {
    try {
        const config = await api('GET', '/api/config');
        const div = document.getElementById('config-sections');

        div.innerHTML = Object.entries(config).map(([section, values]) => {
            if (typeof values !== 'object' || values === null) return '';
            const rows = Object.entries(values).map(([key, value]) => {
                const displayVal = typeof value === 'object' ? JSON.stringify(value) : String(value);
                return `<div class="config-row">
                    <span class="key">${key}</span>
                    <span class="value" data-section="${section}" data-key="${key}"
                          onclick="editConfig(this)">${displayVal}</span>
                </div>`;
            }).join('');

            return `<div class="config-section">
                <h4>${section}</h4>
                ${rows}
            </div>`;
        }).join('');

    } catch (err) {
        console.error('Config load failed:', err);
    }
}

function editConfig(el) {
    const section = el.dataset.section;
    const key = el.dataset.key;
    const current = el.textContent;

    const input = document.createElement('input');
    input.type = 'text';
    input.value = current;
    input.onblur = () => saveConfig(section, key, input.value, el);
    input.onkeydown = (e) => { if (e.key === 'Enter') input.blur(); };

    el.textContent = '';
    el.appendChild(input);
    input.focus();
    input.select();
}

async function saveConfig(section, key, value, el) {
    try {
        const result = await api('PUT', '/api/config', { section, key, value });
        el.textContent = result.value;
        el.style.color = 'var(--accent-green)';
        setTimeout(() => el.style.color = '', 2000);
    } catch (err) {
        el.textContent = value;  // Revert
        alert(`❌ ${err.message}`);
    }
}

// ─ Events ────────────────────────────────────────────────────────────

async function loadEvents() {
    const type = document.getElementById('event-filter-type').value;
    try {
        const events = await api('GET', `/api/events?event_type=${type}&limit=100`);
        const div = document.getElementById('events-list');

        if (events.length === 0) {
            div.innerHTML = '<div class="empty-state">No events</div>';
            return;
        }

        const emoji = {
            UPLOAD_SUCCESS: '✅', UPLOAD_FAIL: '❌', COOKIE_WARNING: '⚠️',
            STOCK_LOW: '⚠️', PROXY_FAIL: '🚫', AI_CALL: '🤖',
            SCRAPE_COMPLETE: '🔍', CONFIG_CHANGE: '️',
        };

        div.innerHTML = events.map(e => `
            <div class="list-item">
                <div>
                    <div class="label">${emoji[e.event_type] || 'ℹ️'} ${e.message}</div>
                    ${e.metadata ? `<div style="color:var(--text-secondary);font-size:0.75rem;margin-top:4px;font-family:monospace">${truncate(e.metadata, 100)}</div>` : ''}
                </div>
                <div class="meta">${formatTime(e.occurred_at)}</div>
            </div>`).join('');

    } catch (err) {
        console.error('Events load failed:', err);
    }
}

// ── Tools ─────────────────────────────────────────────────────────────

async function testProxy() {
    const div = document.getElementById('proxy-result');
    div.textContent = 'Testing...';
    div.className = 'result-box';

    try {
        const result = await api('POST', '/api/actions/test-proxy');
        div.textContent = result.message;
        div.className = `result-box ${result.success ? 'success' : 'error'}`;
    } catch (err) {
        div.textContent = `Error: ${err.message}`;
        div.className = 'result-box error';
    }
}

async function triggerSync() {
    const div = document.getElementById('sync-result');
    div.textContent = 'Syncing...';
    div.className = 'result-box';

    try {
        const result = await api('POST', '/api/actions/sync');
        const stockInfo = result.stock_report
            ? Object.entries(result.stock_report).map(([k, v]) => `${k}: ${v.count || v}`).join('\n')
            : 'No stock data';
        div.textContent = `✅ Sync ${result.success ? 'succeeded' : 'failed'}\n${stockInfo}`;
        div.className = `result-box ${result.success ? 'success' : 'error'}`;
    } catch (err) {
        div.textContent = `Error: ${err.message}`;
        div.className = 'result-box error';
    }
}

async function loadCookieStatus() {
    const div = document.getElementById('cookie-detail');
    try {
        const status = await api('GET', '/api/actions/cookie-status');
        if (!status.exists) {
            div.textContent = '❌ Cookie file not found. Please login to TikTok.';
            div.className = 'result-box error';
        } else {
            const warning = status.needs_refresh ? '⚠️ Needs refresh!' : '✅ OK';
            div.innerHTML = `Path: ${status.path}\nAge: ${status.age_days} days (max: ${status.max_age_days})\nStatus: ${warning}`;
            div.className = `result-box ${status.needs_refresh ? 'warning' : 'success'}`;
        }
    } catch (err) {
        div.textContent = `Error: ${err.message}`;
        div.className = 'result-box error';
    }
}

async function triggerRelogin() {
    const div = document.getElementById('relogin-result');
    const imgContainer = document.getElementById('qr-image-container');
    div.textContent = ' Generating QR code... (takes ~5 seconds)';
    div.className = 'result-box';
    imgContainer.innerHTML = '';

    try {
        const result = await api('POST', '/api/actions/relogin');
        div.textContent = result.message;
        div.className = `result-box ${result.success ? 'success' : 'error'}`;

        if (result.success && result.qr_path) {
            // Load QR image
            const img = document.createElement('img');
            img.src = `/api/qr-image?path=${encodeURIComponent(result.qr_path)}`;
            img.style.maxWidth = '300px';
            img.style.border = '2px solid var(--accent)';
            img.style.borderRadius = '8px';
            img.style.marginTop = '16px';
            imgContainer.appendChild(img);

            const note = document.createElement('p');
            note.style.color = 'var(--text-secondary)';
            note.style.fontSize = '0.85rem';
            note.style.marginTop = '8px';
            note.textContent = '📱 Scan with TikTok app (expires in 60 seconds)';
            imgContainer.appendChild(note);
        }
    } catch (err) {
        div.textContent = `Error: ${err.message}`;
        div.className = 'result-box error';
    }
}

// ── Utilities ─────────────────────────────────────────────────────────

function updateProductFilter(selectId, productNames) {
    const select = document.getElementById(selectId);
    if (!select) return;
    const current = select.value;
    const firstOption = select.options[0].outerHTML;
    select.innerHTML = firstOption + productNames.map(n =>
        `<option value="${n}">${n}</option>`
    ).join('');
    select.value = current;
}

function formatTime(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleString('en-GB', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
    });
}

function truncate(str, len) {
    if (!str) return '-';
    return str.length > len ? str.slice(0, len) + '...' : str;
}

// ── Analytics / Charts ─────────────────────────────────────────────────

const chartInstances = {};

function makeChart(canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
    chartInstances[canvasId] = new Chart(canvas, config);
}

function chartBase(dark = true) {
    const gridColor = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
    const tickColor = dark ? '#8a90a2' : '#666';
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: dark ? '#e8eaf0' : '#333' } } },
        scales: {
            x: { ticks: { color: tickColor }, grid: { color: gridColor } },
            y: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } },
        },
    };
}

async function renderDashboardChart() {
    try {
        const ana = await api('GET', '/api/analytics?days=7');
        const labels = ana.views_by_day.map(r => (r.snap_date || '').slice(5));
        const net = ana.views_delta_by_day.map(r => r.views || 0);
        if (!labels.length) {
            chartEmpty('chart-dashboard-empty');
            return;
        }
        chartClearEmpty('chart-dashboard-empty');
        makeChart('chart-dashboard-views', {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Views / day', data: net,
                    borderColor: '#FFD700',
                    backgroundColor: 'rgba(255,215,0,0.18)',
                    fill: true, tension: 0.3,
                    pointRadius: 2,
                }],
            },
            options: {
                ...chartBase(),
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: c => `${c.parsed.y} views` } },
                },
                scales: {
                    x: { ticks: { color: '#8a90a2', maxTicksLimit: 7 }, grid: { display: false } },
                    y: { beginAtZero: true, ticks: { color: '#8a90a2' }, grid: { color: 'rgba(255,255,255,0.06)' } },
                },
            },
        });
    } catch (err) {
        console.error('Dashboard chart failed:', err);
    }
}

function chartEmpty(id) {
    const el = document.getElementById(id);
    if (el) el.textContent = 'No data yet — post videos and run a scrape + reconcile first.';
}

function chartClearEmpty(id) {
    const el = document.getElementById(id);
    if (el) el.textContent = '';
}

async function loadAnalytics() {
    try {
        const [ana, growth, ops, queue] = await Promise.all([
            api('GET', '/api/analytics?days=7'),
            api('GET', '/api/growth-report'),
            api('GET', '/api/ops-report'),
            api('GET', '/api/queue-status'),
        ]);

        // ── Views over time (line): cumulative + net-new per day ──
        const labels = ana.views_by_day.map(r => (r.snap_date || '').slice(5));
        const cum = ana.views_by_day.map(r => r.views || 0);
        const net = ana.views_delta_by_day.map(r => r.views || 0);

        if (labels.length) {
            chartClearEmpty('chart-views-empty');
            makeChart('chart-views-line', {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        { label: 'Total views', data: cum, borderColor: '#FE2C55',
                          backgroundColor: 'rgba(254,44,85,0.15)', fill: true, tension: 0.3 },
                        { label: 'Net new / day', data: net, borderColor: '#FFD700',
                          backgroundColor: 'rgba(255,215,0,0.12)', fill: true, tension: 0.3 },
                    ],
                },
                options: chartBase(),
            });
        } else {
            chartEmpty('chart-views-empty');
        }

        // ── Views by product (horizontal bar) ──
        const prods = ana.product_views.map(r => r.product);
        const prodViews = ana.product_views.map(r => r.views || 0);
        if (prods.length) {
            chartClearEmpty('chart-product-empty');
            makeChart('chart-product-bar', {
                type: 'bar',
                data: {
                    labels: prods,
                    datasets: [{ label: 'Views', data: prodViews,
                                backgroundColor: '#FFD700' }],
                },
                options: {
                    ...chartBase(),
                    indexAxis: 'y',
                    plugins: { legend: { display: false } },
                },
            });
        } else {
            chartEmpty('chart-product-empty');
        }

        // ── Upload queue ──
        const queueDiv = document.getElementById('queue-list');
        if (!queue.count) {
            queueDiv.innerHTML = '<div class="empty-state">Queue is empty — run video_processor.py</div>';
        } else {
            queueDiv.innerHTML = queue.items.map(it =>
                `<div class="list-item">
                    <span class="label">${it.product_folder || '?'} · ${it.filename}</span>
                    <span class="meta">${it.title || ''} · ${it.size_mb != null ? it.size_mb + 'MB' : ''}${it.style ? ' · ' + it.style : ''}</span>
                </div>`).join('');
        }

        // ── Growth + OPS reports ──
        const growEl = document.getElementById('growth-report-text');
        growEl.textContent = growth.exists ? growth.report : '(no growth report yet — run ai_growth.py --ai)';
        const opsEl = document.getElementById('ops-report-text');
        opsEl.textContent = ops.exists ? ops.report : '(no ops report yet — run generate_report.py)';

    } catch (err) {
        console.error('Analytics load failed:', err);
    }
}

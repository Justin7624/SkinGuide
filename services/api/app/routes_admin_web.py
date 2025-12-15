# services/api/app/routes_admin_web.py

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["admin-ui"])

_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>SkinGuide Admin</title>
  <style>
    :root { --bg:#0b0c10; --card:#12141c; --ink:#e8eaf0; --muted:#9aa3b2; --accent:#7c5cff; }
    html,body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Inter,Arial;background:var(--bg);color:var(--ink);}
    .wrap{max-width:1100px;margin:0 auto;padding:20px;}
    .top{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
    .title{font-size:18px;font-weight:700}
    .row{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:12px;}
    .card{background:var(--card);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px;box-shadow:0 12px 30px rgba(0,0,0,.25);}
    .k{color:var(--muted);font-size:12px}
    .v{font-size:22px;font-weight:800;margin-top:4px}
    input,button,select{background:#0f1118;color:var(--ink);border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:10px 12px}
    button{cursor:pointer}
    button.primary{background:var(--accent);border:none;font-weight:700}
    .span4{grid-column:span 4}
    .span6{grid-column:span 6}
    .span12{grid-column:span 12}
    .muted{color:var(--muted)}
    table{width:100%;border-collapse:collapse}
    th,td{font-size:12px;text-align:left;padding:8px;border-bottom:1px solid rgba(255,255,255,.08);vertical-align:top}
    .pill{display:inline-block;padding:4px 8px;border-radius:999px;background:rgba(124,92,255,.15);border:1px solid rgba(124,92,255,.35);font-size:12px}
    pre{white-space:pre-wrap;word-break:break-word;background:#0f1118;border:1px solid rgba(255,255,255,.08);padding:10px;border-radius:12px;margin:0}
    a{color:#b8a7ff}
    .small{font-size:12px}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">SkinGuide Admin</div>
      <div class="muted small">This page contains no data until you provide an Admin Key. All API calls require X-Admin-Key.</div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <input id="adminKey" placeholder="Admin Key" style="min-width:260px" />
      <button class="primary" onclick="saveKey()">Save</button>
      <button onclick="refreshAll()">Refresh</button>
    </div>
  </div>

  <div class="row" style="margin-top:16px">
    <div class="card span4"><div class="k">Sessions</div><div class="v" id="sessions">—</div></div>
    <div class="card span4"><div class="k">Analyzes (24h)</div><div class="v" id="an24">—</div></div>
    <div class="card span4"><div class="k">Active Model</div><div class="v" id="activeModel" style="font-size:18px">—</div></div>

    <div class="card span4"><div class="k">Donations</div><div class="v" id="donations">—</div><div class="muted small">Withdrawn: <span id="withdrawn">—</span></div></div>
    <div class="card span4"><div class="k">Labeled</div><div class="v" id="labeled">—</div></div>
    <div class="card span4"><div class="k">Consent opt-in</div><div class="muted small">Progress: <span id="optProg">—</span>%</div><div class="muted small">Donate: <span id="optDon">—</span>%</div></div>

    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <div>
          <div class="k">Metrics</div>
          <div class="muted small">Time series (last N days) for charts</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <select id="days">
            <option value="7">7d</option>
            <option value="30" selected>30d</option>
            <option value="90">90d</option>
            <option value="180">180d</option>
          </select>
          <button onclick="loadMetrics()">Load metrics</button>
          <span class="muted small" id="range">—</span>
        </div>
      </div>
      <div style="margin-top:12px" class="small muted">
        <div><span class="pill">analyzes</span> <span id="sparkA">—</span></div>
        <div style="margin-top:8px"><span class="pill">donations</span> <span id="sparkD">—</span></div>
        <div style="margin-top:8px"><span class="pill">labels</span> <span id="sparkL">—</span></div>
      </div>
    </div>

    <div class="card span6">
      <div class="k">Event type breakdown (24h)</div>
      <div id="evBreak" class="small" style="margin-top:10px">—</div>
    </div>

    <div class="card span6">
      <div class="k">Model version breakdown (24h)</div>
      <div id="mvBreak" class="small" style="margin-top:10px">—</div>
    </div>

    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <div>
          <div class="k">Audit (latest)</div>
          <div class="muted small">Paginated. Use "Load more" to page backward.</div>
        </div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <button onclick="loadAudit(true)">Refresh audit</button>
          <button onclick="loadAudit(false)">Load more</button>
          <span class="muted small" id="auditStatus">—</span>
        </div>
      </div>
      <table style="margin-top:12px">
        <thead>
          <tr><th>ID</th><th>Time</th><th>Type</th><th>Session</th><th>Payload</th></tr>
        </thead>
        <tbody id="auditRows"></tbody>
      </table>
    </div>

    <div class="card span12">
      <div class="k">Exports (CSV)</div>
      <div class="muted small">These download via authenticated requests. Click to open in a new tab after saving your Admin Key.</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px" class="small">
        <a href="#" onclick="dl('/v1/admin/export/audit.csv?since_days=7');return false;">audit.csv (7d)</a>
        <a href="#" onclick="dl('/v1/admin/export/sessions.csv?since_days=30');return false;">sessions.csv (30d)</a>
        <a href="#" onclick="dl('/v1/admin/export/consents.csv');return false;">consents.csv</a>
        <a href="#" onclick="dl('/v1/admin/export/donations.csv?since_days=90');return false;">donations.csv (90d)</a>
        <a href="#" onclick="dl('/v1/admin/export/labels.csv?since_days=365');return false;">labels.csv (365d)</a>
        <a href="#" onclick="dl('/v1/admin/export/models.csv');return false;">models.csv</a>
      </div>
      <div class="muted small" style="margin-top:10px">If you deploy publicly, put this page behind your own gateway auth (e.g., Cloudflare Access / basic auth) even though the APIs require X-Admin-Key.</div>
    </div>

  </div>
</div>

<script>
  const keyEl = document.getElementById('adminKey');
  const saved = sessionStorage.getItem('ADMIN_KEY');
  if (saved) keyEl.value = saved;

  let auditBeforeId = null;

  function saveKey(){
    sessionStorage.setItem('ADMIN_KEY', keyEl.value.trim());
    refreshAll();
  }

  function h(){
    const k = (sessionStorage.getItem('ADMIN_KEY') || '').trim();
    return { 'X-Admin-Key': k };
  }

  async function api(path){
    const r = await fetch(path, { headers: h() });
    if (!r.ok) throw new Error(await r.text());
    return r;
  }

  async function refreshAll(){
    await loadSummary();
    await loadMetrics();
    await loadAudit(true);
  }

  function spark(points){
    // points: [{date,value}]
    if (!points || !points.length) return '—';
    const vals = points.map(p => p.value);
    const max = Math.max(...vals, 1);
    const bars = vals.map(v => {
      const t = Math.round((v / max) * 8);
      return "▁▂▃▄▅▆▇█"[Math.max(0, Math.min(7, t))];
    });
    const total = vals.reduce((a,b)=>a+b,0);
    return `${bars.join('')}  (total ${total})`;
  }

  function renderBreakdown(elId, items){
    const el = document.getElementById(elId);
    if (!items || !items.length){ el.textContent = '—'; return; }
    el.innerHTML = items.map(it => `<div style="display:flex;justify-content:space-between;gap:10px"><span>${it.key}</span><span class="muted">${it.value}</span></div>`).join('');
  }

  async function loadSummary(){
    try{
      const r = await api('/v1/admin/summary');
      const j = await r.json();
      document.getElementById('sessions').textContent = j.total_sessions;
      document.getElementById('an24').textContent = j.total_analyzes_24h;
      document.getElementById('activeModel').textContent = j.active_model_version || '—';
      document.getElementById('donations').textContent = j.total_donations;
      document.getElementById('withdrawn').textContent = j.total_donations_withdrawn;
      document.getElementById('labeled').textContent = j.total_labeled;
      document.getElementById('optProg').textContent = j.consent_opt_in_progress_pct;
      document.getElementById('optDon').textContent = j.consent_opt_in_donate_pct;
    }catch(e){
      console.error(e);
    }
  }

  async function loadMetrics(){
    const days = document.getElementById('days').value;
    try{
      const r = await api(`/v1/admin/metrics?days=${encodeURIComponent(days)}`);
      const j = await r.json();
      document.getElementById('range').textContent = `${j.start_date} → ${j.end_date}`;
      document.getElementById('sparkA').textContent = spark(j.analyzes);
      document.getElementById('sparkD').textContent = spark(j.donations_created);
      document.getElementById('sparkL').textContent = spark(j.labels_created);
      renderBreakdown('evBreak', (j.event_type_breakdown_24h && j.event_type_breakdown_24h.items) || []);
      renderBreakdown('mvBreak', (j.model_version_breakdown_24h && j.model_version_breakdown_24h.items) || []);
    }catch(e){
      console.error(e);
    }
  }

  async function loadAudit(reset){
    try{
      if (reset) auditBeforeId = null;
      const path = auditBeforeId ? `/v1/admin/audit?before_id=${auditBeforeId}&limit=50` : `/v1/admin/audit?limit=50`;
      const r = await api(path);
      const j = await r.json();
      if (reset) document.getElementById('auditRows').innerHTML = '';
      const tbody = document.getElementById('auditRows');
      for (const it of j.items){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${it.id}</td><td class="muted">${it.created_at}</td><td>${it.event_type}</td><td class="muted">${it.session_id || ''}</td><td><pre>${(it.payload_json||'').slice(0,800)}</pre></td>`;
        tbody.appendChild(tr);
      }
      auditBeforeId = j.next_before_id || auditBeforeId;
      document.getElementById('auditStatus').textContent = auditBeforeId ? `next before_id=${auditBeforeId}` : 'end';
    }catch(e){
      console.error(e);
    }
  }

  async function dl(path){
    try{
      const k = (sessionStorage.getItem('ADMIN_KEY') || '').trim();
      if (!k){ alert('Set Admin Key first'); return; }
      const r = await fetch(path, { headers: { 'X-Admin-Key': k } });
      if (!r.ok){ alert(await r.text()); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = path.split('/').pop().split('?')[0];
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }catch(e){
      alert(String(e));
    }
  }

  // initial load
  if (saved) refreshAll();
</script>
</body>
</html>
"""

@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(_HTML)

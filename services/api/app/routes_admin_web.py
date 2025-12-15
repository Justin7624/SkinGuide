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
    :root { --bg:#0b0c10; --card:#12141c; --ink:#e8eaf0; --muted:#9aa3b2; --accent:#7c5cff; --ok:#25d0a6; --bad:#ff6b6b; }
    html,body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Inter,Arial;background:var(--bg);color:var(--ink);}
    .wrap{max-width:1200px;margin:0 auto;padding:20px;}
    .top{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
    .title{font-size:18px;font-weight:800}
    .row{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:12px;}
    .card{background:var(--card);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px;box-shadow:0 12px 30px rgba(0,0,0,.25);}
    .k{color:var(--muted);font-size:12px}
    .v{font-size:22px;font-weight:900;margin-top:4px}
    input,button,select,textarea{background:#0f1118;color:var(--ink);border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:10px 12px}
    button{cursor:pointer}
    button.primary{background:var(--accent);border:none;font-weight:900}
    button.good{background:rgba(37,208,166,.2);border:1px solid rgba(37,208,166,.35);font-weight:800}
    button.bad{background:rgba(255,107,107,.15);border:1px solid rgba(255,107,107,.35);font-weight:800}
    .span4{grid-column:span 4}
    .span6{grid-column:span 6}
    .span12{grid-column:span 12}
    .muted{color:var(--muted)}
    .small{font-size:12px}
    .hide{display:none}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    .imgbox{background:#0f1118;border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:10px}
    .stage{position:relative;overflow:auto;border-radius:12px;border:1px solid rgba(255,255,255,.06);background:#0b0c10}
    img{display:block;max-width:none}
    canvas.overlay{position:absolute;left:0;top:0;pointer-events:none}
    .sliderrow{display:grid;grid-template-columns:260px 1fr 64px;gap:10px;align-items:center;margin-top:8px}
    .rowline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .tabs{display:flex;gap:8px;flex-wrap:wrap}
    .tab{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:#0f1118;color:var(--muted);cursor:pointer}
    .tab.active{background:rgba(124,92,255,.18);border-color:rgba(124,92,255,.45);color:var(--ink)}
    .badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid rgba(255,255,255,.12);font-size:12px;color:var(--muted)}
    .badc{color:var(--bad)}
    pre{white-space:pre-wrap;word-break:break-word;background:#0f1118;border:1px solid rgba(255,255,255,.08);padding:10px;border-radius:12px;margin:0;max-height:420px;overflow:auto}
    .drawer{position:fixed;right:16px;top:16px;bottom:16px;width:min(680px, calc(100vw - 32px));background:var(--card);
      border:1px solid rgba(255,255,255,.12);border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.45);padding:14px;overflow:auto}
    table{width:100%;border-collapse:collapse}
    th,td{padding:8px;border-bottom:1px solid rgba(255,255,255,.08);font-size:12px}
    th{text-align:left;color:var(--muted);font-weight:800}
    .chart{width:100%;height:220px;background:#0f1118;border:1px solid rgba(255,255,255,.08);border-radius:12px}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">SkinGuide Admin</div>
      <div class="muted small" id="who">Not signed in</div>
    </div>
    <div class="rowline">
      <button id="btnLogout" class="hide" onclick="logout()">Logout</button>
    </div>
  </div>

  <!-- Login -->
  <div class="row" id="loginPanel">
    <div class="card span12">
      <div class="k">Admin login</div>
      <div class="rowline" style="margin-top:10px">
        <input id="email" placeholder="email" style="min-width:260px" />
        <input id="password" placeholder="password" type="password" style="min-width:260px" />
        <input id="totp" placeholder="2FA code (if enabled)" style="min-width:200px" />
        <input id="recovery" placeholder="Recovery code (optional)" style="min-width:240px" />
        <button class="primary" onclick="login()">Login</button>
      </div>
      <div class="small" id="loginErr" style="margin-top:8px;color:var(--bad)"></div>
    </div>
  </div>

  <!-- Dashboard -->
  <div class="row hide" id="dash">
    <div class="card span4"><div class="k">Sessions</div><div class="v" id="sessions">—</div></div>
    <div class="card span4"><div class="k">Analyzes (24h)</div><div class="v" id="an24">—</div></div>
    <div class="card span4"><div class="k">Active Model</div><div class="v" id="activeModel" style="font-size:18px">—</div></div>

    <div class="card span12">
      <div class="rowline" style="justify-content:space-between">
        <div class="tabs">
          <div class="tab active" id="tabMetrics" onclick="setTab('metrics')">Metrics</div>
          <div class="tab" id="tabModels" onclick="setTab('models')">Models</div>
        </div>
        <div class="rowline">
          <button onclick="refreshAll()">Refresh</button>
        </div>
      </div>
    </div>

    <!-- Metrics panel -->
    <div class="card span12" id="panelMetrics">
      <div class="rowline" style="justify-content:space-between;align-items:center;flex-wrap:wrap">
        <div>
          <div class="k">Metrics</div>
          <div class="muted small">Labeling metrics + model hot-reload status.</div>
        </div>
        <div class="rowline">
          <select id="mDays">
            <option value="30" selected>30d</option>
            <option value="90">90d</option>
            <option value="180">180d</option>
            <option value="365">365d</option>
          </select>
          <select id="mWindow">
            <option value="60">weights window 60d</option>
            <option value="180" selected>weights window 180d</option>
            <option value="365">weights window 365d</option>
          </select>
          <button onclick="loadMetrics()">Load</button>
        </div>
      </div>

      <div class="row" style="margin-top:12px">
        <div class="card span6">
          <div class="k">Conflict rate</div>
          <canvas id="chartConflict" class="chart"></canvas>
          <div class="muted small" id="confNote" style="margin-top:8px">—</div>
        </div>
        <div class="card span6">
          <div class="k">Escalation rate</div>
          <canvas id="chartEscal" class="chart"></canvas>
          <div class="muted small" id="escNote" style="margin-top:8px">—</div>
        </div>

        <div class="card span12">
          <div class="rowline" style="justify-content:space-between;align-items:center">
            <div>
              <div class="k">ML Hot-reload</div>
              <div class="muted small" id="hotNote">—</div>
            </div>
            <button onclick="loadHot()">Refresh</button>
          </div>
          <pre id="hotOut" style="margin-top:10px">—</pre>
        </div>
      </div>
    </div>

    <!-- Models panel -->
    <div class="card span12 hide" id="panelModels">
      <div class="rowline" style="justify-content:space-between;align-items:center;flex-wrap:wrap">
        <div>
          <div class="k">Models</div>
          <div class="muted small">List registered model artifacts, view model card, and promote to active.</div>
        </div>
        <div class="rowline">
          <button onclick="loadModels()">Reload</button>
        </div>
      </div>

      <div class="muted small" id="modelsNote" style="margin-top:10px">—</div>

      <div style="overflow:auto;margin-top:10px">
        <table id="modelsTable">
          <thead>
            <tr>
              <th>Active</th><th>Version</th><th>Created</th><th>Val loss</th><th>Actions</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>

      <div class="k" style="margin-top:14px">Model card</div>
      <pre id="modelCard" style="margin-top:8px">Select a model.</pre>
    </div>

  </div>
</div>

<script>
  let csrf = null;
  let me = null;
  let tab = "metrics";

  async function api(path, opts={}){
    opts.credentials = "include";
    opts.headers = opts.headers || {};
    if (csrf) opts.headers["X-CSRF-Token"] = csrf;
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error(await r.text());
    return r;
  }

  async function login(){
    document.getElementById('loginErr').textContent = '';
    try{
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      const totp = document.getElementById('totp').value.trim() || null;
      const recovery = document.getElementById('recovery').value.trim() || null;

      await api('/v1/admin/auth/login', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({email,password, totp_code: totp, recovery_code: recovery})
      });
      await initAuthed();
    }catch(e){
      document.getElementById('loginErr').textContent = String(e);
    }
  }

  async function logout(){
    try{ await api('/v1/admin/auth/logout', {method:'POST'}); }catch(e){}
    csrf = null; me = null;
    document.getElementById('dash').classList.add('hide');
    document.getElementById('loginPanel').classList.remove('hide');
    document.getElementById('btnLogout').classList.add('hide');
    document.getElementById('who').textContent = 'Not signed in';
  }

  async function initAuthed(){
    const r = await api('/v1/admin/auth/me');
    me = await r.json();
    csrf = me.csrf_token;
    document.getElementById('who').textContent = `Signed in: ${me.email} (${me.role})`;
    document.getElementById('loginPanel').classList.add('hide');
    document.getElementById('dash').classList.remove('hide');
    document.getElementById('btnLogout').classList.remove('hide');
    await refreshAll();
  }

  async function refreshAll(){
    await loadSummary();
    if (tab === 'metrics') {
      await loadHot();
    } else if (tab === 'models') {
      await loadModels();
    }
  }

  async function loadSummary(){
    const r = await api('/v1/admin/summary');
    const j = await r.json();
    document.getElementById('sessions').textContent = j.total_sessions;
    document.getElementById('an24').textContent = j.total_analyzes_24h;
    document.getElementById('activeModel').textContent = j.active_model_version || '—';
  }

  function setTab(next){
    tab = next;
    document.getElementById('tabMetrics').classList.toggle('active', tab==='metrics');
    document.getElementById('tabModels').classList.toggle('active', tab==='models');

    document.getElementById('panelMetrics').classList.toggle('hide', tab!=='metrics');
    document.getElementById('panelModels').classList.toggle('hide', tab!=='models');

    if (tab==='metrics') loadHot();
    if (tab==='models') loadModels();
  }

  // ----- simple chart helper (same look as before) -----
  function drawLineChart(canvasId, labels, values, opts={}){
    const c = document.getElementById(canvasId);
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    const h = c.clientHeight;
    c.width = Math.floor(w * dpr);
    c.height = Math.floor(h * dpr);
    const g = c.getContext('2d');
    g.scale(dpr,dpr);

    g.clearRect(0,0,w,h);
    const padL = 40, padR = 10, padT = 10, padB = 24;
    const iw = w - padL - padR;
    const ih = h - padT - padB;

    g.strokeStyle = "rgba(255,255,255,0.08)";
    g.lineWidth = 1;
    for(let i=0;i<=4;i++){
      const y = padT + (ih*i/4);
      g.beginPath(); g.moveTo(padL,y); g.lineTo(w-padR,y); g.stroke();
    }

    const minY = (opts.minY!=null)?opts.minY:0;
    const maxY = (opts.maxY!=null)?opts.maxY:1;

    function xAt(i){ return padL + (iw * (labels.length<=1?0:i/(labels.length-1))); }
    function yAt(v){
      const t = (v - minY) / (maxY - minY || 1);
      return padT + ih - (ih * Math.max(0, Math.min(1, t)));
    }

    g.strokeStyle = opts.color || "rgba(124,92,255,0.95)";
    g.lineWidth = 2;
    g.beginPath();
    for(let i=0;i<values.length;i++){
      const v = values[i];
      if (v==null) continue;
      const x = xAt(i);
      const y = yAt(v);
      if (i===0) g.moveTo(x,y); else g.lineTo(x,y);
    }
    g.stroke();

    g.fillStyle = "rgba(154,163,178,0.95)";
    g.font = "12px ui-sans-serif, system-ui";
    g.textAlign = "left"; g.textBaseline = "top";
    g.fillText(opts.title || "", 8, 8);
  }

  // ----- Metrics: conflict/escalation (optional) -----
  async function loadMetrics(){
    // If you kept the label-queue stats endpoints, you can re-add those charts here.
    // This file focuses on model promotion + hot-reload visibility.
    await loadHot();
  }

  // ----- Hot reload status -----
  async function loadHot(){
    try{
      const r = await api('/v1/admin/models/active');
      const j = await r.json();
      document.getElementById('hotNote').textContent = "Live inference model as seen by API workers (hot reload).";
      document.getElementById('hotOut').textContent = JSON.stringify(j, null, 2);
    }catch(e){
      document.getElementById('hotOut').textContent = String(e);
    }
  }

  // ----- Models list + promote + card -----
  async function loadModels(){
    try{
      const r = await api('/v1/admin/models/list?limit=100');
      const j = await r.json();
      const tb = document.querySelector('#modelsTable tbody');
      tb.innerHTML = '';

      document.getElementById('modelsNote').textContent =
        `Active: ${j.active_version || '—'} · total: ${(j.items||[]).length} · role: ${(me && me.role) || '—'}`;

      (j.items||[]).forEach(row=>{
        const tr = document.createElement('tr');
        const valLoss = (row.metrics && row.metrics.best_val_loss != null) ? row.metrics.best_val_loss : null;
        const canPromote = me && me.role === 'admin' && !row.is_active;

        tr.innerHTML = `
          <td>${row.is_active ? '✅' : ''}</td>
          <td><code>${row.version}</code></td>
          <td>${row.created_at}</td>
          <td>${valLoss==null ? '—' : Number(valLoss).toFixed(6)}</td>
          <td>
            <button onclick="viewCard(${row.id})">View card</button>
            ${canPromote ? `<button class="primary" onclick="promote(${row.id})">Promote</button>` : ''}
          </td>
        `;
        tb.appendChild(tr);
      });

      // auto-load top card
      if ((j.items||[]).length){
        viewCard(j.items[0].id);
      } else {
        document.getElementById('modelCard').textContent = 'No models registered yet.';
      }
    }catch(e){
      document.getElementById('modelsNote').textContent = String(e);
    }
  }

  async function viewCard(id){
    try{
      const r = await api(`/v1/admin/models/${id}/card`);
      const txt = await r.text();
      document.getElementById('modelCard').textContent = txt;
    }catch(e){
      document.getElementById('modelCard').textContent = `No card or error: ${String(e)}`;
    }
  }

  async function promote(id){
    try{
      await api(`/v1/admin/models/${id}/promote`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({reason:"admin_ui_promote"})
      });
      await loadSummary();
      await loadModels();
      await loadHot();
    }catch(e){
      alert(String(e));
    }
  }

  // Auto-login
  (async ()=>{
    try{
      const r = await api('/v1/admin/auth/me');
      const j = await r.json();
      if (j && j.ok){
        me = j; csrf = j.csrf_token;
        document.getElementById('who').textContent = `Signed in: ${j.email} (${j.role})`;
        document.getElementById('loginPanel').classList.add('hide');
        document.getElementById('dash').classList.remove('hide');
        document.getElementById('btnLogout').classList.remove('hide');
        await refreshAll();
      }
    }catch(e){}
  })();
</script>
</body>
</html>
"""

@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(_HTML)

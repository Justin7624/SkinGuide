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
    .rowline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .tabs{display:flex;gap:8px;flex-wrap:wrap}
    .tab{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:#0f1118;color:var(--muted);cursor:pointer}
    .tab.active{background:rgba(124,92,255,.18);border-color:rgba(124,92,255,.45);color:var(--ink)}
    pre{white-space:pre-wrap;word-break:break-word;background:#0f1118;border:1px solid rgba(255,255,255,.08);padding:10px;border-radius:12px;margin:0;max-height:420px;overflow:auto}
    table{width:100%;border-collapse:collapse}
    th,td{padding:8px;border-bottom:1px solid rgba(255,255,255,.08);font-size:12px}
    th{text-align:left;color:var(--muted);font-weight:800}
    code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
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
    <div class="card span4"><div class="k">Stable Model</div><div class="v" id="stableModel" style="font-size:18px">—</div></div>

    <!-- Deployment controls (visible "inside the labeling dashboard" context) -->
    <div class="card span12">
      <div class="rowline" style="justify-content:space-between;align-items:center;flex-wrap:wrap">
        <div>
          <div class="k">Model Deployment Controls</div>
          <div class="muted small">Canary rollout (% by session hash) + Promote/Commit + Rollback. Auto-rollback uses bias slice MAE.</div>
        </div>
        <div class="rowline">
          <button onclick="refreshAll()">Refresh</button>
        </div>
      </div>

      <div class="rowline" style="margin-top:10px">
        <div class="muted small">Canary model:</div>
        <select id="canarySelect" style="min-width:360px"></select>

        <div class="muted small">Canary %:</div>
        <input id="canaryPct" type="number" min="0" max="100" value="5" style="width:90px" />

        <button class="good" onclick="startCanary()">Start/Update Canary</button>
        <button class="primary" onclick="commitCanary()">Commit (Promote to Stable)</button>
        <button class="bad" onclick="rollbackCanary()">Rollback Canary</button>
      </div>

      <div class="rowline" style="margin-top:10px;justify-content:space-between;align-items:center;flex-wrap:wrap">
        <div class="muted small" id="deployNote">—</div>
        <div class="rowline">
          <button onclick="viewHot()">View ML hot-reload state</button>
        </div>
      </div>

      <pre id="deployOut" style="margin-top:10px">—</pre>
    </div>

    <div class="card span12">
      <div class="rowline" style="justify-content:space-between">
        <div class="tabs">
          <div class="tab active" id="tabModels" onclick="setTab('models')">Models</div>
          <div class="tab" id="tabHot" onclick="setTab('hot')">Hot Reload</div>
        </div>
      </div>
    </div>

    <!-- Models panel -->
    <div class="card span12" id="panelModels">
      <div class="rowline" style="justify-content:space-between;align-items:center;flex-wrap:wrap">
        <div>
          <div class="k">Model Artifacts</div>
          <div class="muted small">List all artifacts. “Promote” here instantly makes it the stable model and disables canary.</div>
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
              <th>Stable</th><th>Version</th><th>Created</th><th>Val loss</th><th>Actions</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>

      <div class="k" style="margin-top:14px">Model card</div>
      <pre id="modelCard" style="margin-top:8px">Select a model.</pre>
    </div>

    <!-- Hot panel -->
    <div class="card span12 hide" id="panelHot">
      <div class="k">ML Hot Reload State</div>
      <div class="muted small">What the API worker currently has loaded (stable + canary).</div>
      <pre id="hotOut" style="margin-top:10px">—</pre>
    </div>

  </div>
</div>

<script>
  let csrf = null;
  let me = null;
  let tab = "models";

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

  function setTab(next){
    tab = next;
    document.getElementById('tabModels').classList.toggle('active', tab==='models');
    document.getElementById('tabHot').classList.toggle('active', tab==='hot');
    document.getElementById('panelModels').classList.toggle('hide', tab!=='models');
    document.getElementById('panelHot').classList.toggle('hide', tab!=='hot');
    if (tab==='models') loadModels();
    if (tab==='hot') viewHot();
  }

  async function refreshAll(){
    await loadSummary();
    await loadModels();
    await loadDeployment();
  }

  async function loadSummary(){
    const r = await api('/v1/admin/summary');
    const j = await r.json();
    document.getElementById('sessions').textContent = j.total_sessions;
    document.getElementById('an24').textContent = j.total_analyzes_24h;
    document.getElementById('stableModel').textContent = j.active_model_version || '—';
  }

  async function loadModels(){
    try{
      const r = await api('/v1/admin/models/list?limit=200');
      const j = await r.json();

      // populate canary dropdown
      const sel = document.getElementById('canarySelect');
      sel.innerHTML = '';
      (j.items||[]).forEach(row=>{
        const opt = document.createElement('option');
        opt.value = row.id;
        opt.textContent = `${row.version}${row.is_active ? ' (stable)' : ''}`;
        sel.appendChild(opt);
      });

      const tb = document.querySelector('#modelsTable tbody');
      tb.innerHTML = '';

      document.getElementById('modelsNote').textContent =
        `Stable: ${j.active_version || '—'} · total artifacts: ${(j.items||[]).length} · role: ${(me && me.role) || '—'}`;

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
            ${canPromote ? `<button class="primary" onclick="promoteStable(${row.id})">Promote Stable</button>` : ''}
          </td>
        `;
        tb.appendChild(tr);
      });

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

  async function promoteStable(id){
    try{
      await api(`/v1/admin/models/${id}/promote`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({reason:"admin_ui_promote_stable"})
      });
      await refreshAll();
    }catch(e){
      alert(String(e));
    }
  }

  async function loadDeployment(){
    try{
      const r = await api('/v1/admin/models/deployment');
      const j = await r.json();
      document.getElementById('deployOut').textContent = JSON.stringify(j, null, 2);

      const dep = (j.deployment || {});
      const stable = (j.stable || {});
      const canary = (j.canary || {});

      let note = `Stable=${stable.version || '—'} · Canary=${canary.version || '—'} · Enabled=${dep.enabled} · %=${dep.canary_percent}`;
      if (dep.last_check && dep.last_check.ok === false) note += " · ⚠️ last_check failed";
      document.getElementById('deployNote').textContent = note;

      // try set dropdown to current canary
      if (dep.canary_model_id){
        document.getElementById('canarySelect').value = String(dep.canary_model_id);
      }
      if (dep.canary_percent != null){
        document.getElementById('canaryPct').value = String(dep.canary_percent);
      }
    }catch(e){
      document.getElementById('deployNote').textContent = String(e);
    }
  }

  async function startCanary(){
    if (!me || me.role !== 'admin'){
      alert('Admin role required.');
      return;
    }
    try{
      const canaryId = Number(document.getElementById('canarySelect').value);
      const pct = Number(document.getElementById('canaryPct').value);
      const r = await api('/v1/admin/models/deployment/set_canary', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          canary_model_id: canaryId,
          canary_percent: pct,
          enabled: true,
          auto_rollback_enabled: true,
          max_slice_mae_increase: 0.03,
          min_slice_n: 50,
          reason: "admin_ui_set_canary"
        })
      });
      const j = await r.json();
      await refreshAll();
      if (j.rolled_back) alert('Auto-rollback triggered due to bias slice MAE degradation. Canary disabled.');
    }catch(e){
      alert(String(e));
    }
  }

  async function commitCanary(){
    if (!me || me.role !== 'admin'){
      alert('Admin role required.');
      return;
    }
    try{
      const r = await api('/v1/admin/models/deployment/commit', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({reason:"admin_ui_commit_canary"})
      });
      const j = await r.json();
      await refreshAll();
      if (j.rolled_back) alert('Commit blocked: auto-rollback guardrail triggered.');
    }catch(e){
      alert(String(e));
    }
  }

  async function rollbackCanary(){
    if (!me || me.role !== 'admin'){
      alert('Admin role required.');
      return;
    }
    try{
      await api('/v1/admin/models/deployment/rollback', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({reason:"admin_ui_rollback"})
      });
      await refreshAll();
    }catch(e){
      alert(String(e));
    }
  }

  async function viewHot(){
    try{
      const r = await api('/v1/admin/models/active');
      const j = await r.json();
      document.getElementById('hotOut').textContent = JSON.stringify(j, null, 2);
      setTab('hot');
    }catch(e){
      document.getElementById('hotOut').textContent = String(e);
      setTab('hot');
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

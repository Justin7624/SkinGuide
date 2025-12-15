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
    :root { --bg:#0b0c10; --card:#12141c; --ink:#e8eaf0; --muted:#9aa3b2; --accent:#7c5cff; --ok:#25d0a6; --bad:#ff6b6b;}
    html,body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Inter,Arial;background:var(--bg);color:var(--ink);}
    .wrap{max-width:1150px;margin:0 auto;padding:20px;}
    .top{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
    .title{font-size:18px;font-weight:700}
    .row{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin-top:12px;}
    .card{background:var(--card);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px;box-shadow:0 12px 30px rgba(0,0,0,.25);}
    .k{color:var(--muted);font-size:12px}
    .v{font-size:22px;font-weight:800;margin-top:4px}
    input,button,select,textarea{background:#0f1118;color:var(--ink);border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:10px 12px}
    textarea{width:100%;min-height:70px}
    button{cursor:pointer}
    button.primary{background:var(--accent);border:none;font-weight:800}
    button.good{background:rgba(37,208,166,.2);border:1px solid rgba(37,208,166,.35)}
    button.bad{background:rgba(255,107,107,.15);border:1px solid rgba(255,107,107,.35)}
    .span4{grid-column:span 4}
    .span6{grid-column:span 6}
    .span12{grid-column:span 12}
    .muted{color:var(--muted)}
    table{width:100%;border-collapse:collapse}
    th,td{font-size:12px;text-align:left;padding:8px;border-bottom:1px solid rgba(255,255,255,.08);vertical-align:top}
    pre{white-space:pre-wrap;word-break:break-word;background:#0f1118;border:1px solid rgba(255,255,255,.08);padding:10px;border-radius:12px;margin:0}
    a{color:#b8a7ff}
    .small{font-size:12px}
    .hide{display:none}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    .imgbox{background:#0f1118;border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:10px}
    img{max-width:100%;border-radius:12px;display:block}
    .sliderrow{display:grid;grid-template-columns:240px 1fr 54px;gap:10px;align-items:center;margin-top:8px}
    .tag{display:inline-block;padding:4px 8px;border-radius:999px;background:rgba(124,92,255,.15);border:1px solid rgba(124,92,255,.35);font-size:12px}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">SkinGuide Admin</div>
      <div class="muted small" id="who">Not signed in</div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <button id="btnRefresh" class="hide" onclick="refreshAll()">Refresh</button>
      <button id="btnLogout" class="hide" onclick="logout()">Logout</button>
    </div>
  </div>

  <!-- Login -->
  <div class="row" id="loginPanel">
    <div class="card span12">
      <div class="k">Admin login</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px">
        <input id="email" placeholder="email" style="min-width:260px" />
        <input id="password" placeholder="password" type="password" style="min-width:260px" />
        <button class="primary" onclick="login()">Login</button>
      </div>
      <div class="muted small" style="margin-top:8px">
        First-time setup: call <code>/v1/admin/auth/bootstrap</code> with header <code>X-Bootstrap-Token</code>.
      </div>
      <div class="small" id="loginErr" style="margin-top:8px;color:var(--bad)"></div>
    </div>
  </div>

  <!-- Dashboard -->
  <div class="row hide" id="dash">
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
          <div class="muted small">Time series (last N days)</div>
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
        <div><span class="tag">analyzes</span> <span id="sparkA">—</span></div>
        <div style="margin-top:8px"><span class="tag">donations</span> <span id="sparkD">—</span></div>
        <div style="margin-top:8px"><span class="tag">labels</span> <span id="sparkL">—</span></div>
      </div>
    </div>

    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <div>
          <div class="k">Label queue</div>
          <div class="muted small">Review ROI-only samples and apply labels (role: labeler/admin)</div>
        </div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <button onclick="loadQueue()">Load queue</button>
          <span class="muted small" id="qStatus">—</span>
        </div>
      </div>

      <div id="queueWrap" style="margin-top:12px" class="grid2">
        <div class="imgbox">
          <div class="muted small" id="qMeta">—</div>
          <div style="margin-top:10px"><img id="qImg" /></div>
        </div>

        <div>
          <div class="muted small">Sample: <span id="qId">—</span> / sha: <span id="qSha">—</span></div>

          <div class="sliderrow">
            <div>uneven_tone_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_uneven"/>
            <div id="v_uneven">0</div>
          </div>
          <div class="sliderrow">
            <div>hyperpigmentation_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_hyper"/>
            <div id="v_hyper">0</div>
          </div>
          <div class="sliderrow">
            <div>redness_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_red"/>
            <div id="v_red">0</div>
          </div>
          <div class="sliderrow">
            <div>texture_roughness_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_text"/>
            <div id="v_text">0</div>
          </div>
          <div class="sliderrow">
            <div>shine_oiliness_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_shine"/>
            <div id="v_shine">0</div>
          </div>
          <div class="sliderrow">
            <div>pore_visibility_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_pore"/>
            <div id="v_pore">0</div>
          </div>
          <div class="sliderrow">
            <div>fine_lines_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_lines"/>
            <div id="v_lines">0</div>
          </div>
          <div class="sliderrow">
            <div>dryness_flaking_appearance</div>
            <input type="range" min="0" max="100" value="0" id="s_dry"/>
            <div id="v_dry">0</div>
          </div>

          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
            <select id="fitz">
              <option value="">Fitzpatrick (optional)</option>
              <option>I</option><option>II</option><option>III</option><option>IV</option><option>V</option><option>VI</option>
            </select>
            <select id="age">
              <option value="">Age band (optional)</option>
              <option>&lt;18</option><option>18-24</option><option>25-34</option><option>35-44</option><option>45-54</option><option>55-64</option><option>65+</option>
            </select>
          </div>

          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px">
            <button class="good" onclick="submitLabel()">Submit label</button>
            <button class="bad" onclick="skipLabel()">Skip</button>
          </div>

          <div class="small" id="qErr" style="margin-top:10px;color:var(--bad)"></div>
        </div>
      </div>
    </div>

    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <div>
          <div class="k">Audit (latest)</div>
          <div class="muted small">Use “Load more” to page backward.</div>
        </div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <button onclick="loadAudit(true)">Refresh audit</button>
          <button onclick="loadAudit(false)">Load more</button>
          <span class="muted small" id="auditStatus">—</span>
        </div>
      </div>
      <table style="margin-top:12px">
        <thead><tr><th>ID</th><th>Time</th><th>Type</th><th>Session</th><th>Payload</th></tr></thead>
        <tbody id="auditRows"></tbody>
      </table>
    </div>

    <div class="card span12">
      <div class="k">Exports (CSV)</div>
      <div class="muted small">Downloads use your admin cookie session.</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px" class="small">
        <a href="/v1/admin/export/audit.csv?since_days=7" target="_blank">audit.csv (7d)</a>
        <a href="/v1/admin/export/sessions.csv?since_days=30" target="_blank">sessions.csv (30d)</a>
        <a href="/v1/admin/export/consents.csv" target="_blank">consents.csv</a>
        <a href="/v1/admin/export/donations.csv?since_days=90" target="_blank">donations.csv (90d)</a>
        <a href="/v1/admin/export/labels.csv?since_days=365" target="_blank">labels.csv (365d)</a>
        <a href="/v1/admin/export/models.csv" target="_blank">models.csv</a>
      </div>
    </div>

  </div>
</div>

<script>
  let csrf = null;
  let auditBeforeId = null;
  let queue = [];
  let qIndex = 0;

  const sliders = [
    ["uneven_tone_appearance","s_uneven","v_uneven"],
    ["hyperpigmentation_appearance","s_hyper","v_hyper"],
    ["redness_appearance","s_red","v_red"],
    ["texture_roughness_appearance","s_text","v_text"],
    ["shine_oiliness_appearance","s_shine","v_shine"],
    ["pore_visibility_appearance","s_pore","v_pore"],
    ["fine_lines_appearance","s_lines","v_lines"],
    ["dryness_flaking_appearance","s_dry","v_dry"],
  ];

  for (const [k,sid,vid] of sliders){
    const s = document.getElementById(sid);
    const v = document.getElementById(vid);
    s.addEventListener('input', ()=> v.textContent = s.value);
    v.textContent = s.value;
  }

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
      await api('/v1/admin/auth/login', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({email,password})
      });
      await initAuthed();
    }catch(e){
      document.getElementById('loginErr').textContent = String(e);
    }
  }

  async function logout(){
    try{
      await api('/v1/admin/auth/logout', {method:'POST'});
    }catch(e){}
    csrf = null;
    document.getElementById('dash').classList.add('hide');
    document.getElementById('loginPanel').classList.remove('hide');
    document.getElementById('btnRefresh').classList.add('hide');
    document.getElementById('btnLogout').classList.add('hide');
    document.getElementById('who').textContent = 'Not signed in';
  }

  async function initAuthed(){
    const r = await api('/v1/admin/auth/me');
    const j = await r.json();
    csrf = j.csrf_token;
    document.getElementById('who').textContent = `Signed in: ${j.email} (${j.role})`;
    document.getElementById('loginPanel').classList.add('hide');
    document.getElementById('dash').classList.remove('hide');
    document.getElementById('btnRefresh').classList.remove('hide');
    document.getElementById('btnLogout').classList.remove('hide');
    await refreshAll();
  }

  async function refreshAll(){
    await loadSummary();
    await loadMetrics();
    await loadAudit(true);
    await loadQueue();
  }

  function spark(points){
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
  }

  async function loadMetrics(){
    const days = document.getElementById('days').value;
    const r = await api(`/v1/admin/metrics?days=${encodeURIComponent(days)}`);
    const j = await r.json();
    document.getElementById('range').textContent = `${j.start_date} → ${j.end_date}`;
    document.getElementById('sparkA').textContent = spark(j.analyzes);
    document.getElementById('sparkD').textContent = spark(j.donations_created);
    document.getElementById('sparkL').textContent = spark(j.labels_created);
  }

  async function loadAudit(reset){
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
  }

  function showQueueItem(){
    const err = document.getElementById('qErr');
    err.textContent = '';
    if (!queue.length){
      document.getElementById('qStatus').textContent = 'Queue empty';
      document.getElementById('qImg').src = '';
      document.getElementById('qId').textContent = '—';
      document.getElementById('qSha').textContent = '—';
      document.getElementById('qMeta').textContent = '—';
      return;
    }
    const it = queue[qIndex];
    document.getElementById('qStatus').textContent = `${qIndex+1}/${queue.length}`;
    document.getElementById('qId').textContent = it.id;
    document.getElementById('qSha').textContent = it.roi_sha256;
    document.getElementById('qImg').src = it.image_url;
    document.getElementById('qMeta').textContent = (it.metadata_json || '').slice(0,400);

    // reset sliders
    for (const [k,sid,vid] of sliders){
      document.getElementById(sid).value = 0;
      document.getElementById(vid).textContent = '0';
    }
    document.getElementById('fitz').value = '';
    document.getElementById('age').value = '';
  }

  async function loadQueue(){
    try{
      const r = await api('/v1/admin/label-queue/next?limit=20');
      const j = await r.json();
      queue = j.items || [];
      qIndex = 0;
      showQueueItem();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  async function submitLabel(){
    const err = document.getElementById('qErr');
    err.textContent = '';
    if (!queue.length) return;
    const it = queue[qIndex];

    const labels = {};
    for (const [k,sid,vid] of sliders){
      const val = parseInt(document.getElementById(sid).value, 10);
      if (val > 0) labels[k] = val / 100.0;
    }
    const fitz = document.getElementById('fitz').value || null;
    const age = document.getElementById('age').value || null;

    try{
      await api(`/v1/admin/label-queue/${it.id}/label`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({labels, fitzpatrick: fitz, age_band: age})
      });
      // advance
      queue.splice(qIndex,1);
      if (qIndex >= queue.length) qIndex = Math.max(0, queue.length-1);
      showQueueItem();
    }catch(e){
      err.textContent = String(e);
    }
  }

  async function skipLabel(){
    const err = document.getElementById('qErr');
    err.textContent = '';
    if (!queue.length) return;
    const it = queue[qIndex];
    try{
      await api(`/v1/admin/label-queue/${it.id}/skip`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({reason:"admin_skip"})
      });
      queue.splice(qIndex,1);
      if (qIndex >= queue.length) qIndex = Math.max(0, queue.length-1);
      showQueueItem();
    }catch(e){
      err.textContent = String(e);
    }
  }

  // Try to auto-detect existing session
  (async ()=>{
    try{
      const r = await api('/v1/admin/auth/me');
      const j = await r.json();
      if (j && j.ok){
        csrf = j.csrf_token;
        document.getElementById('who').textContent = `Signed in: ${j.email} (${j.role})`;
        document.getElementById('loginPanel').classList.add('hide');
        document.getElementById('dash').classList.remove('hide');
        document.getElementById('btnRefresh').classList.remove('hide');
        document.getElementById('btnLogout').classList.remove('hide');
        await refreshAll();
      }
    }catch(e){
      // not logged in
    }
  })();
</script>
</body>
</html>
"""

@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(_HTML)

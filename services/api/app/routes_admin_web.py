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
    textarea{width:100%;min-height:70px}
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
    canvas{position:absolute;left:0;top:0;pointer-events:none}
    .sliderrow{display:grid;grid-template-columns:260px 1fr 64px;gap:10px;align-items:center;margin-top:8px}
    .tag{display:inline-block;padding:4px 8px;border-radius:999px;background:rgba(124,92,255,.15);border:1px solid rgba(124,92,255,.35);font-size:12px}
    table{width:100%;border-collapse:collapse}
    th,td{font-size:12px;text-align:left;padding:8px;border-bottom:1px solid rgba(255,255,255,.08);vertical-align:top}
    pre{white-space:pre-wrap;word-break:break-word;background:#0f1118;border:1px solid rgba(255,255,255,.08);padding:10px;border-radius:12px;margin:0}
    .rowline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .hr{height:1px;background:rgba(255,255,255,.08);margin:10px 0}
    .ok{color:var(--ok)}
    .badc{color:var(--bad)}
    .kbd{font-family:ui-monospace,Menlo,Monaco,Consolas,monospace;border:1px solid rgba(255,255,255,.16);border-bottom-width:2px;border-radius:8px;padding:2px 6px;color:var(--muted);font-size:12px}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">SkinGuide Admin</div>
      <div class="muted small" id="who">Not signed in</div>
      <div class="muted small">Hotkeys: <span class="kbd">Enter</span> submit, <span class="kbd">X</span> skip, <span class="kbd">N</span> next, <span class="kbd">P</span> prev, <span class="kbd">1-8</span> focus slider, <span class="kbd">←/→</span> adjust, <span class="kbd">Z</span> focus zoom</div>
    </div>
    <div class="rowline">
      <button id="btnRefresh" class="hide" onclick="refreshAll()">Refresh</button>
      <button id="btnLogout" class="hide" onclick="logout()">Logout</button>
    </div>
  </div>

  <!-- Login + reset -->
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

      <div class="hr"></div>

      <div class="k">Password reset</div>
      <div class="rowline" style="margin-top:10px">
        <input id="resetEmail" placeholder="email" style="min-width:260px" />
        <button onclick="resetRequest()">Request reset</button>
        <span class="muted small" id="resetReqOut">—</span>
      </div>
      <div class="rowline" style="margin-top:10px">
        <input id="resetToken" placeholder="reset token" style="min-width:260px" />
        <input id="resetNewPw" placeholder="new password" type="password" style="min-width:260px" />
        <input id="resetTotp" placeholder="2FA code (if enabled)" style="min-width:200px" />
        <input id="resetRec" placeholder="Recovery code (optional)" style="min-width:240px" />
        <button class="good" onclick="resetConfirm()">Confirm reset</button>
      </div>
      <div class="small" id="resetErr" style="margin-top:8px;color:var(--bad)"></div>

      <div class="muted small" style="margin-top:10px">
        First-time setup: call <code>/v1/admin/auth/bootstrap</code> with header <code>X-Bootstrap-Token</code>.
      </div>
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

    <!-- 2FA panel -->
    <div class="card span12">
      <div class="k">Account security (2FA)</div>
      <div class="rowline" style="margin-top:10px">
        <span class="muted small">2FA status: <span id="twofaStatus">—</span></span>
        <button onclick="twofaStart()">Start 2FA</button>
        <input id="twofaCode" placeholder="Enter code from app" style="min-width:220px" />
        <button class="good" onclick="twofaConfirm()">Confirm</button>
        <input id="twofaDisablePw" placeholder="password to disable" type="password" style="min-width:220px" />
        <input id="twofaDisableCode" placeholder="code (or use recovery)" style="min-width:220px" />
        <input id="twofaDisableRec" placeholder="recovery code" style="min-width:220px" />
        <button class="bad" onclick="twofaDisable()">Disable</button>
      </div>
      <div class="rowline" style="margin-top:10px">
        <div class="imgbox" style="max-width:320px">
          <div class="muted small">QR (scan in authenticator)</div>
          <div style="margin-top:8px"><img id="twofaQr" style="width:100%;height:auto"/></div>
          <div class="muted small" style="margin-top:8px">Secret: <span id="twofaSecret">—</span></div>
        </div>
        <div style="flex:1">
          <div class="muted small">Recovery codes (shown once after confirm):</div>
          <pre id="recoveryOut">—</pre>
          <div class="small" id="twofaErr" style="margin-top:8px;color:var(--bad)"></div>
        </div>
      </div>
    </div>

    <!-- Metrics -->
    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <div>
          <div class="k">Metrics</div>
          <div class="muted small">Time series (last N days)</div>
        </div>
        <div class="rowline">
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

    <!-- Label queue -->
    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <div>
          <div class="k">Label queue</div>
          <div class="muted small">Per-region overlay from metadata_json.regions[] (bbox) if available.</div>
        </div>
        <div class="rowline">
          <button onclick="loadQueue()">Load queue</button>
          <button onclick="prevItem()">Prev</button>
          <button onclick="nextItem()">Next</button>
          <span class="muted small" id="qStatus">—</span>
          <span class="muted small">Zoom</span>
          <input id="zoom" type="range" min="50" max="220" value="100" />
          <span class="muted small" id="zoomVal">100%</span>
        </div>
      </div>

      <div id="queueWrap" style="margin-top:12px" class="grid2">
        <div class="imgbox">
          <div class="muted small" id="qMeta">—</div>
          <div class="stage" id="stage" style="margin-top:10px;max-height:520px">
            <img id="qImg" />
            <canvas id="qCanvas"></canvas>
          </div>
        </div>

        <div>
          <div class="muted small">Sample: <span id="qId">—</span> / sha: <span id="qSha">—</span></div>

          <div class="sliderrow"><div>1) uneven_tone_appearance</div><input type="range" min="0" max="100" value="0" id="s_uneven"/><div id="v_uneven">0</div></div>
          <div class="sliderrow"><div>2) hyperpigmentation_appearance</div><input type="range" min="0" max="100" value="0" id="s_hyper"/><div id="v_hyper">0</div></div>
          <div class="sliderrow"><div>3) redness_appearance</div><input type="range" min="0" max="100" value="0" id="s_red"/><div id="v_red">0</div></div>
          <div class="sliderrow"><div>4) texture_roughness_appearance</div><input type="range" min="0" max="100" value="0" id="s_text"/><div id="v_text">0</div></div>
          <div class="sliderrow"><div>5) shine_oiliness_appearance</div><input type="range" min="0" max="100" value="0" id="s_shine"/><div id="v_shine">0</div></div>
          <div class="sliderrow"><div>6) pore_visibility_appearance</div><input type="range" min="0" max="100" value="0" id="s_pore"/><div id="v_pore">0</div></div>
          <div class="sliderrow"><div>7) fine_lines_appearance</div><input type="range" min="0" max="100" value="0" id="s_lines"/><div id="v_lines">0</div></div>
          <div class="sliderrow"><div>8) dryness_flaking_appearance</div><input type="range" min="0" max="100" value="0" id="s_dry"/><div id="v_dry">0</div></div>

          <div class="rowline" style="margin-top:14px">
            <select id="fitz">
              <option value="">Fitzpatrick (optional)</option>
              <option>I</option><option>II</option><option>III</option><option>IV</option><option>V</option><option>VI</option>
            </select>
            <select id="age">
              <option value="">Age band (optional)</option>
              <option>&lt;18</option><option>18-24</option><option>25-34</option><option>35-44</option><option>45-54</option><option>55-64</option><option>65+</option>
            </select>
          </div>

          <div class="rowline" style="margin-top:12px">
            <button class="good" onclick="submitLabel()">Submit label</button>
            <button class="bad" onclick="skipLabel()">Skip</button>
          </div>

          <div class="small" id="qErr" style="margin-top:10px;color:var(--bad)"></div>
        </div>
      </div>
    </div>

    <!-- Audit -->
    <div class="card span12">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <div>
          <div class="k">Audit (latest)</div>
          <div class="muted small">Use “Load more” to page backward.</div>
        </div>
        <div class="rowline">
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
  </div>
</div>

<script>
  let csrf = null;
  let me = null;
  let auditBeforeId = null;

  let queue = [];
  let qIndex = 0;
  let focusedSlider = null;

  const canvas = document.getElementById('qCanvas');
  const ctx = canvas.getContext('2d');
  const img = document.getElementById('qImg');
  const stage = document.getElementById('stage');
  const zoom = document.getElementById('zoom');
  const zoomVal = document.getElementById('zoomVal');

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
    s.addEventListener('focus', ()=> focusedSlider = s);
    v.textContent = s.value;
  }

  zoom.addEventListener('input', ()=>{
    zoomVal.textContent = `${zoom.value}%`;
    applyZoom();
    redrawOverlay();
  });

  function applyZoom(){
    const z = parseInt(zoom.value, 10) / 100.0;
    img.style.transformOrigin = "0 0";
    canvas.style.transformOrigin = "0 0";
    img.style.transform = `scale(${z})`;
    canvas.style.transform = `scale(${z})`;
    // stage scrollbars handle overflow
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
    csrf = null;
    me = null;
    document.getElementById('dash').classList.add('hide');
    document.getElementById('loginPanel').classList.remove('hide');
    document.getElementById('btnRefresh').classList.add('hide');
    document.getElementById('btnLogout').classList.add('hide');
    document.getElementById('who').textContent = 'Not signed in';
  }

  async function initAuthed(){
    const r = await api('/v1/admin/auth/me');
    me = await r.json();
    csrf = me.csrf_token;
    document.getElementById('who').textContent = `Signed in: ${me.email} (${me.role})`;
    document.getElementById('twofaStatus').innerHTML = me.totp_enabled ? '<span class="ok">enabled</span>' : '<span class="badc">disabled</span>';

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

  // -------- Password reset (debug scaffold) --------

  async function resetRequest(){
    document.getElementById('resetErr').textContent = '';
    try{
      const email = document.getElementById('resetEmail').value.trim();
      const r = await api('/v1/admin/auth/password-reset/request', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({email})
      });
      const j = await r.json();
      document.getElementById('resetReqOut').textContent = j.token_debug ? `DEBUG token: ${j.token_debug}` : 'Requested (check email if configured)';
      if (j.token_debug) document.getElementById('resetToken').value = j.token_debug;
    }catch(e){
      document.getElementById('resetErr').textContent = String(e);
    }
  }

  async function resetConfirm(){
    document.getElementById('resetErr').textContent = '';
    try{
      const token = document.getElementById('resetToken').value.trim();
      const new_password = document.getElementById('resetNewPw').value;
      const totp_code = document.getElementById('resetTotp').value.trim() || null;
      const recovery_code = document.getElementById('resetRec').value.trim() || null;
      await api('/v1/admin/auth/password-reset/confirm', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({token, new_password, totp_code, recovery_code})
      });
      document.getElementById('resetErr').innerHTML = '<span class="ok">Password updated. You can log in now.</span>';
    }catch(e){
      document.getElementById('resetErr').textContent = String(e);
    }
  }

  // -------- 2FA --------

  async function twofaStart(){
    document.getElementById('twofaErr').textContent = '';
    try{
      const r = await api('/v1/admin/auth/2fa/start', {method:'POST'});
      const j = await r.json();
      document.getElementById('twofaSecret').textContent = j.secret || '—';
      // QR endpoint uses current secret
      document.getElementById('twofaQr').src = '/v1/admin/auth/2fa/qr';
      document.getElementById('recoveryOut').textContent = '—';
    }catch(e){
      document.getElementById('twofaErr').textContent = String(e);
    }
  }

  async function twofaConfirm(){
    document.getElementById('twofaErr').textContent = '';
    try{
      const code = document.getElementById('twofaCode').value.trim();
      const r = await api('/v1/admin/auth/2fa/confirm', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({code})
      });
      const j = await r.json();
      document.getElementById('recoveryOut').textContent = (j.recovery_codes || []).join('\n') || '—';
      await initAuthed();
    }catch(e){
      document.getElementById('twofaErr').textContent = String(e);
    }
  }

  async function twofaDisable(){
    document.getElementById('twofaErr').textContent = '';
    try{
      const password = document.getElementById('twofaDisablePw').value;
      const code = document.getElementById('twofaDisableCode').value.trim() || null;
      const recovery_code = document.getElementById('twofaDisableRec').value.trim() || null;
      await api('/v1/admin/auth/2fa/disable', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({password, code, recovery_code})
      });
      document.getElementById('twofaSecret').textContent = '—';
      document.getElementById('twofaQr').src = '';
      document.getElementById('recoveryOut').textContent = '—';
      await initAuthed();
    }catch(e){
      document.getElementById('twofaErr').textContent = String(e);
    }
  }

  // -------- Summary/Metrics/Audit --------

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

  // -------- Label queue + overlay --------

  function safeJsonParse(s){
    try{ return JSON.parse(s); }catch(e){ return null; }
  }

  function fitCanvasToImage(){
    // match canvas size to natural image size
    canvas.width = img.naturalWidth || 1;
    canvas.height = img.naturalHeight || 1;
    canvas.style.width = (img.naturalWidth || 1) + "px";
    canvas.style.height = (img.naturalHeight || 1) + "px";
    img.style.width = (img.naturalWidth || 1) + "px";
    img.style.height = (img.naturalHeight || 1) + "px";
  }

  function redrawOverlay(){
    ctx.clearRect(0,0,canvas.width,canvas.height);
    if (!queue.length) return;
    const it = queue[qIndex];
    const meta = safeJsonParse(it.metadata_json || '');
    if (!meta || !meta.regions || !Array.isArray(meta.regions)) return;

    // Simple overlay styling
    ctx.lineWidth = 3;
    ctx.font = "18px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto";
    ctx.textBaseline = "top";

    for (const r of meta.regions){
      const b = r.bbox || r.bounding_box || null;
      if (!b) continue;
      const x = b.x ?? b.left ?? 0;
      const y = b.y ?? b.top ?? 0;
      const w = b.w ?? b.width ?? 0;
      const h = b.h ?? b.height ?? 0;
      const name = (r.name || r.region || "region").toString();

      ctx.strokeStyle = "rgba(124,92,255,0.9)";
      ctx.fillStyle = "rgba(124,92,255,0.15)";
      ctx.fillRect(x,y,w,h);
      ctx.strokeRect(x,y,w,h);

      // label background
      const label = name;
      const pad = 6;
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(x, Math.max(0,y-26), tw+pad*2, 24);
      ctx.fillStyle = "rgba(255,255,255,0.95)";
      ctx.fillText(label, x+pad, Math.max(0,y-24));
    }
  }

  img.addEventListener('load', ()=>{
    fitCanvasToImage();
    applyZoom();
    redrawOverlay();
  });

  function resetSliders(){
    for (const [k,sid,vid] of sliders){
      document.getElementById(sid).value = 0;
      document.getElementById(vid).textContent = '0';
    }
    document.getElementById('fitz').value = '';
    document.getElementById('age').value = '';
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
      ctx.clearRect(0,0,canvas.width,canvas.height);
      return;
    }
    const it = queue[qIndex];
    document.getElementById('qStatus').textContent = `${qIndex+1}/${queue.length}`;
    document.getElementById('qId').textContent = it.id;
    document.getElementById('qSha').textContent = it.roi_sha256;

    // show compact metadata
    const meta = safeJsonParse(it.metadata_json || '');
    const metaTxt = meta ? JSON.stringify({
      model_version: meta.model_version,
      quality: meta.quality,
      regions: (meta.regions||[]).map(r=>({name:r.name, bbox:r.bbox})),
    }, null, 2) : (it.metadata_json || '');
    document.getElementById('qMeta').textContent = (metaTxt || '').slice(0,800);

    resetSliders();

    // load image (overlay draws on load)
    document.getElementById('qImg').src = it.image_url;
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

  function nextItem(){
    if (!queue.length) return;
    qIndex = Math.min(queue.length-1, qIndex+1);
    showQueueItem();
  }
  function prevItem(){
    if (!queue.length) return;
    qIndex = Math.max(0, qIndex-1);
    showQueueItem();
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

  // -------- Hotkeys --------
  function isTypingTarget(ev){
    const t = ev.target;
    if (!t) return false;
    const tag = (t.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select';
  }

  document.addEventListener('keydown', (ev)=>{
    if (isTypingTarget(ev)) return;
    if (document.getElementById('dash').classList.contains('hide')) return;

    const k = ev.key;

    if (k === 'Enter'){ ev.preventDefault(); submitLabel(); return; }
    if (k === 'x' || k === 'X'){ ev.preventDefault(); skipLabel(); return; }
    if (k === 'n' || k === 'N'){ ev.preventDefault(); nextItem(); return; }
    if (k === 'p' || k === 'P'){ ev.preventDefault(); prevItem(); return; }
    if (k === 'z' || k === 'Z'){ ev.preventDefault(); zoom.focus(); return; }

    // 1-8 focus sliders
    if (k >= '1' && k <= '8'){
      const idx = parseInt(k,10)-1;
      const sid = sliders[idx][1];
      const el = document.getElementById(sid);
      el.focus();
      focusedSlider = el;
      return;
    }

    // left/right adjust focused slider
    if (k === 'ArrowLeft' || k === 'ArrowRight'){
      if (!focusedSlider) return;
      ev.preventDefault();
      const step = ev.shiftKey ? 10 : 1;
      let v = parseInt(focusedSlider.value,10);
      v += (k === 'ArrowRight') ? step : -step;
      v = Math.max(0, Math.min(100, v));
      focusedSlider.value = v;
      // update its value label
      for (const [ak,sid,vid] of sliders){
        if (sid === focusedSlider.id){
          document.getElementById(vid).textContent = String(v);
          break;
        }
      }
    }
  });

  // -------- Auto-detect session --------
  (async ()=>{
    try{
      const r = await api('/v1/admin/auth/me');
      const j = await r.json();
      if (j && j.ok){
        me = j;
        csrf = j.csrf_token;
        document.getElementById('who').textContent = `Signed in: ${j.email} (${j.role})`;
        document.getElementById('twofaStatus').innerHTML = j.totp_enabled ? '<span class="ok">enabled</span>' : '<span class="badc">disabled</span>';

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

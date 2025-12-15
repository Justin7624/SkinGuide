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
    .rowline{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .tabs{display:flex;gap:8px;flex-wrap:wrap}
    .tab{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:#0f1118;color:var(--muted);cursor:pointer}
    .tab.active{background:rgba(124,92,255,.18);border-color:rgba(124,92,255,.45);color:var(--ink)}
    .badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid rgba(255,255,255,.12);font-size:12px;color:var(--muted)}
    .badc{color:var(--bad)}
    pre{white-space:pre-wrap;word-break:break-word;background:#0f1118;border:1px solid rgba(255,255,255,.08);padding:10px;border-radius:12px;margin:0;max-height:360px;overflow:auto}
    .drawer{position:fixed;right:16px;top:16px;bottom:16px;width:min(560px, calc(100vw - 32px));background:var(--card);
      border:1px solid rgba(255,255,255,.12);border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.45);padding:14px;overflow:auto}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">SkinGuide Admin</div>
      <div class="muted small" id="who">Not signed in</div>
      <div class="muted small">Hotkeys: Enter submit, X skip, N next, P prev, 1-8 focus slider, ←/→ adjust, Z focus zoom</div>
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
          <div class="tab active" id="tabQueue" onclick="setTab('queue')">Queue</div>
          <div class="tab" id="tabConf" onclick="setTab('conf')">Conflicts <span class="badge" id="confCount">—</span></div>
          <div class="tab" id="tabIrr" onclick="setTab('irr')">IRR stats</div>
        </div>
        <div class="rowline">
          <button onclick="refreshAll()">Refresh</button>
        </div>
      </div>
    </div>

    <!-- Main panel -->
    <div class="card span12" id="panelMain">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <div>
          <div class="k" id="panelTitle">Label queue</div>
          <div class="muted small" id="panelSubtitle">Normal queue excludes conflicts. Conflicts tab shows mixed/disagreement samples.</div>
        </div>
        <div class="rowline">
          <button onclick="loadQueue()">Load</button>
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
          <div class="muted small">
            Sample: <span id="qId">—</span> / sha: <span id="qSha">—</span> · submissions: <span id="qSubs">—</span>
            <span id="qConflict" class="badc" style="margin-left:10px"></span>
          </div>

          <div class="rowline" style="margin-top:10px">
            <select id="regionSel" style="min-width:260px"></select>
            <span class="muted small">Global + per-region</span>
          </div>

          <div class="sliderrow"><div>1) uneven_tone_appearance</div><input type="range" min="0" max="100" value="0" id="s_uneven"/><div id="v_uneven">0</div></div>
          <div class="sliderrow"><div>2) hyperpigmentation_appearance</div><input type="range" min="0" max="100" value="0" id="s_hyper"/><div id="v_hyper">0</div></div>
          <div class="sliderrow"><div>3) redness_appearance</div><input type="range" min="0" max="100" value="0" id="s_red"/><div id="v_red">0</div></div>
          <div class="sliderrow"><div>4) texture_roughness_appearance</div><input type="range" min="0" max="100" value="0" id="s_text"/><div id="v_text">0</div></div>
          <div class="sliderrow"><div>5) shine_oiliness_appearance</div><input type="range" min="0" max="100" value="0" id="s_shine"/><div id="v_shine">0</div></div>
          <div class="sliderrow"><div>6) pore_visibility_appearance</div><input type="range" min="0" max="100" value="0" id="s_pore"/><div id="v_pore">0</div></div>
          <div class="sliderrow"><div>7) fine_lines_appearance</div><input type="range" min="0" max="100" value="0" id="s_lines"/><div id="v_lines">0</div></div>
          <div class="sliderrow"><div>8) dryness_flaking_appearance</div><input type="range" min="0" max="100" value="0" id="s_dry"/><div id="v_dry">0</div></div>

          <div class="rowline" style="margin-top:12px">
            <button class="good" onclick="submitLabel()">Submit label</button>
            <button class="bad" onclick="skipLabel()">Skip</button>
            <button onclick="reviewConflict()">Review</button>
            <button class="bad hide" id="btnForce" onclick="forceFinalize()">Force finalize (admin)</button>
          </div>

          <div class="small" id="qErr" style="margin-top:10px;color:var(--bad)"></div>
        </div>
      </div>
    </div>

    <!-- IRR panel -->
    <div class="card span12 hide" id="panelIRR">
      <div class="rowline" style="justify-content:space-between">
        <div>
          <div class="k">Inter-rater reliability</div>
          <div class="muted small">Computed on latest 2 distinct non-skip submissions per sample in window.</div>
        </div>
        <div class="rowline">
          <select id="irrDays">
            <option value="7">7d</option>
            <option value="30" selected>30d</option>
            <option value="90">90d</option>
            <option value="365">365d</option>
          </select>
          <button onclick="loadIRR()">Load</button>
        </div>
      </div>
      <pre id="irrOut" style="margin-top:12px">—</pre>
    </div>
  </div>
</div>

<div class="drawer hide" id="drawer">
  <div class="rowline" style="justify-content:space-between;align-items:center">
    <div>
      <div style="font-weight:900">Conflict review</div>
      <div class="muted small" id="drawerSub">—</div>
    </div>
    <button onclick="closeDrawer()">Close</button>
  </div>
  <div style="margin-top:10px" class="muted small">Conflict detail</div>
  <pre id="drawerConflict">—</pre>
  <div style="margin-top:10px" class="muted small">Suggested final (if any)</div>
  <pre id="drawerSuggested">—</pre>
  <div style="margin-top:10px" class="muted small">Submissions</div>
  <pre id="drawerSubs">—</pre>
</div>

<script>
  let csrf = null;
  let me = null;

  let tab = "queue"; // queue|conf|irr

  let queue = [];
  let qIndex = 0;
  let focusedSlider = null;

  let labelState = { global:{}, regions:{} };

  const canvas = document.getElementById('qCanvas');
  const ctx = canvas.getContext('2d');
  const img = document.getElementById('qImg');
  const zoom = document.getElementById('zoom');
  const zoomVal = document.getElementById('zoomVal');
  const regionSel = document.getElementById('regionSel');

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

  function safeJsonParse(s){ try{ return JSON.parse(s); }catch(e){ return null; } }

  function currentRegionKey(){ return regionSel.value || "__global__"; }
  function getBucket(){
    const k = currentRegionKey();
    if (k === "__global__") return labelState.global;
    if (!labelState.regions[k]) labelState.regions[k] = {};
    return labelState.regions[k];
  }
  function setFromBucket(){
    const b = getBucket();
    for (const [k,sid,vid] of sliders){
      const v01 = (b[k] != null) ? b[k] : 0;
      const v = Math.round(v01 * 100);
      document.getElementById(sid).value = v;
      document.getElementById(vid).textContent = String(v);
    }
  }
  function writeToBucket(){
    const b = getBucket();
    for (const [k,sid,vid] of sliders){
      const v = parseInt(document.getElementById(sid).value,10);
      if (v <= 0) { delete b[k]; continue; }
      b[k] = v / 100.0;
    }
  }

  for (const [k,sid,vid] of sliders){
    const s = document.getElementById(sid);
    const v = document.getElementById(vid);
    s.addEventListener('input', ()=>{
      v.textContent = s.value;
      writeToBucket();
    });
    s.addEventListener('focus', ()=> focusedSlider = s);
    v.textContent = s.value;
  }

  regionSel.addEventListener('change', ()=>{
    setFromBucket();
    redrawOverlay();
  });

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
    await loadQueue();
    await loadConfCount();
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
    document.getElementById('tabQueue').classList.toggle('active', tab==='queue');
    document.getElementById('tabConf').classList.toggle('active', tab==='conf');
    document.getElementById('tabIrr').classList.toggle('active', tab==='irr');

    document.getElementById('panelMain').classList.toggle('hide', tab==='irr');
    document.getElementById('panelIRR').classList.toggle('hide', tab!=='irr');

    if (tab==='queue'){
      document.getElementById('panelTitle').textContent = 'Label queue';
      document.getElementById('panelSubtitle').textContent = 'Normal queue excludes conflicts.';
      loadQueue();
    } else if (tab==='conf'){
      document.getElementById('panelTitle').textContent = 'Conflicts queue';
      document.getElementById('panelSubtitle').textContent = 'Mixed skip/label or disagreement. Use Review + (admin) Force finalize.';
      loadConflicts();
    }
  }

  function fitCanvasToImage(){
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
    if (!meta || !Array.isArray(meta.regions)) return;

    const selected = currentRegionKey();

    ctx.lineWidth = 3;
    ctx.font = "18px ui-sans-serif, system-ui";
    ctx.textBaseline = "top";

    for (const r of meta.regions){
      const b = r.bbox || r.bounding_box || null;
      if (!b) continue;
      const x = b.x ?? 0;
      const y = b.y ?? 0;
      const w = b.w ?? 0;
      const h = b.h ?? 0;
      const name = (r.name || r.region || "region").toString();
      const isSel = (selected !== "__global__" && name === selected);

      ctx.strokeStyle = isSel ? "rgba(37,208,166,0.95)" : "rgba(124,92,255,0.85)";
      ctx.fillStyle = isSel ? "rgba(37,208,166,0.18)" : "rgba(124,92,255,0.12)";
      ctx.fillRect(x,y,w,h);
      ctx.strokeRect(x,y,w,h);
    }
  }

  img.addEventListener('load', ()=>{
    fitCanvasToImage();
    applyZoom();
    redrawOverlay();
  });

  function resetStateForSample(meta){
    labelState = { global:{}, regions:{} };

    regionSel.innerHTML = '';
    const optG = document.createElement('option');
    optG.value = "__global__";
    optG.textContent = "Global (whole face)";
    regionSel.appendChild(optG);

    if (meta && Array.isArray(meta.regions)){
      for (const r of meta.regions){
        const name = (r.name || r.region || "").toString();
        if (!name) continue;
        const o = document.createElement('option');
        o.value = name;
        o.textContent = `Region: ${name}`;
        regionSel.appendChild(o);
      }
    }
    regionSel.value = "__global__";
    setFromBucket();
  }

  function showQueueItem(){
    document.getElementById('qErr').textContent = '';
    document.getElementById('qConflict').textContent = '';
    document.getElementById('btnForce').classList.add('hide');

    if (!queue.length){
      document.getElementById('qStatus').textContent = 'Empty';
      img.src = '';
      document.getElementById('qId').textContent = '—';
      document.getElementById('qSha').textContent = '—';
      document.getElementById('qMeta').textContent = '—';
      document.getElementById('qSubs').textContent = '—';
      ctx.clearRect(0,0,canvas.width,canvas.height);
      return;
    }

    const it = queue[qIndex];
    document.getElementById('qStatus').textContent = `${qIndex+1}/${queue.length}`;
    document.getElementById('qId').textContent = it.id;
    document.getElementById('qSha').textContent = it.roi_sha256;
    document.getElementById('qSubs').textContent = String(it.label_submissions || 0);

    if (it.conflict){
      document.getElementById('qConflict').textContent = 'CONFLICT';
      if (me && me.role === 'admin') document.getElementById('btnForce').classList.remove('hide');
    }

    const meta = safeJsonParse(it.metadata_json || '');
    const metaTxt = meta ? JSON.stringify({regions:(meta.regions||[]).map(r=>({name:r.name, bbox:r.bbox}))}, null, 2) : (it.metadata_json || '');
    document.getElementById('qMeta').textContent = (metaTxt || '').slice(0,900);

    resetStateForSample(meta);
    img.src = it.image_url;
  }

  async function loadQueue(){
    try{
      const r = await api('/v1/admin/label-queue/next?limit=25');
      const j = await r.json();
      queue = j.items || [];
      qIndex = 0;
      showQueueItem();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  async function loadConflicts(){
    try{
      const r = await api('/v1/admin/label-queue/conflicts?limit=50');
      const j = await r.json();
      queue = j.items || [];
      qIndex = 0;
      showQueueItem();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  async function loadConfCount(){
    try{
      const r = await api('/v1/admin/label-queue/conflicts?limit=1');
      const j = await r.json();
      // backend doesn't return total, so we estimate by fetching 50 quickly:
      const r2 = await api('/v1/admin/label-queue/conflicts?limit=50');
      const j2 = await r2.json();
      document.getElementById('confCount').textContent = (j2.items||[]).length;
    }catch(e){
      document.getElementById('confCount').textContent = '—';
    }
  }

  function nextItem(){ if (!queue.length) return; qIndex = Math.min(queue.length-1, qIndex+1); showQueueItem(); }
  function prevItem(){ if (!queue.length) return; qIndex = Math.max(0, qIndex-1); showQueueItem(); }

  async function submitLabel(){
    document.getElementById('qErr').textContent = '';
    if (!queue.length) return;
    const it = queue[qIndex];
    writeToBucket();

    const labels = labelState.global || {};
    const region_labels = labelState.regions || {};

    try{
      await api(`/v1/admin/label-queue/${it.id}/label`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({labels, region_labels})
      });
      queue.splice(qIndex,1);
      if (qIndex >= queue.length) qIndex = Math.max(0, queue.length-1);
      showQueueItem();
      loadConfCount();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  async function skipLabel(){
    document.getElementById('qErr').textContent = '';
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
      loadConfCount();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  // -------- Conflict review drawer --------
  function openDrawer(){ document.getElementById('drawer').classList.remove('hide'); }
  function closeDrawer(){ document.getElementById('drawer').classList.add('hide'); }

  async function reviewConflict(){
    document.getElementById('qErr').textContent = '';
    if (!queue.length) return;
    const it = queue[qIndex];
    try{
      const r = await api(`/v1/admin/label-queue/${it.id}/review`);
      const j = await r.json();
      document.getElementById('drawerSub').textContent = `Sample ${j.donated_sample_id} · ${j.roi_sha256}`;
      document.getElementById('drawerConflict').textContent = JSON.stringify(j.conflict_detail || {}, null, 2);
      document.getElementById('drawerSuggested').textContent = JSON.stringify(j.suggested_final || null, null, 2);
      document.getElementById('drawerSubs').textContent = JSON.stringify(j.submissions || [], null, 2);
      openDrawer();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  async function forceFinalize(){
    document.getElementById('qErr').textContent = '';
    if (!queue.length) return;
    if (!me || me.role !== 'admin'){
      document.getElementById('qErr').textContent = 'Force finalize requires admin role.';
      return;
    }
    const it = queue[qIndex];
    writeToBucket();

    const final = {
      labels: labelState.global || {},
      region_labels: labelState.regions || {},
      note: "force-finalized from UI",
    };

    try{
      await api(`/v1/admin/label-queue/${it.id}/force-finalize`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({final})
      });
      queue.splice(qIndex,1);
      if (qIndex >= queue.length) qIndex = Math.max(0, queue.length-1);
      showQueueItem();
      closeDrawer();
      loadConfCount();
    }catch(e){
      document.getElementById('qErr').textContent = String(e);
    }
  }

  // -------- IRR --------
  async function loadIRR(){
    const days = document.getElementById('irrDays').value;
    const r = await api(`/v1/admin/label-queue/stats/irr?days=${encodeURIComponent(days)}`);
    const j = await r.json();
    document.getElementById('irrOut').textContent = JSON.stringify(j, null, 2);
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

    if (k >= '1' && k <= '8'){
      const idx = parseInt(k,10)-1;
      const sid = sliders[idx][1];
      const el = document.getElementById(sid);
      el.focus();
      focusedSlider = el;
      return;
    }

    if (k === 'ArrowLeft' || k === 'ArrowRight'){
      if (!focusedSlider) return;
      ev.preventDefault();
      const step = ev.shiftKey ? 10 : 1;
      let v = parseInt(focusedSlider.value,10);
      v += (k === 'ArrowRight') ? step : -step;
      v = Math.max(0, Math.min(100, v));
      focusedSlider.value = v;
      for (const [ak,sid,vid] of sliders){
        if (sid === focusedSlider.id){
          document.getElementById(vid).textContent = String(v);
          break;
        }
      }
      writeToBucket();
    }
  });

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

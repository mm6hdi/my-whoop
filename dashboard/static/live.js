/* WHOOP·LIVE — real-time metric view.
 * Reuses the dashboard's /ws stream (same packets as the hex inspector) but renders
 * the decoded METRICS instead of bytes: HR, live HRV (RMSSD from R-R), accelerometer,
 * gyroscope, the raw PPG waveform, battery, and wrist/contact events. A built-in DEMO
 * mode synthesizes the same signals so the view works (and can be reviewed) without a
 * band connected — toggle it with the button or ?demo=1.
 *
 * Metric extraction is defensive: it pulls heart_rate / rr_intervals / battery_pct from
 * the decoded `parsed` block, and looks up IMU/PPG arrays under several candidate key
 * names, so it keeps working regardless of the exact keys the schema decoder emits.
 */
const COL = {hr:'#ff5a6e', rr:'#ff9f43', accel:'#b6ff4d', gyro:'#c08bff',
             ppg:'#2ee6c6', phos:'#39ff9e', dim:'#6f8a86', grid:'#16242a'};
const $ = s => document.querySelector(s);

const N_SPARK = 120, N_CHART = 320, N_WAVE = 640, N_RR = 60;
const buf = {hr:[], hrv:[], rr:[], ax:[], ay:[], az:[], gx:[], gy:[], gz:[], ppg:[]};
const state = {connected:false, device:null, bonded:false, battery:null,
               charging:null, wrist:null, hr:null, hrv:null};
let pktTimes = [];
let demo = false, demoTimer = null, demoT = 0;

/* ---------- rolling buffers ---------- */
function push(arr, v, cap){ arr.push(v); while(arr.length > cap) arr.shift(); }
function pushAll(arr, v, cap){
  if(v == null) return;
  const a = Array.isArray(v) ? v : [v];
  for(const x of a){ if(typeof x === 'number' && isFinite(x)) push(arr, x, cap); }
}

/* ---------- ingest (shared by real packets + demo) ---------- */
function ingestHR(bpm){ if(!bpm) return; state.hr = bpm; push(buf.hr, bpm, N_SPARK); }
function ingestRR(list){
  if(!list || !list.length) return;
  for(const ms of list){ if(ms > 250 && ms < 2000) push(buf.rr, ms, N_RR); }
  const r = buf.rr;
  if(r.length < 5){ state.hrv = null; return; }
  let s = 0;
  for(let i = 1; i < r.length; i++){ const d = r[i] - r[i-1]; s += d*d; }
  state.hrv = Math.sqrt(s / (r.length - 1));   // RMSSD over the recent R-R window
  push(buf.hrv, state.hrv, N_SPARK);
}
function ingestIMU(ax, ay, az, gx, gy, gz){
  pushAll(buf.ax, ax, N_CHART); pushAll(buf.ay, ay, N_CHART); pushAll(buf.az, az, N_CHART);
  pushAll(buf.gx, gx, N_CHART); pushAll(buf.gy, gy, N_CHART); pushAll(buf.gz, gz, N_CHART);
}
function ingestPPG(v){ pushAll(buf.ppg, v, N_WAVE); }
function setBattery(pct, charging){ if(pct != null) state.battery = pct; if(charging != null) state.charging = charging; }
function setWrist(on){ state.wrist = on; }

/* ---------- packet → metrics ---------- */
function firstKey(obj, keys){ for(const k of keys) if(k in obj && obj[k] != null) return obj[k]; return null; }

function onPacket(p){
  pktTimes.push(performance.now()); if(pktTimes.length > 300) pktTimes.shift();
  const v = p.parsed || {};
  if('heart_rate' in v) ingestHR(v.heart_rate);
  if(v.rr_intervals) ingestRR(v.rr_intervals);
  if(v.battery_pct != null) setBattery(v.battery_pct, null);

  const ax = firstKey(v, ['accelX','accel_x','ax']), ay = firstKey(v, ['accelY','accel_y','ay']),
        az = firstKey(v, ['accelZ','accel_z','az']);
  const gx = firstKey(v, ['gyroX','gyro_x','gx']), gy = firstKey(v, ['gyroY','gyro_y','gy']),
        gz = firstKey(v, ['gyroZ','gyro_z','gz']);
  if(ax != null || gx != null) ingestIMU(ax, ay, az, gx, gy, gz);

  const ppg = firstKey(v, ['ppg','ppg_green','ppg_samples','optical','ppg_waveform']);
  if(ppg != null) ingestPPG(ppg);

  if(p.type_name === 'EVENT'){
    const ev = (p.fields || []).find(f => f.name === 'event');
    if(ev){
      const s = String(ev.value);
      logEvent(s);
      if(s.includes('WRIST_ON')) setWrist(true);
      else if(s.includes('WRIST_OFF')) setWrist(false);
      else if(s.includes('CHARGING_ON')) setBattery(null, true);
      else if(s.includes('CHARGING_OFF')) setBattery(null, false);
    }
  }
}

/* ---------- WebSocket (shared with the inspector) ---------- */
function connect(){
  if(location.protocol === 'file:') return;          // demo-only when opened as a file
  let ws;
  try { ws = new WebSocket(`ws://${location.host}/ws`); }
  catch(e){ return; }
  ws.onopen = () => logEvent('socket open');
  ws.onclose = () => { if(!demo) state.connected = false; };  // no auto-reload; demo keeps the view alive
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if(m.kind === 'hello' || m.kind === 'state'){ if(m.state) applyState(m.state); }
    else if(m.kind === 'packet'){ if(!demo) onPacket(m.packet); if(m.state) applyState(m.state); }
  };
  window._ws = ws;
}
function applyState(s){
  if(demo) return;
  state.connected = !!s.connected; state.device = s.device; state.bonded = !!s.bonded;
  if(s.battery != null) state.battery = s.battery;
}
function send(o){ const ws = window._ws; if(ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }

/* ---------- demo data ---------- */
function startDemo(){
  demo = true; state.connected = true; state.device = 'WHOOP (demo)'; state.bonded = true;
  setBattery(64, false); setWrist(true);
  $('#demo-btn').classList.add('on');
  demoTimer = setInterval(() => {
    demoT += 0.05; const t = demoT;
    const hr = Math.round(58 + 6*Math.sin(t/7) + (Math.random()*2 - 1));
    ingestHR(hr);
    ingestRR([Math.round(60000/hr + (Math.random()*44 - 22))]);
    const ax=[], ay=[], az=[], gx=[], gy=[], gz=[], ppg=[];
    const f = hr/60;                                  // beats per second
    for(let i = 0; i < 6; i++){
      const tt = t + i*0.008;
      az.push(1 + 0.03*Math.sin(tt*3) + (Math.random()*0.02 - 0.01));
      ax.push(0.04*Math.sin(tt*2) + (Math.random()*0.02 - 0.01));
      ay.push(0.04*Math.cos(tt*2.3) + (Math.random()*0.02 - 0.01));
      gx.push(Math.random()*6 - 3); gy.push(Math.random()*6 - 3); gz.push(Math.random()*6 - 3);
      ppg.push(Math.sin(2*Math.PI*f*tt) + 0.3*Math.sin(4*Math.PI*f*tt) + (Math.random()*0.06 - 0.03));
    }
    ingestIMU(ax, ay, az, gx, gy, gz); ingestPPG(ppg);
    if(state.battery > 20 && Math.random() < 0.03) state.battery = +(state.battery - 0.1).toFixed(1);
    if(Math.random() < 0.012) logEvent(Math.random() < 0.5 ? 'DOUBLE_TAP' : 'BLE_REALTIME_HR_ON');
  }, 50);
}
function stopDemo(){
  demo = false; clearInterval(demoTimer); demoTimer = null;
  state.connected = !!(window._ws && window._ws.readyState === 1);
  state.device = null;
  $('#demo-btn').classList.remove('on');
}

/* ---------- canvas helpers ---------- */
function fit(c){ const w = c.clientWidth || 300, h = c.clientHeight || 80; c.width = w; c.height = h; return c.getContext('2d'); }
function placeholder(ctx, W, H, msg){
  ctx.fillStyle = COL.dim; ctx.font = '11px IBM Plex Mono';
  ctx.textAlign = 'center'; ctx.fillText(msg, W/2, H/2); ctx.textAlign = 'left';
}
function sparkline(c, arr, col){
  const ctx = fit(c), W = c.width, H = c.height; ctx.clearRect(0, 0, W, H);
  if(arr.length < 2) return;
  const mn = Math.min(...arr), mx = Math.max(...arr), span = (mx - mn) || 1;
  ctx.beginPath();
  arr.forEach((v, i) => { const x = i/(arr.length-1)*W, y = H - (v-mn)/span*(H-4) - 2; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.shadowColor = col; ctx.shadowBlur = 6; ctx.stroke();
}
function grid(ctx, W, H){
  ctx.strokeStyle = COL.grid; ctx.lineWidth = 1;
  for(let i = 1; i < 4; i++){ const y = H*i/4; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
}
function multiline(c, series){
  const ctx = fit(c), W = c.width, H = c.height; ctx.clearRect(0, 0, W, H);
  let mn = Infinity, mx = -Infinity, maxlen = 0;
  for(const [arr] of series){ maxlen = Math.max(maxlen, arr.length); for(const v of arr){ if(v < mn) mn = v; if(v > mx) mx = v; } }
  if(!isFinite(mn) || maxlen < 2){ placeholder(ctx, W, H, 'waiting for raw stream…'); return; }
  if(mx - mn < 1e-6){ mx += 1; mn -= 1; }
  const span = mx - mn;
  grid(ctx, W, H);
  for(const [arr, col] of series){
    if(arr.length < 2) continue;
    ctx.beginPath();
    arr.forEach((v, i) => { const x = i/(maxlen-1)*W, y = H - (v-mn)/span*(H-6) - 3; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = col; ctx.lineWidth = 1.3; ctx.stroke();
  }
  ctx.fillStyle = COL.dim; ctx.font = '9px IBM Plex Mono';
  ctx.fillText(mx.toFixed(2), 4, 11); ctx.fillText(mn.toFixed(2), 4, H - 4);
}
function waveform(c, arr, col){
  const ctx = fit(c), W = c.width, H = c.height; ctx.clearRect(0, 0, W, H);
  if(arr.length < 2){ placeholder(ctx, W, H, 'waiting for PPG…'); return; }
  const mn = Math.min(...arr), mx = Math.max(...arr), span = (mx - mn) || 1;
  grid(ctx, W, H);
  ctx.beginPath();
  arr.forEach((v, i) => { const x = i/(arr.length-1)*W, y = H - (v-mn)/span*(H-8) - 4; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = col; ctx.lineWidth = 1.4; ctx.shadowColor = col; ctx.shadowBlur = 7; ctx.stroke();
}

/* ---------- event log ---------- */
function logEvent(msg){
  const l = $('#evlog'); if(!l) return;
  const d = document.createElement('div'); d.className = 'lrow';
  const t = new Date().toLocaleTimeString('en', {hour12:false});
  d.innerHTML = `<span class="lt">${t}</span><span class="linfo">${msg}</span>`;
  l.prepend(d); while(l.children.length > 60) l.lastChild.remove();
}

/* ---------- render loop ---------- */
function draw(){
  $('#m-hr').textContent  = state.hr  != null ? state.hr : '—';
  $('#m-hrv').textContent = state.hrv != null ? Math.round(state.hrv) : '—';
  $('#m-batt').textContent = state.battery != null ? state.battery + '%' : '—';
  $('#batt-fill').style.width = state.battery != null ? Math.max(3, state.battery) + '%' : '0';
  $('#m-charge').textContent = state.charging ? '⚡ charging' : '';
  const w = $('#m-wrist');
  w.textContent = state.wrist == null ? '—' : (state.wrist ? 'on-wrist' : 'off-wrist');
  w.className = 'tval ' + (state.wrist ? 'good' : (state.wrist === false ? 'warn' : ''));

  const conn = $('#st-conn');
  conn.innerHTML = `<i class="dot ${state.connected ? 'live' : ''}"></i> ${state.connected ? (demo ? 'DEMO' : 'LIVE') : 'down'}`;
  $('#st-dev').textContent  = state.device || '—';
  $('#st-bond').textContent = state.bonded ? 'bonded ✓' : '—';
  const now = performance.now();
  $('#st-rate').textContent = pktTimes.filter(t => now - t < 1000).length + ' pkt/s';

  sparkline($('#spark-hr'),  buf.hr,  COL.hr);
  sparkline($('#spark-hrv'), buf.hrv, COL.rr);
  multiline($('#chart-accel'), [[buf.ax, COL.accel], [buf.ay, '#7fe34a'], [buf.az, '#e6ff9c']]);
  multiline($('#chart-gyro'),  [[buf.gx, COL.gyro],  [buf.gy, '#9a6cff'], [buf.gz, '#d9c2ff']]);
  waveform($('#chart-ppg'), buf.ppg, COL.ppg);
}

/* ---------- wire up ---------- */
document.querySelectorAll('.deck .btn[data-act]').forEach(b => b.onclick = () => send({action: b.dataset.act}));
$('#demo-btn').onclick = () => demo ? stopDemo() : startDemo();

connect();
if(new URLSearchParams(location.search).has('demo')) startDemo();
setInterval(draw, 33);
draw();

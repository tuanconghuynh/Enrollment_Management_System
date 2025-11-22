  /* ===== helpers ===== */
  const $ = (id) => document.getElementById(id);
  const debounce = (fn, ms=400) => { let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; };
  const STORAGE_KEY="apiBase"; let API_PREFIX = "";

  function showToast(msg, type='info', ms=2500){
    const escapeHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    const wrap = $('toast-wrap'); if (!wrap) return;
    const existing = wrap.querySelectorAll('.toast'); if (existing.length >= 3) existing[0].remove();
    const el = document.createElement('div'); el.className = `toast ${type}`; el.setAttribute('role','status'); el.innerHTML = escapeHtml(msg);
    wrap.appendChild(el); requestAnimationFrame(()=> el.classList.add('show'));
    const t = setTimeout(()=>dismiss(), ms);
    function dismiss(){ el.classList.remove('show'); el.addEventListener('transitionend', ()=> el.remove(), {once:true}); }
    el.onclick = ()=>{ clearTimeout(t); dismiss(); };
  }

  const ymdKeep = (s)=> (s||"").slice(0,10);
  function fmtDateToInput(s){
    if(!s) return "";
    const m = String(s).match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
    if (m) return `${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`;
    const d = new Date(s); return Number.isNaN(d.getTime()) ? String(s).slice(0,10) : d.toISOString().slice(0,10);
  }

  function apiBase(){ return ($("apiBase").value || localStorage.getItem(STORAGE_KEY) || window.location.origin).trim().replace(/\/+$/,''); }
  async function pingPrefix(base){
    try{let r=await fetch(base+"/health",{credentials:"include"}); if(r.ok) return "";}catch(_){}
    try{let r2=await fetch(base+"/api/health",{credentials:"include"}); if(r2.ok) return "/api";}catch(_){}
    return null;
  }
  const makeUrl = (path)=> apiBase() + (API_PREFIX || "") + path;
  async function apiFetch(path, init={}){ const opts={credentials:"include", ...init}; return await fetch(makeUrl(path), opts).catch(()=>null); }
  async function journalTrack(payload){
    try{
      await apiFetch('/journal/track', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload || {})
      });
    }catch(_){}
  }

  function handleAuth(r){
    if(r && (r.status===401||r.status===403)){
      showToast("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.","warn",2500);
      const next = encodeURIComponent(location.pathname + location.search);
      setTimeout(()=>location.href="/auth_login.html?next="+next,700);
      return true;
    }
    return false;
  }
  const safeJson = async (r)=>{ try{ return await r.json(); }catch{ return {}; } };

  async function ensureApiBaseAndPrefix(){
    let base = localStorage.getItem(STORAGE_KEY) || window.location.origin;
    $("apiBase").value = base;
    let pref = await pingPrefix(base);
    if (pref === null){
      const guesses=[base, window.location.origin, "http://127.0.0.1:8000", "http://localhost:8000"];
      for (const g of guesses){
        const p = await pingPrefix(g);
        if (p !== null){
          $("apiBase").value=g;
          localStorage.setItem(STORAGE_KEY,g);
          API_PREFIX=p;
          return;
        }
      }
      for(;;){
        const m = prompt("Không kết nối được API.\nNhập IP/URL server (vd: http://192.168.2.82:8000):", base);
        if(!m) break;
        const p=await pingPrefix(m.trim());
        if(p!==null){
          $("apiBase").value=m.trim();
          localStorage.setItem(STORAGE_KEY,m.trim());
          API_PREFIX=p;
          return;
        }
        base=m.trim();
      }
      API_PREFIX="";
    } else {
      API_PREFIX=pref;
    }
  }

  /* ===== Name helpers ===== */
  function normSpace(s){ return String(s||'').replace(/\s+/g,' ').trim(); }
  function titleCaseVN(s){
    return normSpace(s).split(' ').map(w=>{ if(!w) return ''; const [h,...r]=w; return (h||'').toUpperCase()+r.join('').toLowerCase(); }).join(' ');
  }
  function joinFullName(ho_dem, ten){ const hd = normSpace(ho_dem), t = normSpace(ten); return normSpace([hd, t].filter(Boolean).join(' ')); }
  function splitVietnameseName(full){
    const display = titleCaseVN(full||'');
    const toks = display.split(' ').filter(Boolean);
    if (toks.length <= 1) return { ho_dem:'', ten: display };
    return { ho_dem: toks.slice(0, -1).join(' '), ten: toks[toks.length-1] };
  }
  function vnNorm(s){ return (s||"").normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').trim().toLowerCase(); }
  function matchScore(name, query){
    const a=vnNorm(name), b=vnNorm(query); if(!a||!b) return 0;
    if (a===b) return 100; if (a.startsWith(b)) return 90; if (a.includes(b)) return 70;
    const toks=b.split(/\s+/).filter(Boolean); return toks.every(t=>a.includes(t)) ? 60 : 0;
  }

  /* ========== User dropdown + logout modal ========== */
  (function menuSetup(){
    const btn = document.getElementById('userMenuBtn');
    const menu = document.getElementById('userMenu');
    if(!btn || !menu) return;
    function openMenu(on){
      menu.classList.toggle('show', on);
      btn.setAttribute('aria-expanded', String(on));
    }
    btn.addEventListener('click', (e)=>{
      e.stopPropagation();
      openMenu(!menu.classList.contains('show'));
    });
    document.addEventListener('click', ()=> menu.classList.contains('show') && openMenu(false));
    document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') openMenu(false); });
    document.getElementById('btnMenuLogout')?.addEventListener('click', ()=>{
      openMenu(false);
      if (typeof window.openLogout === 'function') window.openLogout();
    });
  })();

  (function(){
    const wrap = document.getElementById('logoutModal');
    const box  = document.getElementById('logoutBox');
    const ok   = document.getElementById('lgOK');
    const cxl  = document.getElementById('lgCancel');
    const x    = document.getElementById('lgClose');
    let last=null;

    function trapFocus(container, e){
      if(e.key!=='Tab') return;
      const f = container.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
      if(!f.length) return;
      const first=f[0], lastEl=f[f.length-1];
      if(e.shiftKey && document.activeElement===first){ e.preventDefault(); lastEl.focus(); }
      else if(!e.shiftKey && document.activeElement===lastEl){ e.preventDefault(); first.focus(); }
    }

    function open(){
      last=document.activeElement;
      wrap.classList.add('show');
      requestAnimationFrame(()=>box.focus());
      document.body.classList.add('overflow-hidden');
    }
    function close(){
      wrap.classList.remove('show');
      document.body.classList.remove('overflow-hidden');
      last?.focus?.();
    }
    window.openLogout = open;

    ok.addEventListener('click', async ()=>{
      try{ await apiFetch('/logout',{method:'POST'});}catch(_){}
      location.href='/auth_login.html';
    });
    cxl.addEventListener('click', close);
    x.addEventListener('click', close);
    wrap.addEventListener('click', e=>{ if(e.target===wrap) close(); });
    box.addEventListener('keydown', (e)=> trapFocus(box,e));

    // nút navLogout "cũ" (bị ẩn) vẫn mở modal
    $('navLogout')?.addEventListener('click', (e)=>{ e.preventDefault(); open(); });
  })();

  /* ===== Auth UI (/me) ===== */
  async function refreshAuthUI(){
    try{
      const r = await apiFetch('/me', { credentials:'include', cache:'no-store' });
      if (!r || !r.ok){
        $('navHello')?.classList.add("hidden");
        const rec = $('nguoi_nhan_ky_ten'); if (rec) rec.value = "";
        return;
      }
      const me = await r.json();

      const role = me.role || (Array.isArray(me.roles) ? me.roles[0] : "") || "";
      const displayName = me.full_name || me.display_name || me.name || me.username || "Người dùng";

      const navHello = $('navHello');
      if (navHello){
        navHello.textContent = `Xin chào, ${displayName}${role ? ' ('+role+')' : ''}`;
        navHello.classList.remove("hidden");
      }

      // sidebar
      const hName = document.getElementById('helloName');
      const hRole = document.getElementById('helloRole');
      if (hName) hName.textContent = displayName;
      if (hRole) hRole.textContent = role || 'User';

      const rec = $('nguoi_nhan_ky_ten');
      if (rec && !rec.value) {
        rec.value = displayName;
        rec.title = `Tự động theo tài khoản: ${displayName}`;
      }

      if (me.checklist || me.settings?.checklist) {
        window.__CHECKLIST_FROM_ME__ = me.checklist || me.settings.checklist;
      }
      if (me.checklist_version_name || me.settings?.checklist_version_name) {
        window.__CHECKLIST_VERSION_NAME__ = me.checklist_version_name || me.settings.checklist_version_name;
      }
    }catch(_){
      $('navHello')?.classList.add("hidden");
    }
  }

  /* ===== Checklist ===== */
  const DEFAULT_QTY = {
    bang_tot_nghiep_dai_hoc:2,
    bang_diem_dai_hoc:2,
    bang_tot_nghiep_cao_dang:2,
    bang_diem_cao_dang:2,
    bang_tot_nghiep_trung_cap:2,
    bang_diem_trung_cap:2,
    anh_3x4:2
  };
  const getDefaultQty = (code) => DEFAULT_QTY[code] ?? 1;

  function renderChecklistFromData(data) {
    if (!data) return;
    window.__CHECKLIST_VERSION_NAME__ = data?.version_name || data?.version || data?.name || window.__CHECKLIST_VERSION_NAME__ || 'v1';
    const body = $("docsBody"); body.innerHTML = "";
    (data.items||[])
      .sort((a,b)=> (a.order_index ?? a.order_no ?? 0) - (b.order_index ?? b.order_no ?? 0))
      .forEach((it, idx) => {
        const def = getDefaultQty(it.code);
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="p-2 border text-center">${idx+1}</td>
          <td class="p-2 border"><div class="font-medium">${it.display_name}</div></td>
          <td class="p-2 border text-center"><input type="checkbox" class="w-5 h-5 has-doc" data-code="${it.code}"></td>
          <td class="p-2 border text-center"><input type="number" min="0" class="input w-24 text-center qty bg-gray-100 text-gray-400" data-code="${it.code}" value="" placeholder="${def}" disabled /></td>`;
        body.appendChild(tr);
      });
    document.querySelectorAll('.has-doc').forEach((chk) => {
      const code = chk.dataset.code; const qty = document.querySelector(`.qty[data-code="${code}"]`); const def = getDefaultQty(code);
      chk.addEventListener("change", () => {
        if (chk.checked) { qty.value = String(def); qty.disabled=false; qty.classList.remove("bg-gray-100","text-gray-400"); }
        else { qty.value=""; qty.disabled=true; qty.classList.add("bg-gray-100","text-gray-400"); }
      });
    });
  }

  async function loadChecklist() {
    try {
      const r = await apiFetch("/checklist/active");
      if (r && r.ok) {
        const data = await r.json();
        renderChecklistFromData(data);
        return;
      }
    } catch (_) {}
    if (window.__CHECKLIST_FROM_ME__) {
      renderChecklistFromData(window.__CHECKLIST_FROM_ME__);
      showToast("Dùng checklist từ /me (fallback).", "warn");
      return;
    }
    showToast("Không lấy được checklist", "error");
  }

  function collectDocs() {
    const rows = Array.from(document.querySelectorAll('#docsBody tr'));
    return rows.map(tr => {
      const chk  = tr.querySelector('.has-doc');
      const qtyI = tr.querySelector('.qty');
      const code = chk?.dataset.code || '';
      const def  = getDefaultQty(code);
      let val = chk?.checked ? Number(qtyI.value || def) : 0;
      if (!Number.isFinite(val) || val < 0) val = 0;
      return { code, so_luong: val };
    });
  }

  /* ===== Deleted flags helper (từ server) ===== */
  function isSoftDeleted(x) {
    if (!x) return false;
    const status = String(x.status ?? x.trang_thai ?? x.trangthai ?? '').toUpperCase().trim();
    const state  = String(x.state ?? '').toUpperCase().trim();
    const dts = x.deleted_at || x.deletedAt || x.removed_at || x.archived_at;
    const boolTrue = (v) => String(v).toLowerCase() === 'true' || v === true || v === 1 || v === '1';
    const flags =
      boolTrue(x.deleted) ||
      boolTrue(x.is_deleted) ||
      boolTrue(x.isDeleted) ||
      boolTrue(x.hard_deleted) ||
      !String(x.active ?? x.is_active ?? true).match(/^(true|1)$/i) ||
      ['DELETED','DELETE_SOFT','DELETED_SOFT','REMOVED','INACTIVE','ARCHIVED'].includes(status) ||
      ['DELETED','REMOVED','ARCHIVED','INACTIVE'].includes(state);
    return Boolean(dts || flags);
  }

  /* ===== NAV/Auth gate ===== */
  (async () => {
    await ensureApiBaseAndPrefix();
    const r = await apiFetch("/me", { credentials: "include", cache: "no-store" });
    if (!r || !r.ok) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.replace(`/auth_login.html?next=${next}`);
      return;
    }
    try { localStorage.setItem("apiBase", apiBase()); } catch {}
    document.documentElement.style.visibility = '';
  })();

  /* ===== Bind name inputs ===== */
  function bindNameInputs(){
    const elHD = $('ho_dem'), elT = $('ten'), elFull = $('ho_ten');
    const mir  = $('fullNameMirror');
    if(!elHD || !elT || !elFull) return;

    const normalizeNow = ()=>{
      elHD.value = titleCaseVN(elHD.value);
      elT.value  = titleCaseVN(elT.value);
      const full = joinFullName(elHD.value, elT.value);
      elFull.value = full;
      if (mir) mir.textContent = full;
    };

    const liveMirror = ()=>{
      const full = [elHD.value, elT.value].filter(Boolean).join(' ');
      elFull.value = full;
      if (mir) mir.textContent = full;
    };

    elHD.addEventListener('input', liveMirror);
    elT .addEventListener('input', liveMirror);

    ['blur','change'].forEach(ev=>{
      elHD.addEventListener(ev, normalizeNow);
      elT .addEventListener(ev, normalizeNow);
    });

    liveMirror();
  }
  bindNameInputs();

  // ===== Mã HS theo Nhóm (Khóa, Đợt) =====
  function composeMaHoSoByGroup(khoa, dot, seq) { return `HS-${String(khoa).trim()}-${String(dot).trim()}-${String(seq).padStart(4,'0')}`; }
  function extractSeq4(code) { const m = String(code || '').match(/(\d{4})$/); return m ? m[1] : ''; }

  async function getMaxSeqInGroup(khoa, dot) {
    const q = String(khoa).trim();
    let page = 1, size = 500, max = 0;
    for (;;) {
      const r = await apiFetch(`/applicants/search?q=${encodeURIComponent(q)}&page=${page}&size=${size}`);
      if (!r || !r.ok) break;
      const j = await (r.json().catch(()=>({})));
      const arr = Array.isArray(j?.items) ? j.items : [];
      for (const it of arr) {
        if (String(it.khoa).trim() !== String(khoa).trim()) continue;
        if (String(it.dot).trim()  !== String(dot).trim())  continue;
        const m = String(it.ma_ho_so || '').match(/(\d{4})$/);
        if (m) {
          const n = parseInt(m[1], 10);
          if (Number.isFinite(n) && n > max) max = n;
        }
      }
      if (arr.length < size) break;
      page += 1;
    }
    return max;
  }
  async function generateNextSeq4(khoa, dot) { if (!khoa || !dot) return ""; const cur = await getMaxSeqInGroup(khoa, dot); return String(cur + 1).padStart(4,'0'); }
  async function generateNextMaHoSoByGroup(khoa, dot) { const max = await getMaxSeqInGroup(khoa, dot); return composeMaHoSoByGroup(khoa, dot, max + 1); }

  async function payloadForCreate() {
    const k = ($('khoa')?.value || '').trim();
    const d = ($('dot')?.value  || '').trim();
    if (!k || !d) { showToast("Vui lòng chọn Niên khoá và Đợt trước khi lưu.", "warn"); return null; }

    let seq4 = ($('ma_ho_so')?.value || '').trim();
    if (!/^\d{4}$/.test(seq4)) {
      const seq = await generateNextSeq4(k, d) || '0001';
      $('ma_ho_so').value = seq;
      $('ma_ho_so').placeholder = seq;
      seq4 = seq;
    }

    const today = new Date().toISOString().slice(0,10);
    $('ngay_nhan_hs').value = today;

    const body = {
      ma_ho_so: seq4,
      ngay_nhan_hs: ymdKeep(today),
      ho_ten: '',
      gioi_tinh: $('gioi_tinh').value || null,
      dan_toc: $('dan_toc').value.trim() || null,
      ma_so_hv: $('ma_so_hv').value.trim(),
      ngay_sinh: ymdKeep($('ngay_sinh').value) || null,
      so_dt: $('so_dt').value.trim() || null,
      email_hoc_vien: $('email_hoc_vien').value.trim() || null,
      nganh_nhap_hoc: $('nganh_nhap_hoc').value.trim() || null,
      dot: d,
      khoa: k,
      da_tn_truoc_do: $('da_tn_truoc_do').value || null,
      ghi_chu: $('ghi_chu').value.trim() || null,
      nguoi_nhan_ky_ten: $('nguoi_nhan_ky_ten').value.trim() || null,
      docs: collectDocs(),
      checklist_version_name: window.__CHECKLIST_VERSION_NAME__ || 'v1',
    };
    const _ho_dem = $('ho_dem')?.value || '';
    const _ten    = $('ten')?.value    || '';
    body.ho_ten = joinFullName(_ho_dem, _ten);
    body.ho_dem = _ho_dem;
    body.ten    = _ten;

    return body;
  }

  async function tryPreviewMaHoSo(force = false) {
    if (!force && window.loadedApplicant?.ma_so_hv) return;
    const k = ($('khoa')?.value || '').trim();
    const d = ($('dot')?.value  || '').trim();
    const el = $('ma_ho_so'); if (!el) return;
    if (!k || !d) { el.value = ''; el.placeholder = '0000'; return; }

    try {
      const full = await generateNextMaHoSoByGroup(k, d);
      const m = /(\d{4})$/.exec(full);
      const seq = (m ? m[1] : '0001');
      el.value = seq;
      el.placeholder = seq;
    } catch {
      el.value = ''; el.placeholder = '0000';
    }
  }

  $('khoa').addEventListener('change', () => tryPreviewMaHoSo(true));
  $('dot').addEventListener('change',  () => tryPreviewMaHoSo(true));

  function payloadForUpdate() {
    const currentDate = $("ngay_nhan_hs").value || new Date().toISOString().split("T")[0];
    const seq4 = $("ma_ho_so").value.trim();

    const payload = {
      ngay_nhan_hs: ymdKeep(currentDate),
      ho_ten: $("ho_ten").value.trim(),
      gioi_tinh: $("gioi_tinh").value || null,
      dan_toc: $("dan_toc").value.trim() || null,
      ma_so_hv: $("ma_so_hv").value.trim(),
      ngay_sinh: ymdKeep($("ngay_sinh").value) || null,
      so_dt: $("so_dt").value.trim() || null,
      email_hoc_vien: $("email_hoc_vien").value.trim() || null,
      nganh_nhap_hoc: $("nganh_nhap_hoc").value.trim() || null,
      dot: $("dot").value.trim() || null,
      khoa: $("khoa").value.trim() || null,
      da_tn_truoc_do: $("da_tn_truoc_do").value || null,
      ghi_chu: $("ghi_chu").value.trim() || null,
      nguoi_nhan_ky_ten: $("nguoi_nhan_ky_ten").value.trim() || null,
      docs: collectDocs(),
    };

    if (/^\d{4}$/.test(seq4)) payload.ma_ho_so = seq4; else payload.auto_assign_ma_ho_so = true;

    const _ho_dem = $('ho_dem')?.value || '';
    const _ten    = $('ten')?.value    || '';
    payload.ho_ten = joinFullName(_ho_dem, _ten);
    payload.ho_dem = _ho_dem;
    payload.ten    = _ten;

    return payload;
  }

  let loadedDocsByCode = {};
  function setPrintButtonsEnabled(on) { $('btnPrintLoadedA5').disabled = !on; $('btnPrintLoadedA4').disabled = !on; }

  function populateFormFromApplicant(a={}, docs){
    $('ma_ho_so').value = extractSeq4(a.ma_ho_so) || "";
    $('ngay_nhan_hs').value = fmtDateToInput(a.ngay_nhan_hs);
    $('khoa').value = a.khoa || "";

    const full = a.ho_ten || a.full_name || '';
    const { ho_dem, ten } = splitVietnameseName(full);
    $('ho_dem').value = a.ho_dem || ho_dem || '';
    $('ten').value    = a.ten    || ten    || '';
    $('ho_ten').value = joinFullName($('ho_dem').value, $('ten').value);

    $('ma_so_hv').value = a.ma_so_hv || "";
    $('ngay_sinh').value = fmtDateToInput(a.ngay_sinh);
    $('gioi_tinh').value = a.gioi_tinh || "";
    $('dan_toc').value = a.dan_toc || "";
    $('so_dt').value = a.so_dt || "";
    $('email_hoc_vien').value = a.email_hoc_vien || "";
    $('nganh_nhap_hoc').value = a.nganh_nhap_hoc || "";
    $('dot').value = a.dot || "";
    $('da_tn_truoc_do').value = a.da_tn_truoc_do || "";
    $('ghi_chu').value = a.ghi_chu || "";
    $('nguoi_nhan_ky_ten').value = a.nguoi_nhan_ky_ten || $('nguoi_nhan_ky_ten').value || "";

    loadedDocsByCode = {}; (docs||[]).forEach(d => loadedDocsByCode[d.code] = d.so_luong || 0);
    const applyDocsToTable = () => {
      document.querySelectorAll('.has-doc').forEach(chk => {
        const code = chk.dataset.code; const qty = document.querySelector(`.qty[data-code="${code}"]`);
        const n = loadedDocsByCode[code] ?? 0;
        if (n > 0) { chk.checked = true; qty.disabled=false; qty.classList.remove("bg-gray-100","text-gray-400"); qty.value = String(n); }
        else { chk.checked = false; qty.disabled=true; qty.classList.add("bg-gray-100","text-gray-400"); qty.value = ""; }
      });
    };
    if (document.querySelectorAll('#docsBody tr').length === 0) loadChecklist().then(applyDocsToTable); else applyDocsToTable();
    try { bindNameInputs(); } catch(_){}
  }

  async function loadApplicantByMSHV(mshv){
    let r = await apiFetch(`/applicants/by-mshv/${encodeURIComponent(mshv)}`);
    if (r && r.ok) {
      const data = await r.json();
      const ap = (data && data.applicant) ? { ...data.applicant, docs: data.docs || [] } : data;
      if (isSoftDeleted(ap)) { showToast(`MSHV ${mshv} đã bị xóa, không thể mở!`, "warn"); throw new Error(`Hồ sơ ${mshv} đã bị xóa!`); }
      return ap;
    }
    if (r && r.status === 404) { showToast(`Không tìm thấy MSHV ${mshv}`, "warn"); throw new Error(`Không tìm thấy hồ sơ ${mshv}`); }

    if (!r || r.status === 405) {
      const rs = await apiFetch(`/applicants/search?q=${encodeURIComponent(mshv)}`);
      if (rs && rs.ok) {
        const j = await rs.json();
        let raw = Array.isArray(j.items) ? j.items : (Array.isArray(j) ? j : []);
        raw = (raw || []).filter(it => !isSoftDeleted(it));
        const hit = raw.find(x => (String(x.ma_so_hv||'').toLowerCase() === String(mshv).toLowerCase()));
        if (hit) {
          const rd = await apiFetch(`/applicants/by-code/${encodeURIComponent(hit.ma_ho_so)}`);
          if (rd && rd.ok) {
            const d2 = await rd.json();
            const ap2 = (d2 && d2.applicant) ? { ...d2.applicant, docs: d2.docs || [] } : d2;
            if (isSoftDeleted(ap2)) { showToast(`MSHV ${mshv} đã bị xóa không thể mở!`, "warn"); throw new Error(`Hồ sơ ${mshv} đã bị xóa!`); }
            return ap2;
          }
        }
      }
    }
    const t = r ? await r.text().catch(()=>"(không phản hồi)") : "(không phản hồi)";
    throw new Error(`Lỗi tải hồ sơ (HTTP ${r ? r.status : '???'})\n${t}`);
  }

  function askUpdateReason() {
    return new Promise((resolve) => {
      const wrap   = $('modalUpdateReason');
      const select = $('updateReasonSelect');
      const txt    = $('updateReasonText');
      const ok     = $('urOK');
      const cancel = $('urCancel');
      const close  = $('urClose');

      select.value = "";
      txt.value = "";

      const toggleOther = () => {
        if (select.value === 'khac') {
          txt.parentElement.classList.remove('hidden');
        } else {
          txt.parentElement.classList.add('hidden');
        }
      };
      toggleOther();

      wrap.classList.remove('hidden');
      wrap.classList.add('flex');

      const onBackdrop = (e) => { if (e.target === wrap) done(null); };
      const onEsc = (e) => { if (e.key === 'Escape') done(null); };

      wrap.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onEsc);
      select.addEventListener('change', toggleOther);

      const done = (v) => {
        wrap.classList.add('hidden');
        wrap.classList.remove('flex');
        ok.onclick = cancel.onclick = close.onclick = null;
        wrap.removeEventListener('click', onBackdrop);
        document.removeEventListener('keydown', onEsc);
        select.removeEventListener('change', toggleOther);
        resolve(v);
      };

      ok.onclick = () => {
        const key  = select.value;
        const text = txt.value.trim();
        if (!key)  { showToast("Vui lòng chọn lý do cập nhật.", "warn"); return; }
        if (key === "khac" && !text) {
          showToast("Nhập lý do khác.", "warn");
          return;
        }
        done({ key, text });
      };
      cancel.onclick = close.onclick = () => done(null);
    });
  }

  async function clearForm(){
    ["ma_ho_so","ngay_nhan_hs","khoa","ho_ten","ho_dem","ten","ma_so_hv","gioi_tinh","ngay_sinh","so_dt","email_hoc_vien","nganh_nhap_hoc","dot","da_tn_truoc_do","ghi_chu"].forEach(id=>{
      const el=$(id); if(!el) return; if(el.type==='checkbox') el.checked=false; else el.value="";
    });
    document.querySelectorAll('.has-doc').forEach(chk=>{ chk.checked=false; });
    document.querySelectorAll('.qty').forEach(q=>{ q.value=""; q.disabled=true; q.classList.add("bg-gray-100","text-gray-400"); });
  }

  function resetToNewForm(){
    const today = new Date().toISOString().slice(0,10);
    clearForm();
    $('ngay_nhan_hs').value = today;
    window.loadedApplicant = null;
    refreshMainButtonLabel(); 
    setPrintButtonsEnabled(false);
    $('lookupMsg').textContent = "";
    $('msg').textContent = "";
    $('nameResults')?.classList.add('hidden');
    $('gioi_tinh').value = "";
    tryPreviewMaHoSo(true);
  }

  async function saveOrUpdate(e) {
    const btn = e?.currentTarget || $('btnSaveOrUpdate');
    const old = btn?.textContent;
    if (btn) { btn.disabled = true; btn.textContent = 'Đang xử lý...'; }

    try {
      if (window.loadedApplicant?.ma_so_hv) {
        const reason = await askUpdateReason();
        if (!reason) return;

        const body = payloadForUpdate();
        body.update_reason_key  = reason.key;
        body.update_reason_text = reason.text;

        $('lookupMsg').textContent = 'Đang cập nhật...';
        const r = await apiFetch(`/applicants/${encodeURIComponent(window.loadedApplicant.ma_so_hv)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (handleAuth(r)) return;
        if (!r.ok) {
          const t = await r.text();
          throw new Error(`Cập nhật thất bại (${r.status}): ${t}`);
        }
        const res = await r.json();
        showToast(`Đã cập nhật MSHV ${res.ma_so_hv}`, 'success');
        const mshv = res.ma_so_hv || window.loadedApplicant?.ma_so_hv;
        if (mshv) {
          const a = await loadApplicantByMSHV(mshv);
          window.loadedApplicant = { ma_so_hv: a.ma_so_hv, ma_ho_so: a.ma_ho_so };
          refreshMainButtonLabel();
          populateFormFromApplicant(a, a.docs || []);
          setPrintButtonsEnabled(true);
          $('lookupMsg').textContent = `Đã cập nhật xong MSHV ${a.ma_so_hv}.`;
        } else {
          $('lookupMsg').textContent = 'Đã cập nhật.';
        }
      } else {
        const created = await createApplicant();
        if (created) {
          showToast(`Đã lưu hồ sơ mới: ${created.ma_so_hv}`, 'success');
          $('msg').textContent = `Đã lưu MSHV ${created.ma_so_hv}`;
          resetToNewForm();
        }
      }
    } catch (err) {
      $('lookupMsg').textContent = err.message || 'Lỗi xử lý.';
      showToast(err.message || 'Lỗi xử lý!', 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = old || 'Lưu'; }
    }
  }
  $('btnSaveOrUpdate')?.addEventListener('click', saveOrUpdate);

  async function createApplicant(){
    const markError = (elId, msg) => {
      const el = $(elId);
      if (el) {
        el.classList.add('ring-2','ring-red-400');
        el.scrollIntoView({behavior:'smooth', block:'center'});
        el.focus();
        setTimeout(()=> el.classList.remove('ring-2','ring-red-400'), 1800);
      }
      showToast(msg, 'error');
    };

    const hoDem = ( $('ho_dem')?.value || '' ).trim();
    const ten   = ( $('ten')?.value    || '' ).trim();
    const hoTen = joinFullName(hoDem, ten);
    const msHv  = ( $('ma_so_hv')?.value || '' ).trim();

    if (!ten)  { markError('ten',    'Vui lòng nhập Tên.');    return null; }
    if (!msHv) { markError('ma_so_hv','Vui lòng nhập MSHV.');  return null; }

    const khoa = ( $('khoa')?.value || '' ).trim();
    const dot  = ( $('dot') ?.value || '' ).trim();
    if (!khoa) { markError('khoa', 'Chọn Niên khoá.'); return null; }
    if (!dot)  { markError('dot',  'Chọn Đợt.');       return null; }

    const email = ( $('email_hoc_vien')?.value || '' ).trim();
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { markError('email_hoc_vien','Email không hợp lệ.'); return null; }
    const phone = ( $('so_dt')?.value || '' ).trim();
    if (phone && !/^[0-9 +().-]{8,20}$/.test(phone)) { markError('so_dt','Số điện thoại chưa đúng.'); return null; }

    const body = await payloadForCreate();
    if (!body) return null;

    body.ho_ten = hoTen; body.ho_dem = hoDem; body.ten = ten;
    body.ma_so_hv = msHv; body.khoa = khoa; body.dot = dot;

    if (!body.ngay_nhan_hs) {
      body.ngay_nhan_hs = new Date().toISOString().slice(0,10);
      const ngayNhan = $('ngay_nhan_hs'); if (ngayNhan) ngayNhan.value = body.ngay_nhan_hs;
    }
    if (!body.ma_ho_so) {
      const seq = await generateNextSeq4(khoa, dot);
      body.ma_ho_so = seq;
      const mhs = $('ma_ho_so'); if (mhs) mhs.value = seq;
    }

    const r = await apiFetch("/applicants", {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify(body)
    });
    if (handleAuth(r)) return null;

    const j = await safeJson(r);
    if (!r || !r.ok){
      console.log("👀 Payload gửi lên:", body);
      showToast(j.detail || `Lỗi lưu (HTTP ${r ? r.status : '???'})`, "error", 4000);
      return null;
    }

    window.loadedApplicant = { ma_so_hv: j.ma_so_hv || body.ma_so_hv, ma_ho_so: j.ma_ho_so || body.ma_ho_so };
    setPrintButtonsEnabled(true);
    return j;
  }

  /* ===== Tìm theo tên ===== */
  async function searchByName(fullName) {
    const q = normSpace(fullName);
    if (q.length < 2) throw new Error("Nhập tối thiểu 2 ký tự để tìm theo tên.");

    const urls = [
      `/applicants/search?q=${encodeURIComponent(q)}`,
      `/applicants/search?name=${encodeURIComponent(q)}`,
      `/applicants/search?full_name=${encodeURIComponent(q)}`,
      `/applicants/by-name?q=${encodeURIComponent(q)}`,
    ];
    const readJson = async (r) => { try { return await r.json(); } catch { return null; } };

    let lastErrText = "";
    for (const u of urls) {
      const r = await apiFetch(u);
      if (!r) continue;
      if (r.status === 401 || r.status === 403) { handleAuth(r); return []; }
      if (!r.ok) { try { lastErrText = await r.text(); } catch {} ; continue; }

      const j = await readJson(r); if (!j) continue;
      let raw = [];
      if (Array.isArray(j)) raw = j;
      else if (Array.isArray(j.items)) raw = j.items;
      else if (Array.isArray(j.data))  raw = j.data;
      else if (Array.isArray(j.results)) raw = j.results;
      else if (j.items && j.items.data && Array.isArray(j.items.data)) raw = j.items.data;

      raw = (raw || []).filter(it => !isSoftDeleted(it));

      const list = raw.map(it => ({
        ho_ten: it.ho_ten || it.full_name || it.ten || "",
        ma_ho_so: it.ma_ho_so || it.code || it.ma_hs || "",
        ma_so_hv: it.ma_so_hv || it.mssv || it.mshv || "",
        ngay_nhan_hs: it.ngay_nhan_hs || it.created_at || it.ngay || null,
        dot: it.dot || it.dot_tuyen || "",
      }));
      if (list.length) return list;
    }
    if (lastErrText) console.warn("Name search last error:", lastErrText);
    return [];
  }

  function filterAndSortByName(list, q, limit=20){
    const scored=(list||[]).map(it=>({it, score:matchScore(it.ho_ten||it.full_name||'', q)})).filter(x=>x.score>0);
    scored.sort((p,q)=>q.score-p.score);
    return scored.slice(0,limit).map(x=>x.it);
  }

  function renderNameResults(list){
    list = Array.isArray(list) ? list : (Array.isArray(list?.items) ? list.items : []);
    const box = $('nameResults'); const ul = $('nameResultsList'); if(!box||!ul) return;

    ul.innerHTML = '';
    if(!list || list.length===0){
      box.classList.remove('hidden');
      const li = document.createElement('li');
      li.className = 'p-2 text-sm text-gray-500';
      li.textContent = 'Không tìm thấy.';
      ul.appendChild(li);
    } else {
      const frag = document.createDocumentFragment();
      list.forEach(it=>{
        const li = document.createElement('li');
        li.className = 'p-2 hover:bg-gray-50 cursor-pointer';
        li.dataset.mshv = it.ma_so_hv || '';

        const top = document.createElement('div');
        top.className = 'flex justify-between';
        const name = document.createElement('div');
        name.className = 'font-medium';
        name.textContent = it.ho_ten || '';
        const date = document.createElement('div');
        date.className = 'text-xs text-gray-500';
        date.textContent = (it.ngay_nhan_hs || '').toString().slice(0,10);
        top.appendChild(name); top.appendChild(date);

        const bot = document.createElement('div');
        bot.className = 'text-xs text-gray-600';
        bot.textContent = `Mã HS: ${it.ma_ho_so||''} • MSHV: ${it.ma_so_hv||''} • Đợt: ${it.dot||''}`;

        li.appendChild(top); li.appendChild(bot);
        frag.appendChild(li);
      });
      ul.appendChild(frag);
    }

    if (!ul._boundClick) {
      ul.addEventListener('click', (e)=>{
        const li=e.target.closest('li[data-mshv]'); if(!li) return;
        $('q_ma_so_hv').value = li.dataset.mshv || '';
        box.classList.add('hidden');
        $('btnLoadApplicantMSHV')?.click();
      });
      ul._boundClick = true;
    }
    box.classList.remove('hidden');
  }

  const liveSearchName = debounce(async () => {
    const name = $('q_ho_ten').value.trim();
    if (name.length < 2) { $('nameResults')?.classList.add('hidden'); return; }
    $('lookupMsg').textContent = 'Đang tìm...';
    let list = await searchByName(name);
    list = filterAndSortByName(list, name, 25);
    renderNameResults(list);
    $('lookupMsg').textContent = list.length ? `Tìm thấy ${list.length} kết quả.` : 'Không tìm thấy.';
  }, 300);

  $('q_ho_ten').addEventListener('input', liveSearchName);
  $('q_ho_ten').addEventListener('focus', liveSearchName);
  $('btnSearchByName').addEventListener('click', debounce(async ()=>{
    try{
      const name = $('q_ho_ten').value.trim();
      if(name.length < 2){ alert("Nhập tối thiểu 2 ký tự."); return; }
      $('lookupMsg').textContent = "Đang tìm theo tên...";
      let list = await searchByName(name);
      list = filterAndSortByName(list, name, 25);
      renderNameResults(list);
      $('lookupMsg').textContent = list.length ? `Tìm thấy ${list.length} kết quả.` : "Không tìm thấy.";
    }catch(e){ $('lookupMsg').textContent = e.message || "Lỗi tìm kiếm."; showToast(e.message || "Lỗi tìm kiếm.", "error"); }
  }, 400));

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#nameResults') && !e.target.closest('#q_ho_ten')) {
      $('nameResults')?.classList.add('hidden');
    }
  });

  // === Autocomplete: MSHV (live) ===
  function ensureMshvBox() {
    let box = $('mshvResults');
    if (!box) {
      const fld = $('q_ma_so_hv').parentElement;
      fld.classList.add('relative');
      box = document.createElement('div');
      box.id = 'mshvResults';
      box.className = 'absolute left-0 top-full mt-1 z-50 w-full max-h-64 overflow-auto rounded-md border bg-white shadow hidden';
      box.innerHTML = '<ul id="mshvResultsList" class="divide-y"></ul>';
      fld.appendChild(box);
    }
    return box;
  }

  async function searchMSHVPartial(q) {
    const r = await apiFetch(`/applicants/search?q=${encodeURIComponent(q)}`);
    if (r && r.ok) {
      const j = await safeJson(r);
      let raw = Array.isArray(j?.items) ? j.items : (Array.isArray(j) ? j : []);
      raw = (raw || []).filter((it) => !isSoftDeleted(it));
      return raw
        .map((it) => ({
          ho_ten: it.ho_ten || it.full_name || '',
          ma_so_hv: it.ma_so_hv || it.mssv || it.mshv || '',
          ma_ho_so: it.ma_ho_so || it.code || '',
          ngay_nhan_hs: it.ngay_nhan_hs || it.created_at || null,
        }))
        .filter((x) => String(x.ma_so_hv || '').toLowerCase().includes(q.toLowerCase()))
        .slice(0, 20);
    }
    return [];
  }

  function renderMshvResults(list) {
    const box = ensureMshvBox();
    const ul  = $('mshvResultsList');
    ul.innerHTML = '';

    if (!list.length) {
      box.classList.remove('hidden');
      const li = document.createElement('li');
      li.className = 'p-2 text-sm text-gray-500';
      li.textContent = 'Không tìm thấy.';
      ul.appendChild(li);
      return;
    }

    const frag = document.createDocumentFragment();
    list.forEach(it=>{
      const li = document.createElement('li');
      li.className = 'p-2 hover:bg-gray-50 cursor-pointer';
      li.dataset.mshv = it.ma_so_hv;

      const top = document.createElement('div');
      top.className = 'flex justify-between';
      const left = document.createElement('div');
      left.className = 'font-medium';
      left.textContent = it.ma_so_hv;
      const right = document.createElement('div');
      right.className = 'text-xs text-gray-500';
      right.textContent = (it.ngay_nhan_hs || '').toString().slice(0,10);
      top.appendChild(left); top.appendChild(right);

      const bot = document.createElement('div');
      bot.className = 'text-xs text-gray-600';
      bot.textContent = `${it.ho_ten||''} • Mã HS: ${it.ma_ho_so||''}`;

      li.appendChild(top); li.appendChild(bot);
      frag.appendChild(li);
    });
    ul.appendChild(frag);

    if (!ul._boundClick) {
      ul.addEventListener('click', (e)=>{
        const li = e.target.closest('li[data-mshv]'); if(!li) return;
        $('q_ma_so_hv').value = li.dataset.mshv || '';
        box.classList.add('hidden');
        $('btnLoadApplicantMSHV')?.click();
      });
      ul._boundClick = true;
    }

    box.classList.remove('hidden');
  }

  const liveSearchMSHV = debounce(async () => {
    const v = $('q_ma_so_hv').value.trim();
    if (v.length < 3) { $('mshvResults')?.classList.add('hidden'); return; }
    $('lookupMsg').textContent = 'Đang gợi ý MSHV...';
    const list = await searchMSHVPartial(v);
    renderMshvResults(list);
    $('lookupMsg').textContent = '';
  }, 250);

  $('q_ma_so_hv').addEventListener('input', liveSearchMSHV);
  $('q_ma_so_hv').addEventListener('focus', liveSearchMSHV);
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#mshvResults') && !e.target.closest('#q_ma_so_hv')) {
      $('mshvResults')?.classList.add('hidden');
    }
  });

  $('q_ma_so_hv').addEventListener('keydown', (e) => {
    const box = $('mshvResults');
    const ul  = $('mshvResultsList');
    if (!box || box.classList.contains('hidden')) return;

    const items = ul.querySelectorAll('li[data-mshv]');
    if (!items.length) return;

    let idx = ul._idx ?? -1;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      idx = (idx + 1) % items.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      idx = (idx - 1 + items.length) % items.length;
    } else if (e.key === 'Enter' && idx >= 0) {
      e.preventDefault();
      items[idx].click();
      ul._idx = -1;
      return;
    } else if (e.key === 'Escape') {
      box.classList.add('hidden');
      ul._idx = -1;
      return;
    }

    items.forEach((el, i) => el.classList.toggle('bg-blue-50', i === idx));
    if (idx >= 0) items[idx].scrollIntoView({ block: 'nearest' });
    ul._idx = idx;
  });

  /* ===== In PDF ===== */
  function openPdf(url){
    const w = window.open(url, "_blank", "noopener,noreferrer");
    if (!w) {
      showToast('Trình duyệt đang chặn pop-up. Hãy bật pop-up cho trang này rồi bấm lại.', 'warn', 4000);
    }
  }
  $("btnPrintLoadedA5").onclick = async (e) => { e.preventDefault();
    const cur = window.loadedApplicant;
    if (!cur?.ma_so_hv) { showToast("Chưa tải hồ sơ nào.", "warn"); return; }
    if (isSoftDeleted(cur)) { showToast("Hồ sơ đã bị xóa, không thể in!", "warn"); return; }

    await journalTrack({
      action: 'PRINT_IN',
      detail: { scope: 'SINGLE', filters: { mshv: cur.ma_so_hv }, name_mode: 'A5', count: 1 }
    });

    openPdf(makeUrl(`/applicants/${encodeURIComponent(cur.ma_so_hv)}/print-a5`));
  };

  $("btnPrintLoadedA4").onclick = async (e) => { e.preventDefault();
    const cur = window.loadedApplicant;
    if (!cur?.ma_so_hv) { showToast("Chưa tải hồ sơ nào!", "warn"); return; }
    if (isSoftDeleted(cur)) { showToast("Hồ sơ đã bị xóa, không thể in!", "warn"); return; }

    await journalTrack({
      action: 'PRINT_IN',
      detail: { scope: 'SINGLE', filters: { mshv: cur.ma_so_hv }, name_mode: 'A4', count: 1 }
    });

    openPdf(makeUrl(`/applicants/${encodeURIComponent(cur.ma_so_hv)}/print`));
  };

  // Load theo MSHV
  $('btnLoadApplicantMSHV').addEventListener('click', async () => {
    const mshv = $('q_ma_so_hv').value.trim();
    if (!mshv) { alert("Nhập MSHV (MSSV) để tải!"); return; }

    $('lookupMsg').textContent = "Đang tải theo MSHV...";

    try {
      let a = await loadApplicantByMSHV(mshv);

      window.loadedApplicant = { ma_so_hv: a.ma_so_hv, ma_ho_so: a.ma_ho_so };
      populateFormFromApplicant(a, a.docs || []);
      setPrintButtonsEnabled(true);
      const displayFull = a.ho_ten || joinFullName(a.ho_dem, a.ten);
      $('lookupMsg').textContent = `Đã tải: ${a.ma_ho_so} ➖ ${displayFull} ➖ ${a.ma_so_hv}`;
    } catch (e) {
      $('lookupMsg').textContent = e.message || 'Không tải được hồ sơ.';
      window.loadedApplicant = null;
      setPrintButtonsEnabled(false);
      await clearForm();
    }
  });
  $('q_ma_so_hv').addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ e.preventDefault(); $('btnLoadApplicantMSHV').click(); } });

  // Hotkeys & input clamps
  document.addEventListener('keydown', (e)=>{ if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $('btnSaveOrUpdate')?.click(); } });
  document.addEventListener('input', (e)=>{ const t = e.target; if (t.classList?.contains('qty')) { let v = parseInt(t.value||'0',10); if (!Number.isFinite(v) || v < 0) v = 0; if (v > 50) v = 50; t.value = String(v); } });

  ['khoa','dot'].forEach(id=>{
    $(id)?.addEventListener('change', ()=>{ if (window.loadedApplicant?.ma_so_hv) showToast('Đang mở hồ sơ – thay đổi Khóa/Đợt chỉ ảnh hưởng mã mới.', 'warn'); });
  });

  /* ===== init ===== */
  window.addEventListener('load', async () => {
    const today = new Date().toISOString().slice(0,10);
    $('ngay_nhan_hs').value = today;
    $('q_ma_so_hv')?.focus();

    await ensureApiBaseAndPrefix();
    await refreshAuthUI();
    await loadChecklist();
    await tryPreviewMaHoSo(true);
    bindNameInputs();
    setPrintButtonsEnabled(false);
    refreshMainButtonLabel(); 

    const url = new URL(window.location.href);
    const mshv = url.searchParams.get('mshv');
    if (mshv) { $('q_ma_so_hv').value = mshv; $('btnLoadApplicantMSHV').click(); }
  });

  // Test API & switch base
  $('btnTestApi').addEventListener('click', async ()=>{
    const base = apiBase();
    const pref = await pingPrefix(base);
    if (pref === null) showToast("Không ping được API /health", "error");
    else { API_PREFIX = pref; localStorage.setItem(STORAGE_KEY, base); showToast(`Kết nối OK (${base}${pref||""}/health)`, "success"); }
  });
  $('apiBase').addEventListener('change', async ()=>{
    const base = apiBase(); localStorage.setItem(STORAGE_KEY, base);
    const pref = await pingPrefix(base);
    if (pref === null) showToast("Không ping được API /health", "warn");
    else { API_PREFIX = pref; showToast("Đã cập nhật máy chủ API", "success"); }
  });

  // Nút reload checklist riêng
  $('btnReloadChecklist').addEventListener('click', async ()=>{
    await loadChecklist();
    showToast('Đã tải lại danh mục hồ sơ.', 'success');
  });
  document.addEventListener('DOMContentLoaded', () => {
    const path = location.pathname.replace(/\/+$/, '');

    document.querySelectorAll('.nav-item').forEach(a => {
      const href = (a.getAttribute('href') || '').replace(/\/+$/, '');
      if (!href) return;

      if (path === href || path.endsWith(href)) {
        a.classList.add('nav-item-active');
      }
    });
  });

  function refreshMainButtonLabel() {
    const btn = $('btnSaveOrUpdate');
    if (!btn) return;
    btn.textContent = window.loadedApplicant?.ma_so_hv ? 'Cập nhật' : 'Lưu';
  }

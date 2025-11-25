  //js/journal.js

  /* ====== Khóa URL sạch ====== */
  (function lockCleanJournalURL(){
    const clean = () => { if (location.pathname !== '/journal.html' || location.search || location.hash) history.replaceState(null, '', '/journal.html'); };
    clean();
    const _replace = history.replaceState.bind(history);
    const _push    = history.pushState.bind(history);
    const toClean = (url) => {
      try { const u = new URL(url, location.origin); return (/\/journal\.html$/.test(u.pathname)) ? u.pathname : url; }
      catch { return url; }
    };
    history.replaceState = (s,t,u)=> _replace(s,t,toClean(u));
    history.pushState    = (s,t,u)=> _push(s,t,toClean(u));
    window.addEventListener('popstate', clean);
  })();

  /* ====== Basics ====== */
  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>document.querySelectorAll(s);
  const STORAGE_KEY = 'apiBase';
  const PREFIX_CANDIDATES = ['', '/api'];
  let API_PREFIX = '';
  const debounce = (fn, ms=300)=>{ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); } };

  (function initApiBase(){ const saved = localStorage.getItem(STORAGE_KEY) || window.location.origin; $('#apiBase').value = saved; })();
  const apiBase = ()=> $('#apiBase').value.trim().replace(/\/+$/,'');
  const makeUrl = (path)=> apiBase() + API_PREFIX + path;

  async function detectPrefix(){
    for(const p of PREFIX_CANDIDATES){
      try{ const r = await fetch(apiBase()+p+'/health', {credentials:'include'}); if(r.ok){ API_PREFIX=p; return; } }catch(_){}
    }
    API_PREFIX='';
  }
  async function apiFetch(path, init={}){
    const opts = {credentials:'include', ...init};
    let r = await fetch(makeUrl(path), opts).catch(()=>null);
    if (r && r.status !== 404) return r;
    const alt = (API_PREFIX === '' ? '/api' : '');
    if (alt !== API_PREFIX){
      try{ const r2 = await fetch(apiBase()+alt+path, opts); if(r2.ok){ API_PREFIX=alt; return r2; } return r2; }catch(e){ return null; }
    }
    return r;
  }
  /* ====== Labels ====== */
  const ACTION_LABELS = {
    CREATE:"Tạo mới",
    UPDATE:"Cập nhật",
    DELETE_SOFT:"Xóa tạm",
    DELETE_HARD:"Xóa vĩnh viễn",
    DELETE:"Xóa vĩnh viễn",
    DELETE_REQUEST:"Yêu cầu xóa",
    RESTORE:"Khôi phục",
    PRINT_IN:"In",     // ✅ thêm
    EXPORT:"Xuất Excel", // ✅ thêm
    EMAIL_SENT: "Gửi email",
    EXCEPTION:"Lỗi hệ thống",
    READ:"Tra cứu",
    BATCH_UPDATE: "Cập nhật hàng loạt",
    BATCH_UPDATE_PREVIEW: "Xem trước (batch)",
  };
  const actionVi = c => ACTION_LABELS[(c||'').toUpperCase()] || (c||'—');

    // 👇 THÊM ĐOẠN NÀY: các action KHÔNG muốn hiển thị trong bảng
  const HIDE_ACTIONS = new Set([
    'READ',              // Tra cứu
    'EXCEPTION',         // Lỗi hệ thống
    'EMAIL_DRAFT_OPEN',  // mở màn hình soạn email
    'EMAIL_PREVIEW',     // xem trước email, nếu có
    'EMAIL_TEMPLATE_VIEW',
    'BATCH_UPDATE_PREVIEW' // chỉ xem trước batch, không thực sự cập nhật
  ]);

  const FIELD_LABELS = {
    checklist_version_name: "Version danh mục",
    checklist_version_id:   "Version danh mục (ID)",
    da_tn_truoc_do:"Đã TN trước đó",
    deleted_at:"Thời điểm xóa",
    deleted_by:"Người xóa",
    deleted_reason:"Lý do xóa",
    dot:"Đợt",
    email_hoc_vien:"Email học viên",
    ghi_chu:"Ghi chú",
    ho_ten:"Họ tên",
    khoa:"Khóa",
    ma_ho_so:"Mã hồ sơ",
    ma_so_hv:"Mã số học viên",
    nganh_nhap_hoc:"Ngành nhập học",
    ngay_nhan_hs:"Ngày nhận hồ sơ",
    ngay_sinh:"Ngày sinh",
    nguoi_nhan_ky_ten:"Người nhận",
    printed:"Trạng thái in",
    status:"Trạng thái",
    so_dt:"Số điện thoại",
    gioi_tinh:"Giới tính",
    dan_toc:"Dân tộc",
    update_reason: "Lý do cập nhật",
    ho_dem: "Họ đệm",
    ten: "Tên",
    ho_ten: "Họ và tên",
  };
  const getFieldLabel = (k) => FIELD_LABELS[k] || k;

  /* ====== State ====== */
  const state = { page:1, size:Number(localStorage.getItem('journal.pageSize')||20), total:0, sort:{key:'occurred_at', dir:'desc'}, filters:{}, currentLog:null };
  const pagesTotal = ()=> Math.max(1, Math.ceil(state.total / state.size));

  function setState({loading=false, empty=false}){
    $('#loading').classList.toggle('hidden', !loading);
    $('#emptyState').classList.toggle('hidden', !empty);
    $('#tableWrap').classList.toggle('hidden', loading || empty);
  }
  function setAriaSort(){
    $$('.th-sortable').forEach(th=> th.removeAttribute('aria-sort'));
    if (state.sort.key){
      const th = document.querySelector(`.th-sortable[data-sort="${state.sort.key}"]`);
      if (th) th.setAttribute('aria-sort', state.sort.dir==='asc'?'ascending':'descending');
    }
  }
  function toggleSort(key){
    if (state.sort.key === key) state.sort.dir = (state.sort.dir==='asc'?'desc':'asc');
    else { state.sort.key=key; state.sort.dir='asc'; }
    setAriaSort(); load();
  }

  function qs(){
    const p = new URLSearchParams();
    p.set('page', state.page);
    p.set('page_size', state.size);
    const f = state.filters;
    if (f.action === 'PRINT_IN')      p.set('action', 'PRINT');
    else if (f.action === 'PRINT_EXPORT') p.set('action', 'EXPORT');
    else if (f.action)                    p.set('action', f.action);
    if (f.q) p.set('q', f.q);
    if (f.type) p.set('target_type', f.type);
    if (f.id) p.set('target_id', f.id);
    if (f.actor) p.set('actor', f.actor);
    if (f.from) p.set('from', f.from);
    if (f.to) p.set('to', f.to);
    if (state.sort.key) {
      const keyMap = { target: 'target_id' };
      const field = keyMap[state.sort.key] || state.sort.key;
      p.set('sort', `${field}:${state.sort.dir}`);
    }
    return p.toString();
  }

  function syncUrl(){
    if (location.pathname === '/journal.html' && (location.search || location.hash)) {
      history.replaceState(null, '', '/journal.html');
    }
  }

  async function load() {
    setState({ loading: true });
    const tb = $('#tbody');
    tb.innerHTML = `<tr><td colspan="7" class="text-center text-gray-500 py-10">Đang tải dữ liệu…</td></tr>`;

    try {
      const res = await apiFetch('/journal/?' + qs());
      if (!res || !res.ok) throw new Error('Không kết nối được máy chủ');

      const payload = await res.json();

      const items = Array.isArray(payload.items)
        ? payload.items
        : (Array.isArray(payload.data) ? payload.data : []);

      const total = Number(payload.total ?? payload.count ?? items.length ?? 0);
      state.total = total;

      const pages = pagesTotal();
      if (state.page > pages) {
        state.page = pages;
        return load();
      }

      renderTable(items);
      renderPager();
      $('#count').textContent = String(state.total);
      setState({ loading: false, empty: items.length === 0 });


      syncUrl();
    } catch (e) {
      tb.innerHTML = `<tr><td colspan="7" class="text-center text-rose-600 py-10">Lỗi: ${e.message}</td></tr>`;
      setState({ loading: false, empty: false });
    }
  }

  function displayActor(row){
    const name = (row.actor_name ?? "").toString().trim();
    return name || (row.actor_id != null ? `#${row.actor_id}` : "—");
  }

  /* ====== Date helpers (VN) ====== */
  function formatVNDateTime(input) {
    if (!input) return '';
    const d = input instanceof Date ? input : new Date(String(input));
    if (isNaN(d)) return '';
    const parts = new Intl.DateTimeFormat('vi-VN', {
      timeZone:'Asia/Ho_Chi_Minh', year:'numeric', month:'2-digit', day:'2-digit',
      hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
    }).formatToParts(d);
    const get = t => parts.find(p => p.type === t)?.value || '00';
    return `${get('hour')}:${get('minute')}:${get('second')} ${get('day')}/${get('month')}/${get('year')}`;
  }

  function formatVNDateOnly(input) {
    if (!input) return '';
    const d = input instanceof Date ? input : new Date(String(input));
    if (isNaN(d)) return '';
    const parts = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).formatToParts(d);
    const get = t => parts.find(p => p.type === t)?.value || '00';
    return `${get('day')}/${get('month')}/${get('year')}`;
  }

  function maybeFormatDateLike(v) {
    if (v == null || v === '') return null;
    const f = (window.currentRenderField || '').toLowerCase();
    const DATE_FIELDS = new Set([
      'occurred_at', 'deleted_at', 'created_at', 'updated_at',
      'ngay_sinh', 'ngay_nhan_hs'
    ]);
    const looksLikeDateField = DATE_FIELDS.has(f) || /^ngay_/.test(f) || /_at$/.test(f);
    if (!looksLikeDateField) return null;

    if (typeof v === 'number') {
      const ms = v > 1e12 ? v : v * 1000;
      return formatVNDateTime(new Date(ms));
    }
    if (typeof v === 'string') {
      const s = v.trim();
      if (/^\d{4}-\d{2}-\d{2}([T\s].*)?$/.test(s)) {
        const d = new Date(s.replace(' ', 'T'));
        if (!isNaN(d)) return formatVNDateTime(d);
      }
      const m1 = s.match(/^(\d{2}):(\d{2}):(\d{2})\s+(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m1) {
        const [_, hh, mm, ss, dd, MM, yyyy] = m1.map(Number);
        const d = new Date(Date.UTC(yyyy, MM - 1, dd, hh, mm, ss));
        return formatVNDateTime(d);
      }
      const m2 = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m2) {
        const [_, dd, MM, yyyy] = m2.map(Number);
        const d = new Date(Date.UTC(yyyy, MM - 1, dd, 0, 0, 0));
        return formatVNDateTime(d);
      }
    }
    return null;
  }

  /* ====== Table list ====== */
  function renderTable(items){
    const tb = $('#tbody');

    // 👇 LỌC BỎ NHỮNG ACTION KHÔNG MUỐN HIỂN THỊ
    const visibleItems = (items || []).filter(row => {
      const act = String(row.action || '').toUpperCase();
      return !HIDE_ACTIONS.has(act);
    });

    if (!visibleItems.length){
      tb.innerHTML = `<tr><td colspan="8" class="text-center text-gray-500 py-10">Không có log nào (đã ẩn bớt các log tra cứu, lỗi hệ thống, mở email, ...)</td></tr>`;
      return;
    }

    tb.innerHTML='';

    const collator = new Intl.Collator('vi', {numeric:true, sensitivity:'base'});
    const key = state.sort.key, dir = state.sort.dir;
    const actionMap = ACTION_LABELS;

    const getVal = (r)=>{
      if (key==='id')          return r.id;
      if (key==='occurred_at') return r.occurred_at;
      if (key==='actor_name')  return r.actor_name||'';
      if (key==='action')      return actionMap[r.action] || r.action || '';
      if (key==='status')      return r.status||'';
      if (key==='target')      return r.target_id || '';
      return '';
    };

    const sorted = visibleItems.slice().sort((a,b)=>{
      return collator.compare(String(getVal(a)), String(getVal(b)));
    });
    if (dir==='desc') sorted.reverse();

    sorted.forEach(row=>{
      const tr = document.createElement('tr');
      const when = row.occurred_at ? new Date(row.occurred_at) : null;
      const actionLabel = actionVi(row.action);
      const actionCls   = String(row.action||'').toUpperCase();
      tr.innerHTML = `
        <td class="text-left whitespace-nowrap">${row.id}</td>
        <td class="text-center whitespace-nowrap">${when ? formatVNDateTime(when) : ''}</td>
        <td class="text-center">${escapeHtml(displayActor(row))}</td>
        <td class="text-center"><span class="chip ${escapeHtml(actionCls)}">${escapeHtml(actionLabel)}</span></td>
        <td class="text-center whitespace-nowrap">${escapeHtml(row.target_id ?? '—')}</td>
        <td class="text-center">
          ${row.status === 'SUCCESS' ? '<span class="status-ok">OK</span>' : '<span class="status-fail">FAIL</span>'}
        </td>
        <td class="text-center">
          ${
            row.correlation_id
              ? `<button class="btn btn-outline btn-xxs" data-corr="${row.correlation_id}" title="Lọc theo đợt">
                  ${String(row.correlation_id).slice(0,8)}
                </button>`
              : '—'
          }
        </td>
        <td class="text-center">
          <button class="btn btn-outline btn-xs" data-id="${row.id}">View👁️‍🗨️</button>
        </td>`;
      tb.appendChild(tr);
    });

    $$('button[data-id]').forEach(b=> b.onclick=()=> openDetail(b.dataset.id));
    $$('button[data-corr]').forEach(b=>{
      b.onclick = ()=>{
        const corr = b.dataset.corr || '';
        if (!corr) return;
        const q = document.getElementById('q');
        if (q) q.value = corr;
        state.page = 1;
        grabFilters();
        load();
      };
    });
  }

  function renderPager(){
    const pages = Math.max(1, Math.ceil(state.total/state.size));
    $$('.pager').forEach(p=>{
      p.querySelector('.pager-info').textContent = `Trang ${state.page}/${pages} • ${state.total} mục`;
      p.querySelector('.pager-first').disabled = state.page<=1;
      p.querySelector('.pager-prev').disabled  = state.page<=1;
      p.querySelector('.pager-next').disabled  = state.page>=pages;
      p.querySelector('.pager-last').disabled  = state.page>=pages;
    });
  }

  /* ====== Common helpers for detail ====== */
  function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c])); }
  function cellValFor(field, v) { window.currentRenderField = field || null; return cellVal(v); }

  function cellVal(x) {
    if (x === null || x === undefined || x === '')
      return '<span class="text-gray-400">—</span>';

    const fieldCtx = (window.currentRenderField || '').toLowerCase();
    if (fieldCtx === 'gioi_tinh' && typeof x === 'string') {
      const s = x.trim().toLowerCase();
      if (s === 'm' || s === 'nam' || s === 'male' || s === '1') return 'Nam';
      if (s === 'f' || s === 'nu' || s === 'nữ'  || s === 'female' || s === '0') return 'Nữ';
    }

    if (typeof x === 'object' && x && ('key' in x || 'text' in x)) {
      const key  = (x.key  || '').toString();
      const text = (x.text || '').toString();
      const MAP = {
        capnhat_thongtin: 'Cập nhật thông tin học viên',
        capnhat_hoso_moi: 'Cập nhật hồ sơ mới',
        bosung_hoso:      'Bổ sung hồ sơ',
        capnhat_chungchi: 'Cập nhật chứng chỉ',
        chinhsua_hoso:    'Chỉnh sửa hồ sơ',
        khac:             `Lý do khác${text ? ': ' + text : ''}`
      };
      if (key) return escapeHtml(MAP[key] || key);
    }
    if (typeof x === 'string') {
      const MAP = {
        capnhat_thongtin: 'Cập nhật thông tin học viên',
        capnhat_hoso_moi: 'Cập nhật hồ sơ mới',
        bosung_hoso:      'Bổ sung hồ sơ',
        capnhat_chungchi: 'Cập nhật chứng chỉ',
        chinhsua_hoso:    'Chỉnh sửa hồ sơ',
        khac:             'Lý do khác'
      };
      const k = x.trim();
      if (MAP[k]) return MAP[k];
    }

    const maybe = maybeFormatDateLike(x);
    if (maybe) {
      const field = (window.currentRenderField || '').toLowerCase();
      if (field === 'deleted_at') {
        const d = new Date(x);
        if (!isNaN(d)) {
          const vn = new Intl.DateTimeFormat('vi-VN', {
            timeZone: 'Asia/Ho_Chi_Minh',
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
          }).format(d);
          return escapeHtml(vn);
        }
      }
      if (/^ngay_(nhan_hs|sinh)$/.test(field)) return escapeHtml(formatVNDateOnly(x));
      return escapeHtml(maybe);
    }

    if (typeof x === 'object') {
      return `<pre class="bg-white border border-dashed border-gray-200 rounded-lg p-2 overflow-auto text-xs">${escapeHtml(JSON.stringify(x, null, 2))}</pre>`;
    }
    return escapeHtml(String(x));
  }

  function diffKeysFiltered(prev={}, next={}){
    const ignore = new Set(['docs_before','docs_after','docs_diff']);
    const set = new Set([...Object.keys(prev||{}), ...Object.keys(next||{})]);
    const changes=[];
    set.forEach(k=>{
      if (ignore.has(k)) return;
      const a=(prev||{})[k]; const b=(next||{})[k];
      if (JSON.stringify(a)!==JSON.stringify(b)) changes.push({field:k, from:a, to:b});
    });
    return changes;
  }

  function snapshotGrid(obj, picks){
    const rows = (picks||[]).map(([label, key])=>{
      const v = obj ? obj[key] : null;
      return `
        <div class="bg-slate-50 font-semibold p-2">${escapeHtml(label)}</div>
        <div class="p-2">${cellValFor(key, v)}</div>`;
    }).join('');
    return `
      <div class="grid grid-cols-[220px_1fr] border border-gray-200 rounded-xl overflow-hidden">
        ${rows || '<div class="p-3 text-gray-500 col-span-2">Không có dữ liệu.</div>'}
      </div>`;
  }

  /* ====== Checklist name map cache ====== */
  let __NAME_MAP_CACHE = null;
  async function getChecklistNameMap(){
    if (__NAME_MAP_CACHE) return __NAME_MAP_CACHE;
    try{
      const r = await apiFetch('/checklist/active');
      if (r && r.ok){
        const j = await r.json();
        const map = {};
        const arr = Array.isArray(j?.items) ? j.items : (Array.isArray(j) ? j : []);
        arr.forEach(it => { if (it?.code) map[it.code] = it.display_name || it.name || it.code; });
        __NAME_MAP_CACHE = map;
        return map;
      }
    }catch(_){}
    __NAME_MAP_CACHE = {};
    return {};
  }

  let __VER_NAME_CACHE = {};
  async function getChecklistVersionName(id) {
    if (!id && id !== 0) return null;
    const key = String(id);
    if (__VER_NAME_CACHE[key]) return __VER_NAME_CACHE[key];
    try {
      const r = await apiFetch('/checklist/version/' + encodeURIComponent(key));
      if (r?.ok) {
        const j = await r.json().catch(() => null);
        const name = j?.display_name || j?.name || j?.title || j?.version_name || key;
        __VER_NAME_CACHE[key] = name;
        return name;
      }
    } catch (_) {}
    __VER_NAME_CACHE[key] = key;
    return key;
  }

  /* ====== Docs tables ====== */
  function renderDocsCurrentTable(docsObj={}, nameMap={}){
    const safe = (docsObj && typeof docsObj === 'object') ? docsObj : {};
    const entries = Object.entries(safe).map(([code, n])=>({ code, name: nameMap[code] || code, qty: Number(n)||0 }))
                                       .filter(x=>x.qty>0);
    if (!entries.length) return `<div class="text-gray-500">Không có danh mục hồ sơ.</div>`;
    entries.sort((a,b)=> a.name.localeCompare(b.name,'vi',{sensitivity:'base'}));
    return `
      <table class="w-full text-sm border border-gray-200 rounded-xl overflow-hidden">
        <thead class="bg-slate-50">
          <tr>
            <th class="p-2 text-left font-semibold text-gray-800">Tên danh mục</th>
            <th class="p-2 text-center font-semibold text-gray-800">Số lượng</th>
          </tr>
        </thead>
        <tbody>
          ${entries.map(x=>`
            <tr class="border-t">
              <td class="p-2 font-semibold text-gray-800">${escapeHtml(x.name)}</td>
              <td class="p-2 text-center">${escapeHtml(String(x.qty))}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  function renderDocsDiffTable(diffs=[], nameMap={}){
    if (!Array.isArray(diffs) && diffs && typeof diffs === 'object') {
      diffs = Object.entries(diffs).map(([code, v]) => {
        const from = Number(v?.from ?? 0);
        const to   = Number(v?.to   ?? (typeof v === 'number' ? v : 0));
        return { code, from, to };
      });
    }
    if (!Array.isArray(diffs) || diffs.length === 0) {
      return `<div class="text-gray-500">Không có thay đổi về danh mục hồ sơ.</div>`;
    }

    const rows = diffs.map(x=>{
      const delta = Number(x.to) - Number(x.from);
      const sign  = delta>0 ? '↑' : (delta<0 ? '↓' : '—');
      return { name: nameMap[x.code] || x.code, from: Number(x.from)||0, to: Number(x.to)||0, delta, sign };
    }).sort((a,b)=> a.name.localeCompare(b.name,'vi',{sensitivity:'base'}));

    return `
      <table class="w-full text-sm border border-gray-200 rounded-xl overflow-hidden">
        <thead class="bg-slate-50">
          <tr>
            <th class="p-2 text-left font-semibold text-gray-800">Tên danh mục</th>
            <th class="p-2 text-center font-semibold text-gray-800">Trước</th>
            <th class="p-2 text-center font-semibold text-gray-800">Sau</th>
            <th class="p-2 text-center font-semibold text-gray-800">±</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(r=>`
            <tr class="border-t">
              <td class="p-2 font-semibold text-gray-800">${escapeHtml(r.name)}</td>
              <td class="p-2 text-center">${escapeHtml(String(r.from))}</td>
              <td class="p-2 text-center">${escapeHtml(String(r.to))}</td>
              <td class="p-2 text-center">${r.sign} ${r.delta}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  /* ====== Batch (PRINT/EXPORT) detail ====== */
  function renderBatchActionDetail(d){
    const nv = (d?.new_values || {});
    const scope = nv.scope || '—';
    const filters = nv.filters || {};
    const nameMode = nv.name_mode || '—';
    const count = (typeof nv.count === 'number') ? nv.count : (d?.count ?? '—');
    

    const filterRows = Object.keys(filters).length
      ? Object.entries(filters).map(([k,v])=>`
          <div class="bg-slate-50 font-semibold p-2">${escapeHtml(String(k))}</div>
          <div class="p-2">${escapeHtml(String(v ?? ''))}</div>
        `).join('')
      : '<div class="p-3 text-gray-500 col-span-2">Không có bộ lọc.</div>';

    return `
      <h4 class="mt-1 mb-2 font-bold text-blue-800">Thông tin chung</h4>
      <div class="grid grid-cols-[220px_1fr] border border-gray-200 rounded-xl overflow-hidden">
        <div class="bg-slate-50 font-semibold p-2">Thời gian</div>     <div class="p-2">${cellValFor('occurred_at', d.occurred_at)}</div>
        <div class="bg-slate-50 font-semibold p-2">Người thao tác</div><div class="p-2">${escapeHtml(d.actor_name || d.actor_id || '—')}</div>
        <div class="bg-slate-50 font-semibold p-2">Hành động</div>     <div class="p-2">${escapeHtml(actionVi(d.action))}</div>
        <div class="bg-slate-50 font-semibold p-2">Trạng thái</div>    <div class="p-2">${escapeHtml(d.status || '')}</div>
        <div class="bg-slate-50 font-semibold p-2">Đường dẫn</div>     <div class="p-2">${escapeHtml(d.path || '')}</div>
        <div class="bg-slate-50 font-semibold p-2">Scope</div>         <div class="p-2">${escapeHtml(String(scope))}</div>
        <div class="bg-slate-50 font-semibold p-2">Name mode</div>     <div class="p-2">${escapeHtml(String(nameMode))}</div>
        <div class="bg-slate-50 font-semibold p-2">Số bản ghi</div>    <div class="p-2">${escapeHtml(String(count))}</div>
      </div>

      <h4 class="mt-6 mb-2 font-bold text-blue-800">Bộ lọc</h4>
      <div class="grid grid-cols-[220px_1fr] border border-gray-200 rounded-xl overflow-hidden">
        ${filterRows}
      </div>
    `;
  }

  function renderBatchUpdateDetail(d){
  // new_values từ server đang là { field: newValue, ... }
  const changes = (d?.new_values && typeof d.new_values === 'object') ? d.new_values : {};
  const rows = Object.entries(changes);

  const changesTable = rows.length
    ? `<table class="w-full text-sm border border-gray-200 rounded-xl overflow-hidden">
         <thead class="bg-slate-50">
           <tr>
             <th class="p-2 text-left font-semibold text-gray-800">Trường</th>
             <th class="p-2 text-left font-semibold text-gray-800">Giá trị mới</th>
           </tr>
         </thead>
         <tbody>
           ${rows.map(([k,v])=>`
             <tr class="border-t">
               <td class="p-2 font-semibold text-gray-800">${escapeHtml(getFieldLabel(k))}</td>
               <td class="p-2">${cellValFor(k, v)}</td>
             </tr>`).join('')}
         </tbody>
       </table>`
    : `<div class="text-gray-500 text-sm">Không thấy trường thay đổi.</div>`;

  return `
    <h4 class="mt-1 mb-2 font-bold text-blue-800">Thông tin chung</h4>
    <div class="grid grid-cols-[220px_1fr] border border-gray-200 rounded-xl overflow-hidden">
      <div class="bg-slate-50 font-semibold p-2">Thời gian</div>       <div class="p-2">${cellValFor('occurred_at', d.occurred_at)}</div>
      <div class="bg-slate-50 font-semibold p-2">Người thao tác</div>  <div class="p-2">${escapeHtml(d.actor_name || d.actor_id || '—')}</div>
      <div class="bg-slate-50 font-semibold p-2">Hành động</div>       <div class="p-2">${escapeHtml(actionVi(d.action))}</div>
      <div class="bg-slate-50 font-semibold p-2">Trạng thái</div>      <div class="p-2">${escapeHtml(d.status || '')}</div>
      <div class="bg-slate-50 font-semibold p-2">Đối tượng</div>       <div class="p-2">${escapeHtml(d.target_type || '—')}</div>
      <div class="bg-slate-50 font-semibold p-2">MSSV</div>            <div class="p-2">${escapeHtml(d.target_id || '—')}</div>
      <div class="bg-slate-50 font-semibold p-2">Correlation ID</div>  <div class="p-2">${escapeHtml(d.correlation_id || '—')}</div>
      <div class="bg-slate-50 font-semibold p-2">Đường dẫn</div>       <div class="p-2">${escapeHtml(d.path || '')}</div>
      <div class="bg-slate-50 font-semibold p-2">IP</div>              <div class="p-2">${escapeHtml(d.ip_address || '')}</div>
    </div>

    <h4 class="mt-6 mb-2 font-bold text-blue-800">Trường thay đổi</h4>
    ${changesTable}
  `;
}

  /* ====== OPEN DETAIL ====== */
  async function openDetail(id) {
    try {
      const r = await apiFetch('/journal/detail/' + id);
      if (!r || !r.ok) throw new Error('Không tải được chi tiết');
      const d = await r.json();
      state.currentLog = d;
      resetHardDeleteUI();

      // Label tiêu đề
      const label = d?.target_id ? `MSSV: ${String(d.target_id)}` : `STT: ${String(id)}`;
      $('#d_id').textContent = label;

      const btnOpenApplicant = document.getElementById('btnOpenApplicant');
      if (btnOpenApplicant) btnOpenApplicant.style.display = 'none';

      const action = String(d?.action || '').toUpperCase();
      const canTarget   = !!(d?.target_id);
      const isApplicant = (d?.target_type === 'Applicant');
      const isBatchLog  =
        (d?.target_type === 'ApplicantBatch') ||
        action === 'PRINT' || action === 'EXPORT' ||
        action === 'BATCH_UPDATE' || action === 'BATCH_UPDATE_PREVIEW';

      // Nút restore / hard-delete: ẩn cho batch logs
      const btnRestore    = document.getElementById('btnRestore');
      const btnHardDelete = document.getElementById('btnHardDelete');
      if (isBatchLog) {
        btnRestore.style.display = 'none';
        btnHardDelete.style.display = 'none';
        $('#d_id').textContent = `Log #${String(d.id)}`;

        if (action === 'BATCH_UPDATE' || action === 'BATCH_UPDATE_PREVIEW') {
          $('#d_view').innerHTML = renderBatchUpdateDetail(d);
        } else {
          // Giữ nguyên cho PRINT/EXPORT
          $('#d_view').innerHTML = renderBatchActionDetail(d);
        }

        $('#detail').style.display = 'flex';
        return;
      }
      // Tiếp tục cho Applicant logs
      const isHardDeleted      = (action === 'DELETE_HARD') || (d?.new_values?.hard_deleted === true);
      const isSoftDeleteAction = ['DELETE_SOFT', 'DELETE'].includes(action);

      const isObj  = (x) => x && typeof x === 'object' && !Array.isArray(x);
      const asObj  = (x) => (isObj(x) ? x : {});
      const prev   = asObj(d.prev_values);
      const next   = asObj(d.new_values);

      // Quyết định hiện nút Khôi phục
      btnRestore.style.display = 'none';
      btnRestore.disabled = false;
      btnRestore.title = '';

      const hasPrev = Object.keys(prev).length > 0;
      const restorableActions = new Set(['UPDATE', 'DELETE_SOFT', 'DELETE']);

      let purgedNow = isHardDeleted;
      if (!purgedNow && isSoftDeleteAction && d?.target_id) {
        purgedNow = await alreadyPurgedByLog(d.target_id);
      }

      const isRestorable = isApplicant && canTarget && !purgedNow && restorableActions.has(action) && hasPrev;
      if (isRestorable) {
        btnRestore.style.display = '';
      } else {
        btnRestore.style.display = '';
        btnRestore.disabled = true;
        btnRestore.title = purgedNow ? 'Dữ liệu đã bị xóa vĩnh viễn, không thể khôi phục.' : 'Không có dữ liệu cũ để khôi phục.';
      }

      // Nút "Xóa vĩnh viễn"
      const showHardDel = IS_ADMIN && isApplicant && canTarget && isSoftDeleteAction && !isHardDeleted && !purgedNow;
      btnHardDelete.style.display = showHardDel ? '' : 'none';

      // Render chi tiết
      const nameMap = await getChecklistNameMap();
      const isDeleteAction = ['DELETE_SOFT', 'DELETE', 'DELETE_HARD'].includes(action);

      const baseSnap = isDeleteAction ? prev : (Object.keys(next).length ? next : prev);

      const verId =
        next?.checklist_version_id ??
        prev?.checklist_version_id ??
        d?.checklist_version_id ?? null;

      const verName = await getChecklistVersionName(verId);

      const deletionMeta = {
        deleted_at:     next?.deleted_at     ?? d?.deleted_at     ?? baseSnap?.deleted_at     ?? null,
        deleted_by:     next?.deleted_by     ?? d?.deleted_by     ?? baseSnap?.deleted_by     ?? null,
        deleted_reason: next?.deleted_reason ?? d?.deleted_reason ?? baseSnap?.deleted_reason ?? null,
      };

      const snapshotForView = {
        ...baseSnap,
        checklist_version_name: verName || baseSnap?.checklist_version_name || null,
        ...deletionMeta
      };

      const asDict = (x) => (isObj(x) ? x : {});
      const docsBefore = asDict(prev.docs_before) || asDict(prev.docs);
      const docsAfter  = asDict(next.docs_after)  || asDict(next.docs);

      let docsDiff = Array.isArray(next.docs_diff)
        ? next.docs_diff
        : (Array.isArray(d.docs_diff) ? d.docs_diff : []);

      if (!Array.isArray(docsDiff) || docsDiff.length === 0) {
        const beforeKeys = Object.keys(docsBefore || {});
        const afterKeys  = Object.keys(docsAfter  || {});
        const all = new Set([...beforeKeys, ...afterKeys]);
        docsDiff = Array.from(all)
          .map(code => ({
            code,
            from: Number((docsBefore || {})[code] || 0),
            to:   Number((docsAfter  || {})[code]  || 0)
          }))
          .filter(x => x.from !== x.to);
      }

      const docsForView = isDeleteAction
        ? (Object.keys(docsBefore).length ? docsBefore : docsAfter)
        : (Object.keys(docsAfter).length  ? docsAfter  : docsBefore);

      const diffs = diffKeysFiltered(prev, next);

      const diffsResolved = await Promise.all(
        diffs.map(async (x) => {
          if (String(x.field) === 'checklist_version_id') {
            return {
              field: 'checklist_version_name',
              from: await getChecklistVersionName(x.from),
              to:   await getChecklistVersionName(x.to)
            };
          }
          return x;
        })
      );

      const infoHtml = `
        <h4 class="mt-1 mb-2 font-bold text-blue-800">Thông tin chung</h4>
        <div class="grid grid-cols-[220px_1fr] border border-gray-200 rounded-xl overflow-hidden">
          <div class="bg-slate-50 font-semibold p-2">Thời gian</div>     <div class="p-2">${cellValFor('occurred_at', d.occurred_at)}</div>
          <div class="bg-slate-50 font-semibold p-2">Người thao tác</div><div class="p-2">${escapeHtml(d.actor_name || d.actor_id || '—')}</div>
          <div class="bg-slate-50 font-semibold p-2">Hành động</div>     <div class="p-2">${escapeHtml(actionVi(d.action))}</div>
          <div class="bg-slate-50 font-semibold p-2">Trạng thái</div>    <div class="p-2">${escapeHtml(d.status || '')}</div>
          <div class="bg-slate-50 font-semibold p-2">Đối tượng (MSSV)</div><div class="p-2">${escapeHtml(d.target_id || '—')}</div>
          <div class="bg-slate-50 font-semibold p-2">Đường dẫn</div>     <div class="p-2">${escapeHtml(d.path || '')}</div>
          <div class="bg-slate-50 font-semibold p-2">IP</div>             <div class="p-2">${escapeHtml(d.ip_address || '')}</div>
          <div class="bg-slate-50 font-semibold p-2">Correlation ID</div><div class="p-2">${escapeHtml(d.correlation_id || '')}</div>
        </div>`;

      const currentPicks = [
        ["Mã hồ sơ","ma_ho_so"],
        ["Ngày nhận hồ sơ","ngay_nhan_hs"],
        ["Mã số học viên","ma_so_hv"],
        ["Họ tên","ho_ten"],
        ["Ngày sinh","ngay_sinh"],
        ["Giới tính","gioi_tinh"],
        ["Dân tộc","dan_toc"],
        ["Số điện thoại","so_dt"],
        ["Email học viên","email_hoc_vien"],
        ["Ngành nhập học","nganh_nhap_hoc"],
        ["Version danh mục","checklist_version_name"],
        ["Đợt","dot"],
        ["Khóa","khoa"],
        ["Đã TN trước đó","da_tn_truoc_do"],
        ["Ghi chú","ghi_chu"],
        ["Người nhận","nguoi_nhan_ky_ten"],
        ["Trạng thái","status"],
        ["Thời điểm xóa (UTC)","deleted_at"],
        ["Người xóa","deleted_by"],
        ["Lý do xóa","deleted_reason"]
      ];

      const snapshotTitle = isDeleteAction ? 'Dữ liệu trước khi xóa' : 'Dữ liệu hiện tại';
      window.currentRenderSection = 'snapshot';
      window.currentRenderField   = null;

      const currentHtml = `
        <h4 class="mt-6 mb-2 font-bold text-blue-800">${snapshotTitle}</h4>
        ${snapshotGrid(snapshotForView, currentPicks)}

        <h4 class="mt-6 mb-2 font-bold text-blue-800">Danh mục hồ sơ (${isDeleteAction ? 'trước khi xóa' : 'hiện tại'})</h4>
        ${renderDocsCurrentTable(docsForView, nameMap)}
      `;

      const diffsFiltered = diffsResolved.filter(x => !['ho_dem','ten','checklist_version_id'].includes(String(x.field)));
      const diffHtml = diffsFiltered.length
        ? `<h4 class="mt-6 mb-2 font-bold text-blue-800">Trường thay đổi</h4>
            <table class="w-full text-sm border border-gray-200 rounded-xl overflow-hidden">
              <thead class="bg-slate-50">
                <tr>
                  <th class="p-2 text-left">Trường</th>
                  <th class="p-2 text-left">Giá trị cũ</th>
                  <th class="p-2 text-left">Giá trị mới</th>
                </tr>
              </thead>
              <tbody>
                ${diffsFiltered.map(x => `
                  <tr class="border-t">
                    <td class="p-2 font-semibold">${escapeHtml(getFieldLabel(x.field))}</td>
                    <td class="p-2">${cellValFor(x.field, x.from)}</td>
                    <td class="p-2">${cellValFor(x.field, x.to)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>`
        : `<div class="text-gray-500 mt-4">Không có trường thay đổi.</div>`;

      const docsHtml = `
        <h4 class="mt-6 mb-2 font-bold text-blue-800">Danh mục hồ sơ thay đổi</h4>
        ${renderDocsDiffTable(docsDiff, nameMap)}
      `;

      $('#d_view').innerHTML = infoHtml + currentHtml + diffHtml + docsHtml;

      const isDel = ['DELETE','DELETE_SOFT'].includes(action);
      if (!(isDel && IS_ADMIN)) {
        $('#btnHardDelete').style.display = 'none';
      }

      $('#detail').style.display = 'flex';
    } catch (e) {
      showNoti('Không tải được chi tiết: ' + (e.message || 'unknown'), 'error');
    } finally {
      window.currentRenderSection = null;
      window.currentRenderField   = null;
    }
  }

  async function journalTrack({ action, target_type='ApplicantBatch', target_id=null, detail={} }) {
    try {
      const r = await apiFetch('/journal/track', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({
          action,
          target_type,
          target_id,
          detail, // <-- đổi tên key cho đẹp
        }),
      });
      return r?.ok;
    } catch { return false; }
  }

  // Helper: kiểm tra đã bị xóa vĩnh viễn chưa (dựa vào Journal)
  async function alreadyPurgedByLog(targetId){
    if (!targetId) return false;
    try {
      const qs = `action=DELETE_HARD&target_id=${encodeURIComponent(targetId)}&page=1&page_size=1&sort=occurred_at:desc`;
      const r = await apiFetch('/journal/?' + qs);
      if (!r || !r.ok) return false;
      const j = await r.json().catch(()=>null);
      const arr = Array.isArray(j?.items) ? j.items : (Array.isArray(j?.data) ? j.data : []);
      return Array.isArray(arr) && arr.length > 0;
    } catch(_) { return false; }
  }

  // Đóng modal bằng ESC và click ra ngoài
  (function bindDetailDismiss(){
    const overlay = document.getElementById('detail');
    overlay.addEventListener('click', (e)=> { if (e.target === overlay) overlay.style.display = 'none'; });
    document.addEventListener('keydown', (e)=>{ if (e.key === 'Escape' && overlay.style.display === 'flex') overlay.style.display = 'none'; });
  })();

  /* ====== Restore ====== */
  async function restore(){
    const log = state.currentLog;
    const logId = log?.id;
    const mssv  = log?.target_id || '—';
    if (!logId) return;

    const box = document.getElementById('confirmRestore');
    const yes = document.getElementById('btnConfirmRestoreYes');
    const no  = document.getElementById('btnConfirmRestoreNo');
    const lbl = document.getElementById('restoreMSSV');

    if (lbl) lbl.textContent = String(mssv);
    box.classList.remove('hidden');

    const closeBox = ()=> box.classList.add('hidden');

    const doRestore = async () => {
      closeBox();
      try{
        const r = await apiFetch('/journal/restore/' + logId, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:'{}'
        });
        if (!r) throw new Error('Không kết nối được máy chủ!');
        if (!r.ok){
          let msg = 'Khôi phục thất bại!', reason='';
          try{
            const ct = r.headers?.get?.('content-type') || '';
            if (ct.includes('application/json')){
              const dataErr = await r.json().catch(()=>null);
              if (dataErr){ reason=dataErr.reason||dataErr.code||''; if (dataErr.message) msg=dataErr.message; }
            }else{
              const t = await r.text().catch(()=> '');
              if (/hard[_\s-]?deleted/i.test(t)) reason='hard_deleted';
            }
          }catch(_){}
          if (r.status===410 || reason==='hard_deleted' || reason==='HARD_DELETED') msg='Dữ liệu đã bị xóa vĩnh viễn, không thể khôi phục!';
          else if (r.status===404) msg='Không tìm thấy dữ liệu để khôi phục.';
          throw new Error(msg);
        }

        let data = null;
        try {
          const ctOk = r.headers?.get?.('content-type') || '';
          if (ctOk.includes('application/json')) data = await r.json().catch(()=>null);
        } catch(_) {}

        showNoti(`Đã khôi phục cho MSSV ${mssv} từ thùng rác!`, 'success');
        document.getElementById('detail').style.display='none';

        const actionSel = document.getElementById('qActionSel');
        if (actionSel) actionSel.value = '';

        state.page = 1;
        grabFilters();
        load();

        try {
          const focusMssv = String(data?.item?.ma_so_hv || mssv || '');
          if (focusMssv) {
            try {
              const bc = new BroadcastChannel('app-events');
              bc.postMessage({ type:'APPLICANT_RESTORED', mssv: focusMssv, item: data?.item || null });
              bc.close?.();
            } catch(_) {}
            localStorage.setItem('restored.mssv', focusMssv);
          }
        } catch(_) {}

      }catch(e){
        showNoti('Lỗi khôi phục: ' + (e.message || 'unknown'), 'error');
      }finally{
        yes.removeEventListener('click', onYes);
        no.removeEventListener('click', onNo);
      }
    };

    const onYes = () => doRestore();
    const onNo  = () => {
      closeBox();
      yes.removeEventListener('click', onYes);
      no.removeEventListener('click', onNo);
    };

    yes.addEventListener('click', onYes, { once:true });
    no.addEventListener('click', onNo,   { once:true });
  };

  /* ====== Filters / UI ====== */
  function grabFilters(){
    state.filters = {
      q:$('#q').value.trim(), action:$('#qActionSel').value, id:$('#qId').value.trim(),
      actor:$('#qActor').value.trim(), from:$('#qFrom').value, to:$('#qTo').value
    };
    state.size = Number($('#pageSize').value)||20;
    localStorage.setItem('journal.pageSize', String(state.size));
  }

  function showNoti(msg, type="info", timeout=2500){
    let box = document.getElementById("notiBox");
    let inner = document.getElementById("notiInner");
    const colors={info:"bg-blue-600",success:"bg-green-600",warning:"bg-amber-600",error:"bg-rose-600"};
    inner.className = `px-6 py-3 rounded-xl shadow-xl text-white font-semibold text-center transition-all duration-300 scale-95 opacity-0 ${colors[type]||colors.info}`;
    inner.textContent = msg; box.classList.remove("hidden");
    requestAnimationFrame(()=>{ inner.classList.replace("scale-95","scale-100"); inner.classList.replace("opacity-0","opacity-100"); });
    setTimeout(()=>{ inner.classList.replace("scale-100","scale-95"); inner.classList.replace("opacity-100","opacity-0"); setTimeout(()=> box.classList.add("hidden"), 300); }, timeout);
  }

  const triggerSearch = debounce(()=>{ state.page=1; grabFilters(); load(); }, 300);
  $('#btnSearch').onclick = ()=>{ state.page=1; grabFilters(); load(); };
  $('#btnClear').onclick  = ()=>{ ['#q','#qType','#qId','#qActor','#qFrom','#qTo'].forEach(s=>$(s).value=''); $('#qActionSel').value=''; state.page=1; grabFilters(); load(); };
  ;['#q','#qType','#qId','#qActor','#qFrom','#qTo'].forEach(sel=>{
    $(sel).addEventListener('input', triggerSearch);
    $(sel).addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); state.page=1; grabFilters(); load(); } });
  });
  $('#qActionSel').addEventListener('change', triggerSearch);
  $('#pageSize').addEventListener('change', ()=>{ state.page=1; grabFilters(); load(); });

  function bindPager(container){
    container.querySelector('.pager-first').onclick = ()=>{ state.page=1; load(); };
    container.querySelector('.pager-prev').onclick  = ()=>{ if(state.page>1){ state.page--; load(); } };
    container.querySelector('.pager-next').onclick  = ()=>{ state.page++; load(); };
    container.querySelector('.pager-last').onclick  = ()=>{ state.page = pagesTotal(); load(); };
  }
  $$('.pager').forEach(bindPager);

  function bindSortHandlers(){
    $$('.th-sortable').forEach(th=>{
      const key = th.getAttribute('data-sort');
      const h = ()=> toggleSort(key);
      th.addEventListener('click', h);
      th.addEventListener('keydown', e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); h(); } });
    });
    setAriaSort();
  }

  $('#btnClose').onclick = ()=> $('#detail').style.display='none';
  $('#btnCopy').onclick  = ()=>{ if(!state.currentLog) return; const text = JSON.stringify(state.currentLog, null, 2); navigator.clipboard.writeText(text).then(()=> showNoti('Đã sao chép JSON chi tiết','success')); };
  $('#btnRestore').onclick = restore;

  /* ====== ROLE ====== */
  let CURRENT_ROLE = null;
  let IS_ADMIN = false;

  window.addEventListener('load', async ()=>{
    try {
      const meRes = await apiFetch('/me');
      if (meRes?.ok) {
        const me = await meRes.json();
        if (!['Admin','NhanVien'].includes(me.role)) { alert('Quyền tài khoản không được phép truy cập trang Nhật ký.'); location.href = '/students_list.html'; return; }
        CURRENT_ROLE = me.role || null; IS_ADMIN = CURRENT_ROLE === 'Admin';
        document.documentElement.dataset.role = CURRENT_ROLE;
        const helloNameEl = document.getElementById('helloName');
        const helloRoleEl = document.getElementById('helloRole');
        if (helloNameEl) helloNameEl.textContent = me.full_name || me.username || 'Người dùng';
        if (helloRoleEl) helloRoleEl.textContent = me.role || '';
      } else { location.href = '/login'; return; }
    } catch (_) { alert('Không kiểm tra được quyền truy cập.'); location.href = '/students_list.html'; return; }

    await detectPrefix();
    try { localStorage.removeItem('purged.mssv'); } catch(_) {}
    $('#pageSize').value = String(state.size);
    bindSortHandlers();
    grabFilters();
    load();
  });

  $('#apiBase').addEventListener('change', ()=>{ localStorage.setItem(STORAGE_KEY, $('#apiBase').value.trim()); });

  /* ====== Hard delete (Admin only) ====== */
  const btnHardDelete       = document.getElementById('btnHardDelete');
  const btnHardDeleteGo     = document.getElementById('btnHardDeleteGo');
  const btnHardDeleteCancel = document.getElementById('btnHardDeleteCancel');
  const hardDelBox          = document.getElementById('hardDelConfirm');

  const hardDelConfirmChk   = document.getElementById('hardDelConfirmChk');
  const hardDelReasonSel    = document.getElementById('hardDelReasonSel');
  const hardDelReasonWrap   = document.getElementById('hardDelReasonWrap');
  const hardDelReasonText   = document.getElementById('hardDelReasonText');

  function getHardDelReason() {
    const code = (hardDelReasonSel?.value || '').trim();
    if (!code) return { code: '', text: '' };
    if (code === 'OTHER') return { code, text: (hardDelReasonText?.value || '').trim() };
    const map = {
      TRUNG_LAP: 'Hồ sơ trùng lặp',
      NHAM_MSSV: 'Nhầm MSSV/mục tiêu',
      YEU_CAU_NGUOI_DUNG: 'Yêu cầu người dùng xóa dữ liệu',
      TEST_DATA: 'Dữ liệu thử nghiệm',
    };
    return { code, text: map[code] || code };
  }

  function updateHardDelOkState() {
    const confirmed = !!(hardDelConfirmChk?.checked);
    const code      = (hardDelReasonSel?.value || '');
    const needText  = (code === 'OTHER');
    const hasText   = (hardDelReasonText?.value || '').trim().length > 0;

    if (hardDelReasonWrap) hardDelReasonWrap.classList.toggle('hidden', !needText);

    const hasReason = code && (!needText || hasText);
    btnHardDeleteGo.disabled = !(confirmed && hasReason);
  }

  btnHardDelete.onclick = () => {
    if (!IS_ADMIN) { showNoti('Chỉ Admin mới được xóa vĩnh viễn.', 'error'); return; }
    if (hardDelConfirmChk)  hardDelConfirmChk.checked = false;
    if (hardDelReasonSel)   hardDelReasonSel.value = '';
    if (hardDelReasonText)  hardDelReasonText.value = '';
    if (hardDelReasonWrap)  hardDelReasonWrap.classList.add('hidden');

    hardDelBox.classList.remove('hidden');
    btnHardDeleteGo.classList.remove('hidden');
    btnHardDeleteCancel.classList.remove('hidden');
    updateHardDelOkState();
  };

  hardDelConfirmChk?.addEventListener('change', updateHardDelOkState);
  hardDelReasonSel?.addEventListener('change', updateHardDelOkState);
  hardDelReasonText?.addEventListener('input', updateHardDelOkState);

  btnHardDeleteCancel.onclick = () => {
    hardDelBox.classList.add('hidden');
    btnHardDeleteGo.classList.add('hidden');
    btnHardDeleteCancel.classList.add('hidden');
    if (hardDelConfirmChk) hardDelConfirmChk.checked = false;
    if (hardDelReasonSel)  hardDelReasonSel.value = '';
    if (hardDelReasonText) hardDelReasonText.value = '';
    if (hardDelReasonWrap) hardDelReasonWrap.classList.add('hidden');
    updateHardDelOkState();
  };

  async function doHardDelete() {
    const log = state.currentLog;
    if (!log) return;
    const { code, text } = getHardDelReason();
    try {
      const r = await apiFetch('/journal/hard-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          log_id: log.id,
          target_type: log.target_type,
          target_id: log.target_id,
          confirm: 'CONFIRM_DELETE',
          reason_code: code,
          reason: text,
        }),
      });
      if (!r) throw new Error('Không kết nối được máy chủ.');
      if (!r.ok) {
        let msg = `Hard-delete thất bại (HTTP ${r.status})`;
        try {
          const ct = r.headers?.get?.('content-type') || '';
          if (ct.includes('application/json')) {
            const j = await r.json().catch(() => null);
            if (j?.detail) msg = j.detail;
          } else {
            const t = await r.text().catch(() => '');
            if (t) msg = t;
          }
        } catch (_) {}
        showNoti(msg, 'error');
        return;
      }
      showNoti('Đã xóa vĩnh viễn!', 'success');
      btnHardDeleteCancel.click();
      document.getElementById('detail').style.display = 'none';
      load();
    } catch (e) {
      showNoti('Hard-delete lỗi: ' + (e.message || 'unknown'), 'error');
    }
  }

  btnHardDeleteGo.onclick = async () => {
    if (!IS_ADMIN) { showNoti('Chỉ Admin mới được xóa vĩnh viễn.', 'error'); return; }
    const log = state.currentLog; if (!log) return;
    if (!hardDelConfirmChk?.checked) { showNoti('Bạn chưa xác nhận xóa vĩnh viễn.', 'warning'); return; }
    const { code, text } = getHardDelReason();
    if (!code) { showNoti('Vui lòng chọn lý do xóa.', 'warning'); return; }
    if (code === 'OTHER' && !text) { showNoti('Vui lòng nhập lý do khác.', 'warning'); return; }

    const confirmBox = document.getElementById('confirmHardDel');
    const yesBtn = document.getElementById('btnConfirmHardDelYes');
    const noBtn  = document.getElementById('btnConfirmHardDelNo');

    if (!confirmBox || !yesBtn || !noBtn) {
      if (!window.confirm('Xác nhận xóa vĩnh viễn hồ sơ này?')) return;
      await doHardDelete();
      return;
    }

    confirmBox.classList.remove('hidden');
    const onNo = () => { confirmBox.classList.add('hidden'); };
    const onYes = async () => {
      confirmBox.classList.add('hidden');
      btnHardDeleteGo.disabled = true;
      await doHardDelete();
      btnHardDeleteGo.disabled = false;
      yesBtn.removeEventListener('click', onYes);
      noBtn.removeEventListener('click', onNo);
    };
    noBtn.addEventListener('click', onNo,  { once: true });
    yesBtn.addEventListener('click', onYes, { once: true });
  };

  function resetHardDeleteUI() {
    hardDelBox.classList.add('hidden');
    btnHardDeleteGo.classList.add('hidden');
    btnHardDeleteCancel.classList.add('hidden');
    const chk = document.getElementById('hardDelConfirmChk');
    if (chk) chk.checked = false;
    if (hardDelReasonSel) hardDelReasonSel.value = '';
    if (hardDelReasonText) hardDelReasonText.value = '';
    if (hardDelReasonWrap) hardDelReasonWrap.classList.add('hidden');
    btnHardDeleteGo.disabled = true;
  }

  /* ===== Dropdown user + Đăng xuất ===== */
  (function menuSetup(){
    const btn  = document.getElementById('userMenuBtn');
    const menu = document.getElementById('userMenu');
    const logoutBtn = document.getElementById('btnMenuLogout');
    if (!btn || !menu) return;

    function openMenu(on) {
      menu.classList.toggle('hidden', !on);
      btn.setAttribute('aria-expanded', String(on));
    }

    btn.addEventListener('click', (e)=>{
      e.stopPropagation();
      openMenu(menu.classList.contains('hidden'));
    });

    document.addEventListener('click', ()=>{
      if (!menu.classList.contains('hidden')) openMenu(false);
    });

    document.addEventListener('keydown', (e)=>{
      if (e.key === 'Escape') openMenu(false);
    });

    logoutBtn?.addEventListener('click', async ()=>{
      openMenu(false);
      try {
        await apiFetch('/logout', { method: 'POST' });
      } catch(_) {}
      location.href = '/auth_login.html';
    });
  })();

  (function () {
    const params = new URLSearchParams(location.search);
    const byQuery = params.get('expired') === '1';
    const byCookie = document.cookie.split(';').some(c => c.trim().startsWith('__session_expired=1'));
    if (byQuery || byCookie) {
      if (typeof showToast === 'function') {
        showToast('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.', 'warn', 4500);
      } else {
        alert('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.');
      }
      document.cookie = '__session_expired=; Max-Age=0; Path=/; SameSite=Lax';
    }
  })();
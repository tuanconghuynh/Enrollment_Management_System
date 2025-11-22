/* =========================
 *  AMS – Checklist Admin UI (safe DOM, DnD+Keyboard, focus trap, robust fetch)
 * ========================= */

/* ---------- Tiny DOM helper ---------- */
const el = (tag, attrs = {}, children = []) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') {
      n.className = v;
    } else if (k === 'dataset') {
      Object.assign(n.dataset, v);
    } else if (k.startsWith('on') && typeof v === 'function') {
      n[k] = v;
    } else if (k === 'text') {
      n.textContent = v ?? '';
    } else if (k === 'html') {
      n.innerHTML = v ?? ''; // cẩn thận XSS
    } else if (k === 'disabled' || k === 'checked' || k === 'readonly' || k === 'required') {
      // boolean attributes: chỉ set khi true
      if (v) n.setAttribute(k, '');
      // nếu false thì bỏ qua, KHÔNG setAttribute
    } else {
      n.setAttribute(k, v);
    }
  }

  (Array.isArray(children) ? children : [children]).forEach(c => {
    if (c == null) return;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return n;
};

/* ---------- Toast ---------- */
function showToast(msg, type='info', ms=2200){
  const wrap = document.getElementById('toast-wrap') || document.body.appendChild(el('div', {id:'toast-wrap'}));
  const box  = el('div', {class: 'toast ' + (type==='success'?'success':type==='warn'?'warn':type==='error'?'error':'' ) , text: String(msg||'')});
  wrap.appendChild(box);
  requestAnimationFrame(()=> box.classList.add('show'));
  const hide = () => {
    box.classList.remove('show');
    box.addEventListener('transitionend',()=>box.remove(),{once:true});
  };
  const timer = setTimeout(hide, ms);
  box.addEventListener('click', ()=>{ clearTimeout(timer); hide(); });
}

/* Giữ alias cũ để không phải sửa hết code bên dưới */
const toast = showToast;


/* ---------- API base & prefix detect + robust fetch with timeout ---------- */
const STORAGE_KEY = 'apiBase';
document.getElementById('apiBase').value = localStorage.getItem(STORAGE_KEY) || window.location.origin;
document.getElementById('apiBase').addEventListener('change', e => {
  localStorage.setItem(STORAGE_KEY, e.target.value.trim());
});

const apiBase = () => document.getElementById('apiBase').value.trim().replace(/\/+$/,'');
let API_PREFIX = ''; // '' hoặc '/api'
async function detectPrefix(){
  const base = apiBase();
  for (const p of ['', '/api']) {
    try {
      const r = await fetch(base + p + '/health', {credentials:'include'});
      if (r.ok) { API_PREFIX = p; return; }
    } catch {}
  }
  API_PREFIX = ''; // mặc định
}

function withTimeout(promise, ms=12000) {
  const ctl = new AbortController();
  const t = setTimeout(()=> ctl.abort('timeout'), ms);
  return Promise.race([
    promise(ctl.signal).finally(()=> clearTimeout(t)),
    new Promise((_, rej)=> setTimeout(()=> rej(new Error('timeout')), ms))
  ]);
}

async function apiFetch(path, init = {}) {
  const base = apiBase();
  const opts  = { credentials:'include', ...init };
  const tryOnce = async (prefix) => {
    try {
      const resp = await withTimeout((signal)=> fetch(base + prefix + path, {...opts, signal}));
      // bắt session hết hạn hoặc ép đổi mật khẩu
      if (resp && resp.status === 403) {
        try {
          const j = await resp.clone().json();
          if (j?.force_change) { location.href = '/account?first=1'; return null; }
        } catch {}
      }
      if (resp && resp.status === 401) {
        // redirect về login (đặt cookie flag để hiện toast ở trang sau)
        document.cookie = '__session_expired=1; Max-Age=30; Path=/; SameSite=Lax';
        location.href = '/auth_login.html?expired=1';
        return null;
      }
      return resp;
    } catch (e) {
      return null;
    }
  };

  let r = await tryOnce(API_PREFIX);
  if (r && r.status !== 404) return r;

  const alt = API_PREFIX === '' ? '/api' : '';
  r = await tryOnce(alt);
  if (r && r.ok) API_PREFIX = alt;
  return r;
}

async function showErrorFromResponse(r, fallback='Thao tác thất bại'){
  if (!r) return toast(fallback,'error');
  try {
    const ct = r.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      const j = await r.json().catch(()=>null);
      const msg = j?.detail || j?.message || j?.error;
      if (msg) return toast(msg, 'error');
    } else {
      const t = await r.text().catch(()=> '');
      if (t) return toast(t.slice(0,160), 'error');
    }
  } catch {}
  if (r.status === 409) return toast('Xung đột trạng thái (409).', 'error');
  if (r.status === 422) return toast('Dữ liệu không hợp lệ (422).', 'error');
  if (r.status === 429) return toast('Quá nhiều yêu cầu (429). Vui lòng thử lại sau.', 'error');
  toast(`${fallback} (HTTP ${r.status})`,'error');
}

/* ---------- Dropdown menu user (giống các trang khác) ---------- */
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
    openLogout();
  });
})();

/* ---------- Modal logout (dùng apiFetch) ---------- */
(function(){
  const wrap = document.getElementById('logoutModal');
  const box  = document.getElementById('logoutBox');
  const ok   = document.getElementById('lgOK');
  const cxl  = document.getElementById('lgCancel');
  const x    = document.getElementById('lgClose');
  let last=null;

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
  function trap(e){
    if(e.key!=='Tab') return;
    const f=box.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
    if(!f.length) return;
    const first=f[0], last=f[f.length-1];
    if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); }
  }

  window.openLogout=open;

  ok.addEventListener('click', async ()=>{
    try{ await apiFetch('/logout',{method:'POST'});}catch{}
    location.href='/auth_login.html';
  });
  cxl.addEventListener('click', close);
  x.addEventListener('click', close);
  wrap.addEventListener('click', e=>{ if(e.target===wrap) close(); });
  box.addEventListener('keydown', trap);
})();

/* ---------- Auth & role banner + fill sidebar name ---------- */
let IS_ADMIN = false;
async function ensureAdmin(){
  await detectPrefix();
  const r = await apiFetch('/me');
  if (!r || !r.ok) { 
    location.href = '/auth_login.html'; 
    return; 
  }
  const me = await r.json();

  // Gom hết role có thể có
  const rawRoles = [];

  // roles có thể là mảng hoặc string
  if (Array.isArray(me.roles)) {
    rawRoles.push(...me.roles);
  } else if (me.roles) {
    rawRoles.push(me.roles);
  }

  if (me.role) rawRoles.push(me.role);

  // ⚠️ Quan trọng: is_admin có thể là true, 1, "1"
  if (me.is_admin === true || me.is_admin === 1 || me.is_admin === '1') {
    rawRoles.push('Admin');
  }

  // Nếu rỗng thì cho default
  const roles = rawRoles.length ? rawRoles : ['User'];

  // Chuẩn hóa lower để check admin
  const rolesLower = roles.map(r => String(r).toLowerCase());

  IS_ADMIN = rolesLower.some(r =>
    r === 'admin' ||
    r === 'administrator' ||
    r.includes('admin')
  );

  console.log('[/me]', me, 'roles =', roles, 'IS_ADMIN =', IS_ADMIN);

  // Fill sidebar user info
  const name = me.full_name || me.username || 'Người dùng';
  const helloNameEl = document.getElementById('helloName');
  const helloRoleEl = document.getElementById('helloRole');
  if (helloNameEl) helloNameEl.textContent = name;
  if (helloRoleEl) helloRoleEl.textContent = roles.join(', ');

  const banner = document.getElementById('roleBanner');
  const t = document.getElementById('roleText');
  const controlIds = ['btnAdd','btnSaveOrder','btnCreateVer'];

  if (IS_ADMIN) {
    // Ẩn banner, bật nút
    if (banner) banner.classList.add('hidden');
    if (t) t.textContent = '';
    controlIds.forEach(id => { 
      const b = document.getElementById(id); 
      if (b) b.disabled = false; 
    });
  } else {
    if (banner) banner.classList.remove('hidden');
    if (t) {
      t.innerHTML = `Tài khoản <b>${name}</b> (<b>${roles.join(', ')}</b>) ` +
                    `<span class="text-rose-600 font-semibold">không có quyền chỉnh sửa</span>. Bạn chỉ được xem danh mục.`;
    }
    controlIds.forEach(id => { 
      const b = document.getElementById(id); 
      if (b) b.disabled = true; 
    });
  }
}

/* ---------- Versions ---------- */
let VERSIONS = [];
let ACTIVE_VERSION_ID = null;

const verWrap  = document.getElementById('verWrap');
const verName  = document.getElementById('verName');
const verClone = document.getElementById('verClone');
const verActivate = document.getElementById('verActivate');
const btnCreateVer = document.getElementById('btnCreateVer');
const activeVerChip = document.getElementById('activeVer');

function renderVersionsList(list){
  verWrap.innerHTML = '';
  if (!list.length) {
    verWrap.appendChild(el('div', {
      class: 'p-4 text-gray-500',
      text: 'Chưa có dữ liệu.'
    }));
    return;
  }

  list.forEach(v => {
    const isActive = (v.is_active === true) || (v.active === true) || (v.id === ACTIVE_VERSION_ID);

    const row = el('div', {
      class: 'px-4 py-3 flex items-center justify-between gap-2'
    }, [
      // Thông tin version
      el('div', { class: 'min-w-0' }, [
        el('div', { class: 'font-semibold', text: v.version_name || '' }),
        el('div', { class: 'text-xs text-gray-500' }, [
          'ID: ', String(v.id || ''),
          isActive ? ' • ' : '',
          isActive ? el('span', {
            class: 'text-green-700 font-semibold',
            text: 'Đang hoạt động'
          }) : ''
        ])
      ]),

      // Các nút thao tác
      el('div', { class: 'shrink-0 flex items-center gap-2' }, [
        // Xem
        el('button', {
          class: 'btn btn-outline btn-xs',
          type: 'button',
          onclick: () => handleViewVersion(v.id)
        }, 'Xem'),

        // Kích hoạt
        el('button', {
          class: 'btn btn-outline btn-xs',
          type: 'button',
          disabled: isActive || !IS_ADMIN,
          onclick: () => handleActivateVersion(v.id)
        }, 'Kích hoạt'),

        // Xóa
        el('button', {
          class: 'btn btn-outline btn-xs border-rose-600 text-rose-600 hover:bg-rose-600 hover:text-white',
          type: 'button',
          disabled: isActive || !IS_ADMIN,
          onclick: () => handleDeleteVersion(v.id)
        }, 'Xóa')
      ])
    ]);

    verWrap.appendChild(row);
  });
}

function handleViewVersion(id) {
  if (!id) return;
  // debug cho chắc
  console.log('view version', id);
  openViewModal(Number(id));
}

async function handleActivateVersion(id) {
  if (!IS_ADMIN) {
    toast('Bạn không có quyền kích hoạt phiên bản.', 'error');
    return;
  }
  id = Number(id);
  if (!id) return;

  console.log('activate version', id);
  const btnText = 'Kích hoạt version';

  const r = await apiFetch(`/checklist/versions/${id}/activate`, { method: 'POST' });
  if (!r || !r.ok) {
    if (r && r.status === 400) {
      toast(`Không thể kích hoạt: thiếu cột 'active'/'is_active'`, 'error');
    } else {
      await showErrorFromResponse(r, 'Kích hoạt thất bại');
    }
  } else {
    toast('Đã kích hoạt version', 'success');
    await loadVersions();
    await loadItems();
  }
}

async function handleDeleteVersion(id) {
  if (!IS_ADMIN) {
    toast('Bạn không có quyền xóa phiên bản.', 'error');
    return;
  }
  id = Number(id);
  if (!id) return;

  if (!confirm(`Xóa phiên bản ID ${id}?`)) return;

  console.log('delete version', id);
  const r = await apiFetch(`/checklist/versions/${id}`, { method: 'DELETE' });
  if (!r || !r.ok) {
    await showErrorFromResponse(r, 'Xóa phiên bản thất bại');
  } else {
    toast('Đã xóa phiên bản', 'success');
    await loadVersions();
    await loadItems();
  }
}

async function loadVersions(){
  // active
  {
    const r = await apiFetch('/checklist/active');
    if (!r || !r.ok) { toast('Không tải được version active','error'); return; }
    const j = await r.json();
    ACTIVE_VERSION_ID = j.version_id;
    activeVerChip.textContent = j.version_name || '—';
  }
  // list
  {
    const r = await apiFetch('/checklist/versions');
    VERSIONS = (r && r.ok) ? await r.json() : [];
    renderVersionsList(VERSIONS);

    // clone select
    verClone.innerHTML = '';
    verClone.appendChild(el('option', {value:'active', text:'Version đang active'}));
    VERSIONS.forEach(v => {
      verClone.appendChild(el('option', {value:String(v.id), text: `${v.version_name} (id ${v.id})`}));
    });
  }
}

btnCreateVer.addEventListener('click', async ()=>{
  if (!IS_ADMIN) return;
  const name = verName.value.trim();
  if (!name) { toast('Nhập tên phiên bản','warn'); verName.focus(); return; }
  btnCreateVer.disabled = true;
  const payload = { version_name: name, clone_from: verClone.value || 'active', activate: !!verActivate.checked };
  const r = await apiFetch('/checklist/versions', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
  });
  if (!r || !r.ok) { await showErrorFromResponse(r,'Tạo version thất bại'); }
  else {
    verName.value = ''; verActivate.checked = false;
    toast('Đã tạo version mới','success'); await loadVersions(); await loadItems();
  }
  btnCreateVer.disabled = false;
});

/* ---------- Items (active) + reorder ---------- */
let ITEMS = [];
let DIRTY_ORDER = false;

const tbody = document.getElementById('tbody');
const btnAdd = document.getElementById('btnAdd');
const btnSaveOrder = document.getElementById('btnSaveOrder');
const emptyHint = document.getElementById('empty');

function setDirty(on){
  DIRTY_ORDER = !!on;
  btnSaveOrder.disabled = !IS_ADMIN || !DIRTY_ORDER;
}

window.addEventListener('beforeunload', (e)=>{
  if (DIRTY_ORDER) { e.preventDefault(); e.returnValue = ''; }
});

async function loadItems(){
  const r = await apiFetch('/checklist/active');
  if (!r || !r.ok) {
    tbody.innerHTML=''; emptyHint.classList.remove('hidden');
    toast('Không tải được danh mục active','error'); return;
  }
  const j = await r.json();
  ITEMS = (j.items||[]).slice().sort((a,b)=>{
    const ga = a.order_index ?? a.order_no ?? 0;
    const gb = b.order_index ?? b.order_no ?? 0;
    return ga - gb;
  });
  activeVerChip.textContent = j.version_name || '—';
  ACTIVE_VERSION_ID = j.version_id || ACTIVE_VERSION_ID;
  renderItems();
  setDirty(false);
}

function rowTemplate(it, idx){
  const tr = el('tr', {'data-code': it.code});
  // #
  tr.appendChild(el('td', {class:'text-center select-none'}, String(idx+1)));
  // handle
  const handle = el('span', {
    class:`handle inline-flex items-center justify-center w-8 h-8 rounded-lg border hover:bg-slate-50 ${IS_ADMIN?'':'opacity-40'}`,
    title:'Kéo để sắp xếp', draggable: IS_ADMIN ? 'true' : 'false', role:'button', tabindex: IS_ADMIN ? '0' : '-1', 'aria-label':'Kéo để sắp xếp'
  }, '☰');
  tr.appendChild(el('td', {class:'text-left'}, handle));
  // code
  tr.appendChild(el('td', {class:'font-mono'}, it.code || ''));
  // name
  tr.appendChild(el('td', {}, it.display_name || ''));
  // order
  tr.appendChild(el('td', {class:'text-center text-gray-500'}, `${idx+1}/${ITEMS.length}`));
  // actions
  const upBtn   = el('button', {class:'btn btn-outline btn-xs act-up',   dataset:{i:String(idx)}, disabled:!IS_ADMIN}, '↑');
  const downBtn = el('button', {class:'btn btn-outline btn-xs act-down', dataset:{i:String(idx)}, disabled:!IS_ADMIN}, '↓');
  const editBtn = el('button', {class:'btn btn-outline btn-xs act-edit', dataset:{code:it.code}, disabled:!IS_ADMIN}, 'Sửa');
  const delBtn  = el('button', {class:'btn btn-outline btn-xs border-rose-600 text-rose-600 hover:bg-rose-600 hover:text-white act-del', dataset:{code:it.code}, disabled:!IS_ADMIN}, 'Xóa');
  tr.appendChild(el('td', {class:'text-right'}, el('div', {class:'inline-flex gap-2'}, [upBtn,downBtn,editBtn,delBtn])));

  // keyboard reorder (focus on handle)
  if (IS_ADMIN) {
    handle.addEventListener('keydown', (e)=>{
      const i = Array.from(tbody.children).indexOf(tr);
      if (i < 0) return;
      if (['ArrowUp','ArrowDown','Home','End'].includes(e.key)) e.preventDefault();
      if (e.key === 'ArrowUp' && i>0)          swapItems(i, i-1);
      if (e.key === 'ArrowDown' && i<ITEMS.length-1) swapItems(i, i+1);
      if (e.key === 'Home') swapItems(i, 0);
      if (e.key === 'End')  swapItems(i, ITEMS.length-1);
    });
  }

  // DnD
  if (IS_ADMIN) {
    handle.addEventListener('dragstart', (e)=> {
      tr.classList.add('dragging');
      e.dataTransfer?.setData('text/plain', it.code || '');
      e.dataTransfer?.setDragImage?.(tr, 20, 10);
    });
    handle.addEventListener('dragend', ()=> tr.classList.remove('dragging'));
    tr.addEventListener('dragover', (e)=>{
      const dragging = tbody.querySelector('tr.dragging');
      if (!dragging) return;
      e.preventDefault();
      const rect = tr.getBoundingClientRect();
      const after = (e.clientY - rect.top) > rect.height/2;
      if (after) tr.after(dragging); else tr.before(dragging);
    });
    tr.addEventListener('drop', (e)=>{ e.preventDefault(); rebuildItemsFromDOM(); setDirty(true); });
  }

  return tr;
}

function renderItems(){
  tbody.innerHTML = '';
  if (!ITEMS.length){ emptyHint.classList.remove('hidden'); return; }
  emptyHint.classList.add('hidden');

  ITEMS.forEach((it, idx)=> tbody.appendChild(rowTemplate(it, idx)));

  tbody.querySelectorAll('.act-up').forEach(b=> b.addEventListener('click', ()=>{
    const i = +b.dataset.i;
    if (i>0) { swapItems(i, i-1); }
  }));
  tbody.querySelectorAll('.act-down').forEach(b=> b.addEventListener('click', ()=>{
    const i = +b.dataset.i;
    if (i<ITEMS.length-1) { swapItems(i, i+1); }
  }));
  tbody.querySelectorAll('.act-edit').forEach(b=> b.addEventListener('click', ()=> openModalChecklist('edit', b.dataset.code)));
  tbody.querySelectorAll('.act-del').forEach(b=> b.addEventListener('click', ()=> onDelete(b.dataset.code)));
}

function swapItems(i, j){
  [ITEMS[i], ITEMS[j]] = [ITEMS[j], ITEMS[i]];
  renderItems();
  setDirty(true);
  // focus lại vào handle của hàng vừa di chuyển
  const targetRow = tbody.children[j];
  targetRow?.querySelector('.handle')?.focus();
}

function rebuildItemsFromDOM(){
  const codes = [...tbody.querySelectorAll('tr')].map(tr=> tr.dataset.code);
  const map = Object.fromEntries(ITEMS.map(x=>[x.code, x]));
  ITEMS = codes.map(c=> map[c]).filter(Boolean);
  renderItems();
}

async function onDelete(code){
  if (!IS_ADMIN) return;
  if (DIRTY_ORDER && !confirm('Bạn đang thay đổi thứ tự chưa lưu. Vẫn tiếp tục xoá?')) return;
  if (!confirm(`Xóa mục '${code}' ?`)) return;
  const r = await apiFetch(`/checklist/items/${encodeURIComponent(code)}`, {method:'DELETE'});
  if (!r || !r.ok){ await showErrorFromResponse(r,'Xóa thất bại'); return; }
  toast('Đã xóa','success');
  await loadItems();
}

btnSaveOrder.addEventListener('click', async ()=>{
  if (!IS_ADMIN) return;
  const codes = [...tbody.querySelectorAll('tr')].map(tr=> tr.dataset.code);
  const r = await apiFetch('/checklist/reorder', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ codes })
  });
  if (!r || !r.ok){ await showErrorFromResponse(r,'Lưu thứ tự thất bại'); return; }
  toast('Đã lưu thứ tự','success');
  setDirty(false);
  await loadItems();
});

document.getElementById('btnAdd').addEventListener('click', ()=> openModalChecklist('add'));

/* ---------- Modal Add/Edit (focus trap + backdrop + ESC) ---------- */
const modalChecklist = document.getElementById('modal');
const btnClose = document.getElementById('btnClose');
const btnCancel = document.getElementById('btnCancel');
const btnOk = document.getElementById('btnOk');
const inpCode = document.getElementById('inpCode');
const inpName = document.getElementById('inpName');
const rowCode = document.getElementById('rowCode');
const modalTitle = document.getElementById('modalTitle');

let MODAL_MODE = 'add', MODAL_CODE = null;
let lastFocusedBeforeModal = null;

function trapFocus(container, e){
  const focusables = container.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  const list = Array.from(focusables).filter(el=> !el.hasAttribute('disabled'));
  if (list.length === 0) return;
  const first = list[0], last = list[list.length-1];
  if (e.key !== 'Tab') return;
  if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
  else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
}

function openModalChecklist(mode, code=null){
  if (!IS_ADMIN) return;
  MODAL_MODE = mode; MODAL_CODE = code;
  lastFocusedBeforeModal = document.activeElement;

  document.body.style.overflow = 'hidden';
  modalChecklist.classList.add('show'); modalChecklist.setAttribute('aria-hidden','false');

  modalTitle.textContent = mode === 'add' ? 'Thêm mục danh mục' : 'Sửa mục danh mục';
  rowCode.style.display = (mode === 'add') ? '' : 'none';
  inpCode.value = ''; inpName.value = '';

  if (mode === 'edit') {
    const it = ITEMS.find(x=> x.code === code);
    inpName.value = it?.display_name || '';
  }

  setTimeout(()=> (mode==='add'? inpCode : inpName).focus(), 50);
}

function closeModalChecklist(){
  modalChecklist.classList.remove('show'); modalChecklist.setAttribute('aria-hidden','true');
  document.body.style.overflow = '';
  lastFocusedBeforeModal?.focus?.();
}
btnClose.addEventListener('click', closeModalChecklist);
btnCancel.addEventListener('click', closeModalChecklist);
modalChecklist.addEventListener('click', (e)=>{ if (e.target === modalChecklist) closeModalChecklist(); });
modalChecklist.addEventListener('keydown', (e)=>{ if (e.key === 'Escape') closeModalChecklist(); trapFocus(modalChecklist, e); });

btnOk.addEventListener('click', async ()=>{
  if (MODAL_MODE === 'add'){
    const c = inpCode.value.trim();
    const n = inpName.value.trim();
    if (!/^[a-z0-9_]+$/.test(c)) { toast('Mã (code) chỉ gồm chữ thường, số, gạch dưới','warn'); return; }
    if (!n) { toast('Nhập tên hiển thị','warn'); return; }
    btnOk.disabled = true;
    const r = await apiFetch('/checklist/items', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ code:c, display_name:n }) });
    btnOk.disabled = false;
    if (!r || !r.ok){ await showErrorFromResponse(r,'Thêm thất bại'); return; }
    toast('Đã thêm','success'); closeModalChecklist(); await loadItems();
  } else {
    const n = inpName.value.trim();
    if (!n) { toast('Nhập tên hiển thị','warn'); return; }
    btnOk.disabled = true;
    const r = await apiFetch(`/checklist/items/${encodeURIComponent(MODAL_CODE)}`, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ display_name:n }) });
    btnOk.disabled = false;
    if (!r || !r.ok){ await showErrorFromResponse(r,'Cập nhật thất bại'); return; }
    toast('Đã cập nhật','success'); closeModalChecklist(); await loadItems();
  }
});

/* ---------- Modal xem phiên bản bất kỳ ---------- */
const modalView = document.getElementById('modalViewVer');
const viewTitle = document.getElementById('viewTitle');
const viewMeta  = document.getElementById('viewMeta');
const viewBody  = document.getElementById('viewBody');
const btnCloseView  = document.getElementById('btnCloseView');
const btnCloseView2 = document.getElementById('btnCloseView2');

let lastFocusView = null;
async function openViewModal(versionId){
  lastFocusView = document.activeElement;
  document.body.style.overflow = 'hidden';
  modalView.classList.add('show'); modalView.setAttribute('aria-hidden','false');

  viewTitle.textContent = `Phiên bản #${versionId}`;
  viewMeta.textContent  = 'Đang tải...';
  viewBody.innerHTML    = '';

  const r = await apiFetch(`/checklist/versions/${versionId}/items`);
  if (!r || !r.ok){ await showErrorFromResponse(r,'Không tải được phiên bản'); closeViewModal(); return; }
  const j = await r.json();
  viewTitle.textContent = `Phiên bản: ${j.version_name} (ID ${j.version_id})`;
  viewMeta.innerHTML = (j.is_active ? '<span class="text-green-700 font-semibold">Đang hoạt động</span>' : '<span class="text-gray-600">Không hoạt động</span>');

  const arr = (j.items||[]).slice().sort((a,b)=>{
    const ga = a.order_index ?? a.order_no ?? 0;
    const gb = b.order_index ?? b.order_no ?? 0;
    return ga - gb;
  });

  viewBody.innerHTML = '';
  if (!arr.length){
    viewBody.appendChild(el('tr',{}, el('td',{colspan:'4',class:'text-center text-gray-500 py-4',text:'Trống'})));
  } else {
    const frag = document.createDocumentFragment();
    arr.forEach((it, idx)=>{
      const tr = el('tr');
      tr.appendChild(el('td', {class:'text-center'}, String(idx+1)));
      tr.appendChild(el('td', {class:'font-mono'}, it.code || ''));
      tr.appendChild(el('td', {}, it.display_name || ''));
      tr.appendChild(el('td', {class:'text-center'}, String(it.order_index ?? it.order_no ?? (idx+1))));
      frag.appendChild(tr);
    });
    viewBody.appendChild(frag);
  }
}

function closeViewModal(){
  modalView.classList.remove('show'); modalView.setAttribute('aria-hidden','true');
  document.body.style.overflow = '';
  lastFocusView?.focus?.();
}
btnCloseView.addEventListener('click', closeViewModal);
btnCloseView2.addEventListener('click', closeViewModal);
modalView.addEventListener('click', (e)=>{ if (e.target === modalView) closeViewModal(); });
modalView.addEventListener('keydown', (e)=>{ if (e.key === 'Escape') closeViewModal(); trapFocus(modalView, e); });

/* ---------- Boot ---------- */
window.addEventListener('load', async ()=>{
  await ensureAdmin();
  await loadVersions();
  await loadItems();
});

/* ---------- Session expired toast (giữ nguyên behavior cũ) ---------- */
(function () {
  const params = new URLSearchParams(location.search);
  const byQuery = params.get('expired') === '1';
  const byCookie = document.cookie.split(';').some(c => c.trim().startsWith('__session_expired=1'));
  if (byQuery || byCookie) {
    if (typeof showToast === 'function') {
      showToast('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.', 'warn', 4500);
    } else {
      toast('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.', 'warn', 4500);
    }
    document.cookie = '__session_expired=; Max-Age=0; Path=/; SameSite=Lax';
  }
})();
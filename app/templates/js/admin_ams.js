/* ===== Helpers API (chung toàn hệ thống) ===== */
async function api(path, opt = {}) {
  try {
    return await fetch('/api' + path, { credentials:'include', ...opt });
  } catch (e) {
    console.error('API error:', e);
    return null;
  }
}

/* ===== Toast helper (dùng chung, khớp style.css) ===== */
function showToast(msg, type='info', ms=3200){
  const wrap=document.getElementById('toast-wrap'); if(!wrap) return alert(msg);
  const el=document.createElement('div');
  el.className=`toast ${type}`;
  el.textContent=String(msg);
  wrap.appendChild(el);
  requestAnimationFrame(()=>el.classList.add('show'));
  const close=()=>{
    el.classList.remove('show');
    el.addEventListener('transitionend',()=>el.remove(),{once:true});
  };
  const t=setTimeout(close,ms);
  el.addEventListener('click',()=>{clearTimeout(t); close();});
}

/* ===== Dropdown menu user (giống trang chủ) ===== */
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

/* ===== Modal logout (chung, giống trang chủ) ===== */
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
    try{ await api('/logout',{method:'POST'});}catch{}
    location.href='/auth_login.html';
  });
  cxl.addEventListener('click', close);
  x.addEventListener('click', close);
  wrap.addEventListener('click', e=>{ if(e.target===wrap) close(); });
  box.addEventListener('keydown', trap);
})();

/* ===== Boot: load /me cho sidebar ===== */
async function boot(){
  const r = await api('/me');
  if (!r || !r.ok) { location.href = '/auth_login.html'; return; }
  const me = await r.json();
  const name = me.full_name || me.username || 'Người dùng';
  (document.getElementById('helloName')||{}).textContent = name;
  (document.getElementById('helloRole')||{}).textContent = me.role || '';
}
boot();

/* ========= Helpers format thời gian theo VN ========= */
function parseToDate(raw) {
  if (!raw) return null;
  let s = String(raw).trim();
  if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/.test(s)) s = s.replace(' ', 'T');
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?)?(Z|[+\-]\d{2}:?\d{2})?$/);
  if (m) {
    const [_, Y, M, D, h='00', mi='00', se='00', ms='0', tz] = m;
    if (!tz) return new Date(Date.UTC(+Y, +M-1, +D, +h, +mi, +se, +ms));
    return new Date(s);
  }
  const d = new Date(s);
  return isNaN(d) ? null : d;
}
function toVNDateText(raw) {
  if (!raw) return '—';
  const only = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (only) {
    const d = new Date(Date.UTC(+only[1], +only[2]-1, +only[3]));
    return new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      day:'2-digit', month:'2-digit', year:'numeric'
    }).format(d);
  }
  const d = parseToDate(raw); if (!d) return raw;
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    day:'2-digit', month:'2-digit', year:'numeric'
  }).format(d);
}
function toVNDateTimeText(raw) {
  if (!raw) return '—';
  const d = parseToDate(raw); if (!d) return raw;
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    day:'2-digit', month:'2-digit', year:'numeric',
    hour:'2-digit', minute:'2-digit', second:'2-digit'
  }).format(d).replace(',', '');
}
function formatVNDate(selector='[data-dateonly]') {
  document.querySelectorAll(selector).forEach(el => {
    const raw = (el.textContent || '').trim();
    if (!raw || raw === '—') return;
    el.textContent = toVNDateText(raw);
  });
}

/* ========= Toggle hiện/ẩn mật khẩu ========= */
document.querySelectorAll('[data-toggle-eye]').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    const input = document.querySelector(btn.getAttribute('data-toggle-eye'));
    if (!input) return;
    input.type = (input.type === 'password') ? 'text' : 'password';
    btn.textContent = (input.type === 'password') ? '👁️' : '🙈';
  });
});

/* ========= Modal View/Edit user + trap focus ========= */
const modal = document.getElementById('editUserModal');
const modalBox = document.getElementById('editUserBox');
let lastActiveEl = null;

function openModal() {
  lastActiveEl = document.activeElement;
  modal.classList.add('show');
  requestAnimationFrame(()=> modalBox.focus());
  document.body.classList.add('overflow-hidden');
}
function closeModal() {
  modal.classList.remove('show');
  document.body.classList.remove('overflow-hidden');
  lastActiveEl && lastActiveEl.focus?.();
}
function trapFocus(e){
  if (e.key !== 'Tab') return;
  const f = modalBox.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

document.getElementById('e_cancel')?.addEventListener('click', closeModal);
document.getElementById('e_cancel_top')?.addEventListener('click', closeModal);
modal.addEventListener('click', e=>{ if(e.target.id==='editUserModal') closeModal(); });
modalBox.addEventListener('keydown', trapFocus);

/* ========= Gắn dữ liệu vào modal từ data-* ========= */
function boolLikeTrue(v){ return v===true || v===1 || v==='1' || String(v).toLowerCase()==='true'; }
function safeSubDate(s){ return (s||'').substring(0,10); }

document.querySelectorAll('button[data-id]').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    const g = a => (btn.getAttribute(a) || '');
    document.getElementById('e_id').value         = g('data-id');
    document.getElementById('e_username').value   = g('data-username');
    document.getElementById('e_full_name').value  = g('data_full_name') || g('data-full_name');
    document.getElementById('e_email').value      = g('data-email');
    document.getElementById('e_dob').value        = safeSubDate(g('data-dob'));
    document.getElementById('e_role').value       = g('data-role') || 'CongTacVien';
    document.getElementById('e_is_active').checked= boolLikeTrue(g('data-is_active'));
    document.getElementById('e_last_login').value = toVNDateTimeText(g('data-last_login_at'));
    document.getElementById('e_pw_changed').value = toVNDateTimeText(g('data-password_changed_at'));
    document.getElementById('rp_id').value        = g('data-id');
    document.getElementById('rp_new').value       = '';
    openModal();
  });
});

/* ========= Tìm kiếm nhanh & lọc role ========= */
(function bindSearchFilter(){
  const q = document.getElementById('q');
  const roleSel = document.getElementById('roleFilter');
  const rows = Array.from(document.querySelectorAll('#userTable tbody tr'));
  function apply(){
    const keyword = (q.value||'').trim().toLowerCase();
    const role = roleSel.value;
    rows.forEach(tr=>{
      const u = (tr.dataset.username || '').toLowerCase();
      const f = (tr.dataset.fullname||'').toLowerCase();
      const r = tr.dataset.role;
      const okK = !keyword || u.includes(keyword) || f.includes(keyword);
      const okR = !role || r === role;
      tr.classList.toggle('hidden', !(okK && okR));
    });
  }
  q.addEventListener('input', apply);
  roleSel.addEventListener('change', apply);
})();

/* ========= Submit form: tạo user ========= */
(function(){
  const form = document.getElementById('createForm');
  if(!form) return;
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const old = btn?.innerHTML;
    if (btn) { btn.disabled = true; btn.innerHTML = 'Đang tạo…'; }
    try{
      const fd = new FormData(form);
      const r = await fetch(form.action, { method:'POST', body: fd, credentials:'include' });
      let data = null;
      const ct = r.headers.get('content-type')||'';
      if (ct.includes('application/json')) { try{ data = await r.json(); }catch{} }
      else { try{ const t = await r.text(); data = t ? JSON.parse(t) : null; }catch{} }

      if (r.ok) {
        showToast('Tạo tài khoản thành công ✅','success',2200);
        form.reset();
        setTimeout(()=> location.reload(), 900);
      } else {
        const msg = (data && (data.detail || data.message)) || (r.status===409?'Username/Email đã tồn tại':'Lỗi tạo tài khoản');
        showToast(`${msg} (HTTP ${r.status})`,'error',4200);
      }
    }catch(err){
      showToast('Không kết nối được máy chủ. Vui lòng thử lại.','error',3500);
    }finally{
      if (btn) { btn.disabled = false; btn.innerHTML = old || 'Tạo mới'; }
    }
  });
})();

/* ========= Submit form: cập nhật user trong modal ========= */
(function(){
  const form = document.getElementById('updateForm');
  if(!form) return;
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const btn = document.getElementById('e_save');
    const old = btn?.innerHTML;
    if (btn) { btn.disabled = true; btn.innerHTML = 'Đang lưu…'; }
    try{
      const fd = new FormData(form);
      const r = await fetch(form.action, { method:'POST', body: fd, credentials:'include' });
      let data = null;
      const ct = r.headers.get('content-type')||'';
      if (ct.includes('application/json')) { try{ data = await r.json(); }catch{} }
      else { try{ const t = await r.text(); data = t ? JSON.parse(t) : null; }catch{} }

      if (r.ok) {
        showToast('Cập nhật thành công ✅','success',2400);
        closeModal();
        setTimeout(()=> location.reload(), 900);
      } else {
        const msg = (data && (data.detail || data.message)) || `Lỗi cập nhật (HTTP ${r.status})`;
        showToast(msg,'error',4200);
      }
    }catch(err){
      showToast('Không kết nối được máy chủ. Vui lòng thử lại.','error',3800);
    }finally{
      if (btn) { btn.disabled = false; btn.innerHTML = old || 'Lưu thay đổi'; }
    }
  });
})();

/* ========= Format cột ngày sinh trong bảng ========= */
window.addEventListener('DOMContentLoaded', () => {
  formatVNDate('[data-dateonly]');
});

/* ========= Thông báo hết hạn phiên ========= */
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

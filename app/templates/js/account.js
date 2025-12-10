/* ===== Helpers chung (giống trang chủ, bỏ phần dashboard) ===== */
async function api(path, opt = {}) {
  try {
    return await fetch('/api' + path, { credentials: 'include', ...opt });
  } catch (e) {
    console.error('API error:', e);
    return null;
  }
}

function showToast(msg, type = 'info', ms = 3200) {
  const wrap = document.getElementById('toast-wrap');
  if (!wrap) return alert(msg);
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = String(msg);
  wrap.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  const close = () => {
    el.classList.remove('show');
    el.addEventListener('transitionend', () => el.remove(), { once: true });
  };
  const t = setTimeout(close, ms);
  el.addEventListener('click', () => {
    clearTimeout(t);
    close();
  });
}

/* Dropdown menu user */
(function menuSetup() {
  const btn = document.getElementById('userMenuBtn');
  const menu = document.getElementById('userMenu');
  if (!btn || !menu) return;
  function openMenu(on) {
    menu.classList.toggle('show', on);
    btn.setAttribute('aria-expanded', String(on));
  }
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    openMenu(!menu.classList.contains('show'));
  });
  document.addEventListener('click', () => menu.classList.contains('show') && openMenu(false));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') openMenu(false); });
  document.getElementById('btnMenuLogout')?.addEventListener('click', () => {
    openMenu(false);
    openLogout();
  });
})();

/* Modal logout (dùng chung) */
(function () {
  const wrap = document.getElementById('logoutModal');
  const box = document.getElementById('logoutBox');
  const ok = document.getElementById('lgOK');
  const cxl = document.getElementById('lgCancel');
  const x = document.getElementById('lgClose');
  let last = null;
  function open() {
    last = document.activeElement;
    wrap.classList.add('show');
    requestAnimationFrame(() => box.focus());
    document.body.classList.add('overflow-hidden');
  }
  function close() {
    wrap.classList.remove('show');
    document.body.classList.remove('overflow-hidden');
    last?.focus?.();
  }
  function trap(e) {
    if (e.key !== 'Tab') return;
    const f = box.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
  window.openLogout = open;
  ok.addEventListener('click', async () => {
    try { await api('/logout', { method: 'POST' }); } catch { }
    location.href = '/auth_login.html';
  });
  cxl.addEventListener('click', close);
  x.addEventListener('click', close);
  wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
  box.addEventListener('keydown', trap);
})();

/* Boot: load /me cho header sidebar */
async function boot() {
  const r = await api('/me');
  if (!r || !r.ok) {
    location.href = '/auth_login.html'; 
    return;
  }
  const me = await r.json();
  const name = me.full_name || me.username || 'Người dùng';
  (document.getElementById('helloName')||{}).textContent = name;
  (document.getElementById('helloRole')||{}).textContent = me.role || '';
  (document.getElementById('dashName')||{}).textContent  = name;

  // Nếu người dùng là Manager và cố gắng truy cập trang nhật ký
  if (me.role === "Manager" && window.location.pathname === '/journal.html') {
    // Hiển thị thông báo lỗi Toast
    showToast('Bạn không có quyền truy cập vào trang này.', 'error', 4500);
    setTimeout(() => { location.href = '/ams_home.html'; }, 5000);  // Chuyển hướng về trang chủ sau 5 giây
  }
}

boot();

/* ====== Định dạng thời gian VN cho account ====== */
function parseToDate(raw) {
  if (!raw) return null;
  let s = String(raw).trim();
  if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/.test(s)) s = s.replace(' ', 'T');

  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+\-]\d{2}:?\d{2})?$/);
  if (m) {
    const [, Y, M, D, h, mi, sec, ms, tz] = m;
    if (!tz) return new Date(Date.UTC(+Y, +M - 1, +D, +h, +mi, +sec, +(ms || 0)));
    return new Date(s);
  }
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

function formatVNTime(selector) {
  document.querySelectorAll(selector).forEach(el => {
    const raw = (el.textContent || '').trim();
    if (!raw || raw === '—') return;
    const d = parseToDate(raw);
    if (!d) return;
    el.textContent = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      day: '2-digit', month: '2-digit', year: 'numeric'
    }).format(d).replace(',', '');
  });
}

function formatVNDate(selector) {
  document.querySelectorAll(selector).forEach(el => {
    const raw = (el.textContent || '').trim();
    if (!raw || raw === '—') return;
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(raw)) return;
    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    let d = m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : parseToDate(raw);
    if (!d) return;
    el.textContent = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      day: '2-digit', month: '2-digit', year: 'numeric'
    }).format(d);
  });
}

/* Eye toggle cho password */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-toggle-eye]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.querySelector(btn.getAttribute('data-toggle-eye'));
      if (!input) return;
      const isPw = input.type === 'password';
      input.type = isPw ? 'text' : 'password';
      btn.setAttribute('aria-pressed', String(isPw));
      btn.textContent = isPw ? '🙈' : '👁️';
    });
  });
});

/* Chống double submit */
function lockSubmit(form) {
  const btn = form.querySelector('button[type=submit]');
  if (btn) {
    btn.disabled = true;
    btn.dataset.origText = btn.textContent;
    btn.textContent = 'Đang lưu...';
    btn.classList.add('opacity-60', 'cursor-not-allowed');
  }
  form.querySelectorAll('input,select,textarea,button').forEach(el => {
    if (el.tagName === 'BUTTON') return;
    el.readOnly = true;
  });
  return true;
}

/* Mật khẩu: strength + match */
(function bindPasswordHelpers() {
  const newPw = document.getElementById('new');
  const cfPw = document.getElementById('cf');
  const msg = document.getElementById('pwMatchMsg');
  const strength = document.getElementById('pwStrength');
  const submit = document.getElementById('btnSubmitPw');

  if (!newPw || !cfPw) return;

  function zxcvbnLiteScore(pw) {
    let score = 0;
    if (pw.length >= 6) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/\d/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    if (pw.length >= 12) score++;
    return Math.min(score, 4);
  }

  function renderStrength(pw) {
    const s = zxcvbnLiteScore(pw);
    const label = ['Rất yếu', 'Yếu', 'Trung bình', 'Khá', 'Mạnh'][s] || '';
    strength.textContent = pw ? `Độ mạnh: ${label}` : '';
    strength.className = 'mt-1 text-xs font-medium ' + (s <= 1 ? 'text-red-600' : s === 2 ? 'text-yellow-600' : 'text-green-600');
    return s;
  }

  function sync() {
    const s = renderStrength(newPw.value);
    const okMatch = !!newPw.value && newPw.value === cfPw.value;
    msg.textContent = cfPw.value ? (okMatch ? 'Khớp mật khẩu ✅' : 'Chưa khớp mật khẩu ❌') : '';
    msg.className = 'text-xs mt-1 ' + (okMatch ? 'text-green-600' : 'text-red-600');
    submit.disabled = !(okMatch && s >= 2);
  }

  newPw.addEventListener('input', sync);
  cfPw.addEventListener('input', sync);
  cfPw.addEventListener('paste', e => e.preventDefault());
  sync();
})();

/* Toggle form hồ sơ / đổi mật khẩu */
function showSection(id, on = true) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('hidden', !on);
  const trigger = id === 'profileForm'
    ? document.getElementById('btnToggleProfile')
    : document.getElementById('btnTogglePw');
  trigger?.setAttribute('aria-expanded', String(on));
  if (on) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

(function bindAccountToggles() {
  const btnProfile = document.getElementById('btnToggleProfile');
  const btnPw = document.getElementById('btnTogglePw');

  btnProfile?.addEventListener('click', () => {
    const on = document.getElementById('profileForm').classList.contains('hidden');
    showSection('profileForm', on);
  });

  btnPw?.addEventListener('click', () => {
    const on = document.getElementById('pwForm').classList.contains('hidden');
    showSection('pwForm', on);
    if (on) document.getElementById('old')?.focus();
  });
})();

/* Boot cho riêng trang account: định dạng ngày + xử lý flash & bắt buộc đổi mật khẩu */
window.addEventListener('DOMContentLoaded', () => {
  formatVNTime('[data-datetime]');
  formatVNDate('[data-dateonly]');

  const flashEl = document.getElementById('flash-data');
  if (flashEl) {
    const lvl = flashEl.dataset.level || 'info';
    const msg = flashEl.dataset.message || '';
    const type = lvl === 'success' ? 'success' : lvl === 'error' ? 'error' : lvl === 'warn' ? 'warn' : 'info';
    showToast(msg, type, 4500);
    flashEl.remove();
  }

  const url = new URL(window.location.href);
  const qFirst = url.searchParams.get('first') === '1';
  const flagsEl = document.getElementById('acct-flags');
  const mustChange = qFirst ||
    (flagsEl && (flagsEl.dataset.mustChange === '1' || flagsEl.dataset.first === '1'));

  if (mustChange) {
    showSection('pwForm', true);
    document.getElementById('old')?.focus();
    showToast('Lần đầu đăng nhập hoặc vừa được reset mật khẩu. Vui lòng đổi mật khẩu!', 'warn', 5000);
  }
});

/* Thông báo hết hạn phiên (query/cookie flag) */
(function () {
  const params = new URLSearchParams(location.search);
  const byQuery = params.get('expired') === '1';
  const byCookie = document.cookie.split(';').some(c => c.trim().startsWith('__session_expired=1'));
  if (byQuery || byCookie) {
    if (typeof showToast === 'function')
      showToast('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.', 'warn', 4500);
    else
      alert('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.');
    document.cookie = '__session_expired=; Max-Age=0; Path=/; SameSite=Lax';
  }
})();

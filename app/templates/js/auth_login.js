    /* ========== DOM refs ========== */
    const form = document.getElementById('loginForm');
    const u = document.getElementById('u');
    const p = document.getElementById('p');
    const remember = document.getElementById('remember');
    const btn = document.getElementById('btnLogin');
    const spinner = document.getElementById('spinner');
    const err = document.getElementById('err');
    const alertBox = document.getElementById('alert');
    const toggleBtn = document.getElementById('toggle');
    const capsTip = document.getElementById('capsTip');

    /* ========== Helpers ========== */
    function showErr(msg){
      err.textContent = msg || '';
      err.classList.toggle('hidden', !msg);
    }
    function showMsg(msg, type='info'){
      alertBox.textContent = msg || '';
      alertBox.className = 'min-h-[1.25rem] mb-2 text-sm ' + (type==='error'
        ? 'text-red-700' : type==='success' ? 'text-emerald-700' : 'text-gray-600');
    }
    function setLoading(on){
      if(!btn) return;
      btn.disabled = on;
      spinner.classList.toggle('hidden', !on);
    }
    function getCsrf(){
      // Ưu tiên meta, fallback đọc cookie nếu tên __Host-csrf/ csrf_token (tùy BE)
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content) return meta.content;
      const m = document.cookie.match(/(?:^|;\s*)(?:__Host-)?csrf(?:_token)?=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : null;
    }

    function persistUsername(){
      try{
        if(remember.checked){
          localStorage.setItem('ams_username', u.value.trim());
        }else{
          localStorage.removeItem('ams_username');
        }
      }catch{}
    }

    function restoreUsername(){
      try{
        const saved = localStorage.getItem('ams_username');
        if(saved){
          u.value = saved;
          remember.checked = true;
          // đưa focus vào password cho nhanh
          p.focus();
        }
      }catch{}
    }

    /* ========== Interactions ========== */
    // Hiện/ẩn password với ARIA
    toggleBtn.addEventListener('click', ()=>{
      const next = p.type === 'password' ? 'text' : 'password';
      p.type = next;
      toggleBtn.setAttribute('aria-pressed', String(next === 'text'));
      toggleBtn.title = next === 'text' ? 'Ẩn mật khẩu' : 'Hiện mật khẩu';
    });

    // Cảnh báo Caps Lock
    function handleKey(e){
      if (typeof e.getModifierState === 'function') {
        const on = e.getModifierState('CapsLock');
        capsTip.classList.toggle('hidden', !on);
      }
    }
    p.addEventListener('keydown', handleKey);
    p.addEventListener('keyup', handleKey);

    // Nhấn Enter trong input => submit (form mặc định đã làm, nhưng đảm bảo)
    [u,p].forEach(el=> el.addEventListener('keypress', e=>{
      if(e.key === 'Enter'){ form.requestSubmit(); }
    }));

    // Khôi phục username đã nhớ
    restoreUsername();

    /* ========== Submit login ========== */
    form.addEventListener('submit', async (e)=>{
      e.preventDefault();
      showErr(''); showMsg('');

      if (!u.value.trim() || !p.value) {
        showErr('Vui lòng nhập đầy đủ tài khoản và mật khẩu.');
        return;
      }

      setLoading(true);

      const fd = new FormData();
      fd.append('username', u.value.trim());
      fd.append('password', p.value);

      const headers = {};
      const csrf = getCsrf();
      if (csrf) headers['X-CSRF-Token'] = csrf;

      try{
        const resp = await fetch('/api/login', {
          method: 'POST',
          body: fd,
          headers,
          credentials: 'include'
        });

        // Thử đọc payload JSON nếu có
        let payload = null;
        const ct = resp.headers.get('content-type') || '';
        if (ct.includes('application/json')) {
          try{ payload = await resp.json(); }catch{}
        } else {
          try{ const t = await resp.text(); payload = t ? JSON.parse(t) : null; }catch{}
        }

        if (!resp.ok) {
          let msg =
            (payload && (payload.detail || payload.message || payload.error)) ||
            (resp.status===401 ? 'Sai tài khoản hoặc mật khẩu.' :
             resp.status===423 ? 'Tài khoản đang bị khoá. Vui lòng liên hệ Admin.' :
             resp.status===429 ? 'Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.' :
             `Đăng nhập thất bại (HTTP ${resp.status}).`);
          showErr(msg);
          return;
        }

        // Thành công
        persistUsername();
        showMsg('Đăng nhập thành công ✅', 'success');

        // Đặt cookie báo login thành công (sống 30 giây thôi)
        document.cookie = '__login_success=1; Max-Age=30; Path=/; SameSite=Lax';

        // Chuyển sang trang chủ
        location.href = '/ams_home.html';

      }catch(ex){
        showErr('Không thể kết nối máy chủ. Vui lòng kiểm tra mạng và thử lại.');
      }finally{
        setLoading(false);
      }
    });
/* ========== Thông báo khi phiên đăng nhập đã hết hạn (redirect về login) ========== */
    (function () {
      const params = new URLSearchParams(location.search);
      const byQuery  = params.get('expired') === '1';
      const byCookie = document.cookie.split(';').some(c => c.trim().startsWith('__session_expired=1'));

      if (byQuery || byCookie) {
        // Dùng showMsg để hiện thông báo ngay trên form login
        showMsg('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.', 'info');

        // Xoá cookie flag để F5 lại không hiện nữa
        document.cookie = '__session_expired=; Max-Age=0; Path=/; SameSite=Lax';
      }
    })();

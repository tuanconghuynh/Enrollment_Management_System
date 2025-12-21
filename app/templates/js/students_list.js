// app/templates/js/students_list.js
    // Ẩn lúc kiểm tra login
    document.documentElement.style.visibility = 'hidden';

    // ===== helpers =====
    const $ = id => document.getElementById(id);
    const STORAGE_KEY = "apiBase";
    const PREFIX_CANDIDATES = ["", "/api"];
    let API_PREFIX = "";

    // ===== Print Type Modal =====
    let __printMode = null;

    function __openPrintTypeModal(mode){
      __printMode = mode;
      const m = document.getElementById("printTypeModal");
      if (m) m.classList.remove("hidden");
    }

    function __closePrintTypeModal(){
      const m = document.getElementById("printTypeModal");
      if (m) m.classList.add("hidden");
    }

    (function bindPrintTypeEvents(){
      const cancel = document.getElementById("printTypeCancel");
      cancel && cancel.addEventListener("click", __closePrintTypeModal);

      document.querySelectorAll(".print-option").forEach(btn=>{
        btn.addEventListener("click", async ()=>{
          const type = btn.dataset.type;
          if (!type) return;
          await __handlePrintTypeSelected(type);
          __closePrintTypeModal();
        });
      });
    })();

    async function __handlePrintTypeSelected(type){
      if (__printMode === "DAY"){
          const d = dayEl.value.trim();
          if (!d){ alert("Anh chọn ngày đã"); return; }

          await journalTrack({
            action: "PRINT_IN",
            detail: { scope:"DAY", filters:{ day:d }, name_mode:type, count:null }
          });

          const url = `/batch/print?day=${encodeURIComponent(d)}&type=${type}`;
          await openPdfOrAlert(url);
          return;
      }

      if (__printMode === "DOT"){
          const dot  = $("dot").value.trim();
          const khoa = $("dotKhoa")?.value.trim() || "";

          if (!dot){ alert("Nhập tên đợt trước đã."); return; }

          await journalTrack({
            action: "PRINT_IN",
            detail: { scope:"DOT", filters:{ dot, ...(khoa?{khoa}:{}) }, name_mode:type, count:null }
          });

          let url = `/batch/print-dot?dot=${encodeURIComponent(dot)}&type=${type}`;
          if (khoa) url += `&khoa=${encodeURIComponent(khoa)}`;

          await openPdfOrAlert(url);
          return;
      }
    }

    // ===== Compose / Editor detection =====
    const COMPOSE_CANDIDATES = ["/compilation.html", "/compose.html", "/editor.html"];
    let COMPOSE_BASE = "/compilation.html";

    async function detectComposePage(){
      for (const p of COMPOSE_CANDIDATES) {
        try {
          const r = await fetch(p, { method: "GET", credentials: "include" });
          if (r.ok) { COMPOSE_BASE = p; break; }
        } catch(_) {}
      }
      const soan = document.querySelector('a[title="Biên soạn Hồ Sơ"]');
      if (soan) soan.href = COMPOSE_BASE;
    }

    const debounce = (fn, ms=300) => { let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); }; };

    (function initApiBase(){
      const saved = localStorage.getItem(STORAGE_KEY) || window.location.origin;
      $("apiBase").value = saved;
    })();

    const apiBase = () => $("apiBase").value.trim().replace(/\/+$/,'');
    const makeUrl = (path) => apiBase() + API_PREFIX + path;

    async function detectPrefix() {
      for (const p of PREFIX_CANDIDATES) {
        try { const r = await fetch(apiBase() + p + "/health", {credentials:"include"}); if (r.ok) { API_PREFIX = p; return; } } catch(_){}
      }
      API_PREFIX = ""; // fallback
    }

    async function apiFetch(path, init={}){
      const opts = {credentials:"include", ...init};
      let r = await fetch(makeUrl(path), opts).catch(()=>null);
      if (r && r.status !== 404) return r;
      // thử prefix còn lại nếu 404
      const alt = (API_PREFIX === "" ? "/api" : "");
      if (alt !== API_PREFIX) {
        try { const r2 = await fetch(apiBase() + alt + path, opts); if (r2.ok) { API_PREFIX = alt; return r2; } return r2; } catch(e){ return null; }
      }
      return r;
    }
    // --- Ghi log vào Journal (PRINT_IN / EXPORT)
    async function journalTrack(payload){
      try{
        await apiFetch('/journal/track', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify(payload || {})
        });
      }catch(_){ /* im lặng, không chặn luồng in/xuất */ }
    }
    // --- Định dạng ngày DMY ---
    function fmtDMY(s) {
      if (!s) return "";
      const t = String(s).trim();
      if (/^\d{2}\/\d{2}\/\d{4}$/.test(t)) return t;
      const m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (m) return `${m[3]}/${m[2]}/${m[1]}`;
      const d = new Date(t);
      if (!isNaN(d)) {
        const dd = String(d.getDate()).padStart(2, "0");
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const yy = d.getFullYear();
        return `${dd}/${mm}/${yy}`;
      }
      return t;
    }

    const dash = (x)=> (x && String(x).trim()!=="") ? x : '<span class="text-muted">—</span>';

    function setState({loading=false, empty=false}){
      $("loading").classList.toggle("hidden", !loading);
      $("emptyState").classList.toggle("hidden", !empty);
      $("tableWrap").classList.toggle("hidden", loading || empty);
    }

    // ===== Auth check (/me) =====
    async function ensureLoggedIn(){
      await detectPrefix();
      try{
        const r = await apiFetch("/me");
        if (!r || !r.ok) throw new Error();
        const me   = await r.json();
        const name = me.full_name || me.username || "";
        const role = me.role || "";

        // Cụm cũ (ẩn) – giữ lại cho script cũ
        if ($("meName"))   $("meName").textContent = name;
        if ($("meRole"))   $("meRole").textContent = role;
        if ($("meText"))   $("meText").classList.remove("hidden");
        if ($("loginLink"))$("loginLink").classList.add("hidden");
        if ($("btnLogout"))$("btnLogout").classList.remove("hidden");

        // Cụm mới trên sidebar
        if ($("helloName")) $("helloName").textContent = name || "Người dùng";
        if ($("helloRole")) $("helloRole").textContent = role || "";

        document.documentElement.style.visibility = '';
      }catch{
        const next = encodeURIComponent(location.pathname + location.search);
        location.replace(`/login?next=${next}`);
      }
    }

    $("btnLogout")?.addEventListener("click", async ()=>{
      try{ await apiFetch("/logout", {method:"POST"}); }catch(_) {}
      location.href = "/login";
    });

    // ===== Data/paging/sort state =====
    const state = {
      q: "",
      page: 1,
      size: 10,
      total: 0,
      cachedAllForFilter: [],
      sort: { key: null, dir: 'asc' },
      cacheAll: []
    };
    function pagesTotal(){ return Math.max(1, Math.ceil(state.total / state.size)); }

    // ===== Xoá mềm (client blacklist theo session) =====
    function isDeletedFlag(it){
      return !!(it?.deleted || it?.is_deleted || it?.deleted_at || it?.status === 'deleted');
    }
    const deletedMshv = new Set(JSON.parse(sessionStorage.getItem('deletedMshv') || '[]'));
    function persistDeletedMshv(){
      try { sessionStorage.setItem('deletedMshv', JSON.stringify([...deletedMshv])); } catch(_){}
    }

    function clearDeletedIfExists(items){
      (items || []).forEach(it => {
        const id = String(it?.ma_so_hv || '');
        const serverSoftDeleted = isDeletedFlag(it); // true nếu bản ghi còn đang soft-delete trên BE
        // Nếu server trả về và KHÔNG soft-delete -> gỡ khỏi blacklist của FE
        if (id && deletedMshv.has(id) && !serverSoftDeleted){
          deletedMshv.delete(id);
        }
      });
      persistDeletedMshv();
    }

    function notDeleted(it){
      const id = String(it?.ma_so_hv || '');
      return id && !deletedMshv.has(id) && !isDeletedFlag(it);
    }

    function renderRows(items){
      const tbody = $("tbody"); 
      tbody.innerHTML = "";
      (items||[]).forEach((it) => {
        const mshv = it.ma_so_hv;

        // ✅ THÊM 4 DÒNG NÀY
        const nganh = it.nganh_nhap_hoc ?? it.nganh ?? "";
        const dot   = it.dot ?? it.dot_tuyen ?? "";
        const khoa  = it.khoa ?? it.khoa_hoc ?? it.khoahoc ?? "";
        const nguoi = it.nguoi_nhan_ky_ten ?? it.nguoi_nhan ?? it.nguoi_ky ?? "";

        const tr = document.createElement("tr");
        tr.className = "row-alt";
        tr.innerHTML = `
          <td class="border-b text-center">
            <input type="checkbox" class="rowChk accent-blue-600" data-mshv="${encodeURIComponent(mshv)}" />
          </td>
          <td class="border-b whitespace-nowrap font-medium">
            <button class="text-blue-700 hover:underline link-detail"
                    data-mshv="${encodeURIComponent(mshv)}"
                    title="Xem chi tiết hồ sơ">
              ${dash(it.ma_ho_so)}
            </button>
          </td>
          <td class="border-b">
            <button class="text-blue-700 hover:underline link-detail"
                    data-mshv="${encodeURIComponent(mshv)}"
                    title="Xem chi tiết hồ sơ">
              ${dash(it.ho_dem || '')}
            </button>
          </td> 
          <td class="border-b">
            <button class="text-blue-700 hover:underline link-detail"
                    data-mshv="${encodeURIComponent(mshv)}"
                    title="Xem chi tiết hồ sơ">
              ${dash(it.ten || '')}
            </button>
          </td>
          <td class="border-b">
            <button class="text-blue-700 hover:underline font-mono link-detail"
                    data-mshv="${encodeURIComponent(mshv)}"
                    title="Xem chi tiết hồ sơ">
              ${dash(mshv)}
            </button>
          </td>
          <td class="border-b text-center whitespace-nowrap">${dash(fmtDMY(it.ngay_nhan_hs))}</td>
          <td class="border-b">${dash(nganh)}</td>
          <td class="border-b text-center">${dash(dot)}</td>
          <td class="border-b text-center">${dash(khoa)}</td>
          <td class="border-b">${dash(nguoi)}</td>
          <td class="border-b text-center whitespace-nowrap">
            <button class="btn btn-outline btn-xs btn-pill btn-email" data-mshv="${encodeURIComponent(mshv)}">✉️ Email</button>
          </td>
          <td class="border-b text-center whitespace-nowrap">
            <div class="inline-flex gap-2">
              <button class="btn btn-primary btn-xs btn-pill btn-print-a4"
                      data-mshv="${encodeURIComponent(mshv)}">
                in BNhận
              </button>
              <button class="btn btn-outline btn-xs btn-pill btn-postal"
                      data-mshv="${encodeURIComponent(mshv)}">
                in BĐiện
              </button>
            </div>
          </td>
          <td class="border-b text-center whitespace-nowrap">
            <div class="inline-flex gap-2">
              <button class="btn btn-outline btn-xs btn-pill btn-edit" data-mshv="${encodeURIComponent(mshv)}">Sửa</button>
              <button class="btn btn-outline btn-xs btn-pill btn-del text-rose-600 border border-rose-600 hover:bg-rose-600 hover:text-white" data-mshv="${encodeURIComponent(mshv)}">Xóa</button>
            </div>
          </td>`;
        tbody.appendChild(tr);
      });

      // ✅ Giữ nguyên phần sync checkbox + bulk
      document.querySelectorAll('.rowChk').forEach(ch => {
        const id = decodeURIComponent(ch.dataset.mshv || '');
        if (id && selectedMSHV.has(id)) ch.checked = true;
      });
      selectedMSHV.clear();
      updateBulkUI();
    }

    // ===== Drawer chi tiết hồ sơ =====
    const detailDrawer = document.getElementById('detailDrawer');
    const detailBackdrop = document.getElementById('detailBackdrop');
    const detailCloseBtn = document.getElementById('detailCloseBtn');
    const detailOpenEditBtn = document.getElementById('detailOpenEditBtn');
    const detailPrintA5Btn = document.getElementById('detailPrintA5Btn');
    const detailPrintA4Btn = document.getElementById('detailPrintA4Btn');

    let currentDetailMSHV = null;

    function openDetailDrawer() {
      if (!detailDrawer) return;
      detailDrawer.classList.remove('hidden');
    }

    function closeDetailDrawer() {
      if (!detailDrawer) return;
      detailDrawer.classList.add('hidden');
      currentDetailMSHV = null;
    }

    // Đóng khi bấm nền / nút X / phím Esc
    detailBackdrop?.addEventListener('click', closeDetailDrawer);
    detailCloseBtn?.addEventListener('click', closeDetailDrawer);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !detailDrawer.classList.contains('hidden')) {
        closeDetailDrawer();
      }
    });

    // helper nhẹ
    const $id = (id) => document.getElementById(id);

    // map status -> nhiều badge
    function setStatusBadge(app) {
      const el = $id('detailStatusBadge');
      if (!el) return;

      const statusRaw = (app && (app.status || app.tinh_trang || '') || '')
        .toString()
        .toLowerCase();

      const hasMaHS = !!(app && app.ma_ho_so && String(app.ma_ho_so).trim() !== '');

      const printed =
        !!(app &&
          (app.printed === true ||
            String(app.printed).toLowerCase() === 'true' ||
            statusRaw === 'printed'));

      const emailed =
        !!(app &&
          (app.email_sent === true ||
            String(app.email_sent).toLowerCase() === 'true' ||
            statusRaw === 'emailed' ||
            (app.last_email_at && String(app.last_email_at).trim() !== '')));

      // container
      el.innerHTML = '';
      el.className = 'inline-flex flex-wrap gap-1';

      const badges = [];

      // === 1. Badge theo status chính ===
      if (['done', 'complete', 'đủ hồ sơ', 'du_ho_so'].includes(statusRaw)) {
        badges.push({ text: 'Đã đủ hồ sơ', cls: 'bg-green-100 text-green-700' });
      } else if (['missing', 'thiếu hồ sơ'].includes(statusRaw)) {
        badges.push({ text: 'Thiếu hồ sơ', cls: 'bg-amber-100 text-amber-700' });
      } else if (statusRaw === 'draft') {
        badges.push({ text: 'Nháp / Chưa hoàn thành', cls: 'bg-sky-100 text-sky-700' });
      } else if (['saved', 'new', 'created'].includes(statusRaw)) {
        badges.push({ text: 'Đã lưu hồ sơ', cls: 'bg-sky-100 text-sky-700' });
      } else if (statusRaw === 'printed') {
        badges.push({ text: 'Đã in biên nhận', cls: 'bg-indigo-100 text-indigo-700' });
      } else if (['emailed', 'email_sent', 'da_gui_email'].includes(statusRaw)) {
        badges.push({ text: 'Đã gửi email', cls: 'bg-emerald-100 text-emerald-700' });
      }

      // Nếu hoàn toàn không có status
      if (!badges.length) {
        badges.push({ text: 'Chưa rõ tình trạng', cls: 'bg-slate-100 text-slate-700' });
      }

      // === 2. Badge theo mã hồ sơ ===
      if (hasMaHS) {
        badges.push({ text: 'Hồ sơ đã xử lý', cls: 'bg-blue-100 text-blue-700' });
      } else {
        badges.push({ text: 'Hồ sơ chờ xử lý', cls: 'bg-sky-100 text-sky-700' });
      }

      // === 3. Badge “Đã in biên nhận” nếu có cờ printed mà status không nói rõ ===
      if (printed && !badges.some(b => b.text === 'Đã in biên nhận')) {
        badges.push({ text: 'Đã in biên nhận', cls: 'bg-indigo-100 text-indigo-700' });
      }

      // === 4. Badge “Đã gửi email” nếu có log gửi email ===
      if (emailed && !badges.some(b => b.text === 'Đã gửi email')) {
        badges.push({ text: 'Đã gửi email', cls: 'bg-purple-100 text-purple-700' });
      }

      // render tất cả badge
      badges.forEach(b => {
        const span = document.createElement('span');
        span.className =
          'inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ' + b.cls;
        span.textContent = b.text;
        el.appendChild(span);
      });
    }

    function fillDetailDrawer(app) {
      if (!app) app = {};

      const fullName =
        app.full_name ||
        (app.ho_ten || `${app.ho_dem || ''} ${app.ten || ''}`).trim();

      $id('detailName').textContent = fullName || '—';
      $id('detailMSHV').textContent = app.ma_so_hv || '—';
      $id('detailMaHS').textContent = app.ma_ho_so || '—';

      // Họ đệm / Tên
      $id('detailHoDem').textContent = app.ho_dem || '—';
      $id('detailTen').textContent   = app.ten    || '—';

      // Ngày sinh / giới tính / dân tộc
      $id('detailNgaySinh').textContent = fmtDMY(app.ngay_sinh) || '—';
      $id('detailGioiTinh').textContent = app.gioi_tinh || '—';
      $id('detailDanToc').textContent   = app.dan_toc   || '—';

      // Liên hệ
      $id('detailSoDT').textContent = app.so_dt || app.so_dien_thoai || '—';

      const email = app.email_hoc_vien || app.email || '';
      const emailEl = $id('detailEmail');
      if (emailEl) {
        if (email) {
          emailEl.textContent = email;
          emailEl.href = 'mailto:' + email;
        } else {
          emailEl.textContent = '—';
          emailEl.removeAttribute('href');
        }
      }

      // Nhập học
      $id('detailNganh').textContent =
        app.nganh_nhap_hoc || app.nganh || '—';
      $id('detailKhoa').textContent =
        app.khoa || app.khoa_hoc || app.khoahoc || '—';
      $id('detailDot').textContent =
        app.dot || app.dot_tuyen || '—';
      $id('detailNgayNhan').textContent = fmtDMY(app.ngay_nhan_hs) || '—';
      $id('detailNguoiNhan').textContent =
        app.nguoi_nhan_ky_ten || app.nguoi_nhan || app.nguoi_ky || '—';

      // Ghi chú + nhật ký
      $id('detailGhiChu').textContent = app.ghi_chu || '';

      $id('detailUpdatedAt').textContent =
        app.updated_at ? fmtDMY(app.updated_at) : '—';
      $id('detailUpdatedBy').textContent =
        app.updated_by || '—';

      // Badge giới tính góc trên
      const g = (app.gioi_tinh || '').toString().toLowerCase();
      const gEl = $id('detailGenderBadge');
      if (gEl) {
        let txt = '—';
        if (g === 'nam') txt = 'Nam';
        else if (g === 'nữ' || g === 'nu') txt = 'Nữ';
        else if (g) txt = app.gioi_tinh;
        gEl.textContent = txt;
      }

      // Trạng thái hồ sơ (status)
      setStatusBadge(app);

      // Checklist hồ sơ
      const checklistWrap = $id('detailChecklist');
      const checklistSummary = $id('detailChecklistSummary');
      if (checklistWrap) {
        checklistWrap.innerHTML = '';
        const list = app.checklist || [];
        if (!list.length) {
          checklistWrap.innerHTML =
            '<li class="text-gray-500 italic">Chưa có dữ liệu checklist.</li>';
          if (checklistSummary) checklistSummary.textContent = '—';
        } else {
          let done = 0;
          list.forEach(item => {
            const ok = item.done || item.da_nop || item.completed;
            if (ok) done++;
            const li = document.createElement('li');
            li.className = 'flex items-center gap-2';
            li.innerHTML = `
              <span class="inline-flex w-4 h-4 rounded-full border flex-shrink-0
                          ${ok ? 'bg-green-500 border-green-500' : 'border-gray-300'}">
                ${ok ? '<span class="m-auto text-[10px] text-white">✓</span>' : ''}
              </span>
              <span class="${ok ? 'text-gray-800' : 'text-gray-600'}">
                ${item.label || item.ten || item.name || ''}
              </span>`;
            checklistWrap.appendChild(li);
          });

          if (checklistSummary) {
            checklistSummary.textContent = `${done}/${list.length} mục đã có`;
          }
        }
      }
    }

    // Gọi API lấy chi tiết
    async function openDetailByMSHV(mshv) {
      try {
        currentDetailMSHV = mshv;

        // set UI "loading"
        $id('detailName').textContent = 'Đang tải...';
        $id('detailMSHV').textContent = mshv;
        $id('detailMaHS').textContent = '—';
        $id('detailStatusBadge').textContent = 'Đang tải...';
        $id('detailStatusBadge').className =
          'inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700';

        openDetailDrawer();

        // Anh có thể đổi endpoint này cho khớp BE:
        const r = await apiFetch(`/applicants/by-mshv/${encodeURIComponent(mshv)}`);
        if (!r || !r.ok) {
          let msg = `Không lấy được chi tiết hồ sơ (HTTP ${r?.status || '???'})`;
          try {
            const t = await r.text();
            const j = JSON.parse(t);
            if (j?.detail) msg = j.detail;
          } catch {}
          showToast(msg, 'error');
          return;
        }

        const data = await r.json();
        // nếu BE trả kiểu {applicant: {...}} thì đổi thành data.applicant
        const app = data.applicant || data;

        fillDetailDrawer(app);
      } catch (e) {
        showToast(e.message || 'Lỗi tải chi tiết hồ sơ', 'error');
      }
    }

    // ===== Toast helper =====
    function showToast(msg, maybeOpts){
      let type = 'danger', timeout = 2200;
      if (typeof maybeOpts === 'object' && maybeOpts !== null) {
        type = maybeOpts.type || 'danger';
        timeout = Number(maybeOpts.timeout || 2200);
      } else if (typeof maybeOpts === 'string') {
        type = maybeOpts;
        if (typeof arguments[2] !== 'undefined') {
          const t = Number(arguments[2]);
          if (!Number.isNaN(t)) timeout = t;
        }
      }

      let toast = document.getElementById('toast');
      let inner = document.getElementById('toastInner');

      if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.className = 'fixed top-8 left-1/2 -translate-x-1/2 z-[11000] pointer-events-none hidden';
        document.body.appendChild(toast);
      }
      if (!inner) {
        inner = document.createElement('div');
        inner.id = 'toastInner';
        inner.className = 'px-5 py-3 rounded-xl shadow-xl text-white font-semibold backdrop-blur transition-all duration-300 scale-95 opacity-0 max-w-[90vw] sm:max-w-md text-center';
        toast.appendChild(inner);
      }

      const colors = {
        info: 'bg-blue-600/95',
        success: 'bg-green-600/95',
        warn: 'bg-amber-600/95',
        warning: 'bg-amber-600/95',
        error: 'bg-rose-600/95',
        danger: 'bg-rose-600/95'
      };

      inner.className = `px-5 py-3 rounded-xl shadow-xl text-white font-semibold backdrop-blur transition-all duration-300 scale-95 opacity-0 max-w-[90vw] sm:max-w-md text-center ${colors[type] || colors.danger}`;
      inner.textContent = String(msg || '');

      toast.classList.remove('hidden');
      requestAnimationFrame(() => {
        inner.classList.replace('scale-95', 'scale-100');
        inner.classList.replace('opacity-0', 'opacity-100');
      });

      clearTimeout(showToast._t);
      showToast._t = setTimeout(() => {
        inner.classList.replace('scale-100', 'scale-95');
        inner.classList.replace('opacity-100', 'opacity-0');
        setTimeout(() => toast.classList.add('hidden'), 300);
      }, timeout);
    }

    // ===== Modal nhập lý do (Promise) =====
    function askDeleteReason(message, placeholder=''){
      const overlay = document.getElementById('delModal');
      const msg = document.getElementById('delMsg');
      const txt = document.getElementById('delReason');
      const err = document.getElementById('delErr');
      const ok = document.getElementById('delOk');
      const cancel = document.getElementById('delCancel');

      msg.textContent = message || 'Xóa bản ghi này?';
      txt.value = placeholder || '';
      err.classList.add('hidden');
      overlay.classList.add('show');
      txt.focus();

      return new Promise(resolve=>{
        const done = (val)=>{
          overlay.classList.remove('show');
          ok.removeEventListener('click', onOk);
          cancel.removeEventListener('click', onCancel);
          overlay.removeEventListener('click', onBackdrop);
          document.removeEventListener('keydown', onEsc);
          resolve(val);
        };
        const onOk = ()=>{
          const v = (txt.value||'').trim();
          if(!v){ err.classList.remove('hidden'); txt.focus(); return; }
          done(v);
        };
        const onCancel = ()=> done(null);
        const onBackdrop = (e)=>{ if(e.target===overlay) done(null); };
        const onEsc = (e)=>{ if(e.key==='Escape') done(null); };

        ok.addEventListener('click', onOk);
        cancel.addEventListener('click', onCancel);
        overlay.addEventListener('click', onBackdrop);
        document.addEventListener('keydown', onEsc);
      });
    }

    // ===== Bắt sự kiện trong bảng (In / Sửa / Xoá) =====
    document.addEventListener('DOMContentLoaded', () => {
      const tbody = document.getElementById('tbody');
      if (!tbody) return;

      tbody.addEventListener('click', async (e) => {
        // --- Sửa: điều hướng sang trang biên soạn ---
        const editBtn = e.target.closest('.btn-edit');
        if (editBtn) {
          const mshv = decodeURIComponent(editBtn.dataset.mshv || '');
          if (!mshv) return;
          location.href = `${COMPOSE_BASE}?mshv=${encodeURIComponent(mshv)}&action=edit`;
          return;
        }
        // In A5/A4
        const a4 = e.target.closest('.btn-print-a4');
        if (a4) {
          const mshv = decodeURIComponent(a4.dataset.mshv || '');
          if (!mshv) return;

          await journalTrack({
            action: 'PRINT_IN',
            detail: { scope:'SINGLE', filters:{ mshv }, name_mode:'A4', count: 1 }
          });

          await openPdfOrAlert(`/print/a4/${encodeURIComponent(mshv)}`);
          return;
        }
        // In bưu điện
        const ps = e.target.closest('.btn-postal');
        if (ps) {
          const mshv = decodeURIComponent(ps.dataset.mshv || '');
          if (!mshv) return;

          await journalTrack({
            action: 'PRINT_IN',
            detail: { scope:'SINGLE', filters:{ mshv }, name_mode:'POSTAL', count: 1 }
          });

          await openPdfOrAlert(`/applicants/${encodeURIComponent(mshv)}/postal-print`);
          return;
        }
        // In A5 biên nhận (không email)
        const a5 = e.target.closest('.btn-print-a5');
        if (a5) {
          const mshv = decodeURIComponent(a5.dataset.mshv || '');
          if (!mshv) return;

          await journalTrack({
            action: 'PRINT_IN',
            detail: { scope:'SINGLE', filters:{ mshv }, name_mode:'A5', count: 1 }
          });

          await openPdfOrAlert(`/print/a5/${encodeURIComponent(mshv)}`);
          return;
        }

        // Xoá mềm
        const btn = e.target.closest('.btn-del');
        if (!btn) return;

        if (btn.disabled) { showToast('Bạn không có quyền xoá.', {type:'warn'}, 2000); return; }

        const mshv = decodeURIComponent(btn.dataset.mshv || '');
        if (!mshv) return;

        const reason = await askDeleteReason(`Xóa hồ sơ MSHV ${mshv} ?`, '');
        if (reason === null) return;

        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Đang xoá…';

        let resp = null;
        try {
          resp = await apiFetch(`/applicants/${encodeURIComponent(mshv)}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
          });
        } catch (_) {}

        if (!resp) {
          showToast('Không kết nối được máy chủ.', {type:'error', timeout:2200});
        } else if (resp.status === 204 || resp.status === 410) {
          deletedMshv.add(String(mshv));
          persistDeletedMshv();

          const tr = btn.closest('tr'); if (tr) tr.remove();
          showToast(`Đã xóa MSHV ${mshv}`, {type:'danger'});

          await runSearch();
        } else {
          let msg = `Xóa thất bại (HTTP ${resp.status})`;
          try { const t = await resp.text(); const j = JSON.parse(t); if (j?.detail) msg = j.detail; } catch {}
          showToast(msg, {type:'error', timeout:2600});
        }

        btn.textContent = original;
        btn.disabled = false;
      });
    });

    (function colorDeleteButtons(){
      const btns = Array.from(document.querySelectorAll('button, a'));
      btns.forEach(b => {
        const t = b.textContent?.trim();
        if (t === 'Xóa' || t === 'Xoá') {
          b.classList.add(
            'border', 'border-rose-600', 'text-rose-600',
            'hover:bg-rose-600', 'hover:text-white',
            'focus:ring-2','focus:ring-rose-400','focus:outline-none'
          );
          b.classList.remove('btn-primary','text-gray-700','border-gray-300');
          b.classList.add('rounded-lg');
        }
      });
    })();

    function updatePagerUI(total, page, size){
      $("count").textContent = String(total);
      document.querySelectorAll('.pager').forEach(p => {
        p.querySelector('.pager-info').textContent = `Trang ${page}/${Math.max(1, Math.ceil(total/size))} • ${total} mục`;
        const totalPages = Math.max(1, Math.ceil(total/size));
        p.querySelector('.pager-first').disabled = page <= 1;
        p.querySelector('.pager-prev').disabled  = page <= 1;
        p.querySelector('.pager-next').disabled  = page >= totalPages;
        p.querySelector('.pager-last').disabled  = page >= totalPages;
      });
    }

    // sắp xếp client-side (trên toàn tập)
    function applySort(list) {
      const { key, dir } = state.sort;
      if (!key) return list;

      const getVal = (it) => {
        switch (key) {
          case 'ho_dem': return (it.ho_dem || "").toString();
          case 'ten': return (it.ten || "").toString();
          case 'ma_so_hv': return (it.ma_so_hv || "").toString();
          case 'ngay_nhan_hs': {
            const v = it.ngay_nhan_hs;
            // chuẩn ISO -> số để sort ổn định; fallback về 0
            const t = v ? Date.parse(v) : 0;
            return isNaN(t) ? 0 : t;
          }
          case 'nganh': {
            const ng = it.nganh_nhap_hoc ?? it.nganh ?? "";
            return ng.toString();
          }
          case 'dot': {
            const d = it.dot ?? it.dot_tuyen ?? "";
            return d.toString();
          }
          case 'khoa': {
            const k = it.khoa ?? it.khoa_hoc ?? it.khoahoc ?? "";
            return k.toString();
          }
          case 'nguoi_nhan': {
            const n = it.nguoi_nhan_ky_ten ?? it.nguoi_nhan ?? it.nguoi_ky ?? "";
            return n.toString();
          }
          default: return "";
        }
      };

      const collator = new Intl.Collator('vi', { numeric: true, sensitivity: 'base' });
      const arr = list.slice().sort((a, b) => {
        const A = getVal(a), B = getVal(b);
        if (typeof A === 'number' && typeof B === 'number') return A - B;
        return collator.compare(String(A), String(B));
      });
      return dir === 'asc' ? arr : arr.reverse();
    }

    function setAriaSort(){
      document.querySelectorAll('.th-sortable').forEach(th=> th.removeAttribute('aria-sort'));
      if (state.sort.key){
        const th = document.querySelector(`.th-sortable[data-sort="${state.sort.key}"]`);
        if (th) th.setAttribute('aria-sort', state.sort.dir === 'asc' ? 'ascending' : 'descending');
      }
    }

    async function toggleSort(key) {
      if (state.sort.key === key) {
        state.sort.dir = (state.sort.dir === 'asc' ? 'desc' : 'asc');
      } else {
        state.sort.key = key;
        state.sort.dir = 'asc';
      }
      setAriaSort();
      await runSearch();
    }

    // --- Helpers chuẩn hoá và fetch ---
    function normalizePaged(data) {
      if (!data) return { items: [], total: 0, page: 1, size: 0 };
      if (Array.isArray(data.items)) {
        return { items: data.items, total: Number(data.total ?? data.items.length ?? 0), page: Number(data.page ?? 1), size: Number(data.size ?? data.items.length ?? 0) };
      }
      if (Array.isArray(data.results)) {
        return { items: data.results, total: Number(data.total ?? data.results.length ?? 0), page: Number(data.page ?? 1), size: Number(data.size ?? data.results.length ?? 0) };
      }
      if (Array.isArray(data)) { return { items: data, total: data.length, page: 1, size: data.length }; }
      return { items: [], total: 0, page: 1, size: 0 };
    }
    async function tryJson(url) {
      const r = await apiFetch(url).catch(()=>null);
      if (!r || !r.ok) return null;
      try { return await r.json(); } catch { return null; }
    }

    function isLikelyNameQuery(q){
      const s = (q||"").trim();
      if (!s) return false;
      const hasLetter = /[A-Za-zÀ-Ỵà-ỵ]/.test(s);
      const manyDigits = /^\d{4,}$/.test(s);
      return hasLetter && !manyDigits;
    }

  // Chuẩn hóa văn bản và loại bỏ dấu (chỉ so sánh dấu chính xác)
  function vnNorm(s) {
    return (s || "")
      .normalize("NFD")  // Phân tách dấu
      .replace(/[\u0300-\u036f]/g, "") // Loại bỏ dấu
      .replace(/đ/g, "d").replace(/Đ/g, "D") // Thay thế "đ" và "Đ"
      .trim().toLowerCase();  // Chuyển về chữ thường
  }

  // So sánh tên (Họ đệm + Tên) với từ khóa, chỉ ra kết quả chính xác
  function matchScore(name, query) {
    const normalizedName = vnNorm(name);
    const normalizedQuery = vnNorm(query);

    // Nếu cả hai giống nhau (có dấu giống nhau)
    if (normalizedName === normalizedQuery) return 100;  

    // Nếu tên bắt đầu giống từ khóa (có dấu giống nhau)
    if (normalizedName.startsWith(normalizedQuery)) return 90;

    // Nếu tên chứa từ khóa
    if (normalizedName.includes(normalizedQuery)) return 80;

    return 0;  // Không có sự khớp
  }

  // Lọc và sắp xếp tên (Họ đệm + Tên) theo từ khóa nhập vào
  function filterAndSortByName(list, query) {
    return list.filter(item => {
      const fullName = item.ho_ten || item.ten || "";  // Lấy Họ tên
      return matchScore(fullName, query) > 0;  // Kiểm tra xem có khớp không
    });
  }

    // lấy 1 trang server
    async function fetchPageServer(q, page, size){
      for (const k of ["q","name","full_name"]) {
        const j = await tryJson(`/applicants/search?${k}=${encodeURIComponent(q)}&page=${page}&size=${size}`);
        if (j) {
          const norm = normalizePaged(j);

          // ✅ Gỡ MSHV khỏi blacklist nếu server đã trả về (và không còn soft-delete)
          clearDeletedIfExists(norm.items);

          // Sau đó mới lọc notDeleted
          norm.items = (norm.items || []).filter(notDeleted);
          return norm;
        }
      }

      let j = await tryJson(`/applicants/search?page=${page}&size=${size}`);
      if (j) {
        const norm = normalizePaged(j);
        clearDeletedIfExists(norm.items);
        norm.items = (norm.items || []).filter(notDeleted);
        return norm;
      }

      j = await tryJson(`/applicants?page=${page}&size=${size}`);
      if (j) {
        const norm = normalizePaged(j);
        clearDeletedIfExists(norm.items);
        norm.items = (norm.items || []).filter(notDeleted);
        return norm;
      }

      return { items: [], total: 0, page: 1, size: size };
    }

    // lấy nhiều trang (để sort/loc client)
    async function fetchUpTo(limit=5000){
      const out = [];
      let page = 1;
      const size = 200;
      for(;;){
        const data = await fetchPageServer(state.q, page, size);
        (data.items||[]).forEach(x => { if (notDeleted(x)) out.push(x); });
        const total = data.total ?? out.length;
        if (out.length >= total || out.length >= limit || (data.items||[]).length === 0 || (data.items||[]).length < size) break;
        page += 1;
      }
      return out.slice(0, limit);
    }

    function applyClientFilters(list){
      const dot  = $("filterDot").value.trim().toLowerCase();
      const khoa = $("filterKhoa").value.trim().toLowerCase();
      return (list||[]).filter(it=>{
        const _dot  = String(it.dot ?? it.dot_tuyen ?? "").toLowerCase();
        const _khoa = String(it.khoa ?? it.khoa_hoc ?? it.khoahoc ?? "").toLowerCase();
        const okDot  = !dot  || _dot.includes(dot);
        const okKhoa = !khoa || _khoa === khoa || _khoa.includes(khoa);
        return okDot && okKhoa;
      });
    }

    async function buildSourceFull(){
      state.cacheAll = (await fetchUpTo(5000)).filter(notDeleted);

      // 🔹 Lần đầu có dữ liệu thì build dropdown Đợt/Khóa
      if (!filterOptionsBuilt) {
        buildFilterOptions(state.cacheAll);
      }

      const wantFilter = $("filterDot").value.trim() !== "" || $("filterKhoa").value.trim() !== "";
      let list = wantFilter ? applyClientFilters(state.cacheAll) : state.cacheAll.slice();
      list = applySort(list);
      return list;
    }

    let filterOptionsBuilt = false;

    // Tạo options cho các dropdown Đợt / Khóa từ danh sách hồ sơ
    function buildFilterOptions(list) {
      const dotSet  = new Set();
      const khoaSet = new Set();

      (list || []).forEach(it => {
        const dot  = (it.dot ?? it.dot_tuyen ?? '').toString().trim();
        const khoa = (it.khoa ?? it.khoa_hoc ?? it.khoahoc ?? '').toString().trim();
        if (dot)  dotSet.add(dot);
        if (khoa) khoaSet.add(khoa);
      });

      const filterDotSel   = document.getElementById('filterDot');   // lọc trên danh sách
      const filterKhoaSel  = document.getElementById('filterKhoa');  // lọc trên danh sách
      const dotSel         = document.getElementById('dot');         // xuất theo đợt
      const dotKhoaSel     = document.getElementById('dotKhoa');     // xuất theo khóa

      const dots  = Array.from(dotSet).sort();
      const khoas = Array.from(khoaSet).sort();

      const buildOpts = (arr, firstLabel) =>
        `<option value="">${firstLabel}</option>` +
        arr.map(v => `<option value="${v}">${v}</option>`).join('');

      if (filterDotSel)  filterDotSel.innerHTML  = buildOpts(dots,  'Tất cả đợt');
      if (dotSel)        dotSel.innerHTML        = buildOpts(dots,  '-- Chọn đợt --');

      if (filterKhoaSel) filterKhoaSel.innerHTML = buildOpts(khoas, 'Tất cả khóa');
      if (dotKhoaSel)    dotKhoaSel.innerHTML    = buildOpts(khoas, '-- Chọn khóa --');

      filterOptionsBuilt = true;
    }

    async function runSearch(){
      setState({loading:true});
      try{
        const full = await buildSourceFull(); // Lấy dữ liệu đã lọc
        clearDeletedIfExists(full);
        state.total = full.length;

        const totalPages = Math.max(1, Math.ceil(state.total / state.size));
        if (state.page > totalPages) state.page = totalPages;

        const start = (state.page - 1) * state.size;
        renderRows(full.slice(start, start + state.size)); // Hiển thị các kết quả
        updatePagerUI(state.total, state.page, state.size);
        setState({loading:false, empty: state.total === 0});
      }catch(e){
        setState({loading:false, empty:true});
        $("msg").textContent = e.message || "Lỗi không xác định";
      }
    }

    (function listenRestoreBroadcast(){
      try {
        const bc = new BroadcastChannel('app-events');
        bc.onmessage = (ev) => {
          const t = ev?.data?.type;
          const id = String(ev?.data?.mssv || '');
          if (!id) return;

          if (t === 'APPLICANT_RESTORED') {
            deletedMshv.delete(id);
            persistDeletedMshv();
            state.page = 1;
            runSearch();
          }

          // 🧹 Khi xoá vĩnh viễn: gỡ luôn khỏi blacklist xoá mềm để sau này tạo lại sẽ hiện
          if (t === 'APPLICANT_DELETED_PERMANENT') {
            deletedMshv.delete(id);
            persistDeletedMshv();
            state.page = 1;
            runSearch();
          }
        };
      } catch(_) {}
    })();

    // ===== File helpers =====
    async function fetchFileOrAlert(url, filename, type = "excel"){
      const resp = await fetch(makeUrl(url), { credentials: "include" });

      if (!resp.ok){
        let msg;
        try {
          const t = await resp.text();
          const j = JSON.parse(t);

          if (j?.detail && j.detail !== 'Not Found') {
            // BE có message tiếng Việt thì ưu tiên
            msg = j.detail;
          } else if (resp.status === 404) {
            msg = `Không tìm thấy dữ liệu phù hợp để ${
              type === 'pdf' ? 'in' : 'xuất'
            } Trong thời gian này!`;
          } else {
            msg = `Không thể ${
              type === 'pdf' ? 'in' : 'xuất'
            } (HTTP ${resp.status}).`;
          }
        } catch(_){
          msg = `Không thể ${
            type === 'pdf' ? 'in' : 'xuất'
          } (HTTP ${resp.status}).`;
        }

        if (typeof showToast === 'function') {
          showToast(msg, 'error', 2800);
        } else {
          alert(msg);
        }
        return;
      }

      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a); 
      a.click(); 
      a.remove();
      setTimeout(()=>URL.revokeObjectURL(a.href), 60000);
    }

  async function openPdfOrAlert(url){
    window.open(makeUrl(url), "_blank");
  }

    // ===== Export/In ấn theo ngày/đợt =====
    // ---- Theo NGÀY
    const dayEl = $("day");
    if (dayEl) {
      // Khởi tạo Flatpickr
      flatpickr(dayEl, {
        locale: "vn",              // tiếng Việt
        dateFormat: "Y-m-d",       // giá trị thực gửi về BE
        altInput: true,            // ô hiển thị đẹp
        altFormat: "d/m/Y",        // hiển thị cho người dùng
        altInputClass: "input w-60",
        defaultDate: new Date(),
        allowInput: true
      });

      // Nút Xuất Excel theo ngày
      $("btnExportDay")?.addEventListener("click", async () => {
        const day = dayEl.value.trim();        // format Y-m-d
        if (!day) {
          alert("Anh chọn ngày trước đã.");
          return;
        }
        showLoading("Đang tải dữ liệu xuất, vui lòng đợi...");

        await journalTrack({
          action: "EXPORT",
          detail: {
            scope: "DAY",
            filters: { day },
            name_mode: "split",
            count: null
          }
        });

        const url = `/export/excel?day=${encodeURIComponent(day)}&name=split`;
        await fetchFileOrAlert(
          url,
          `tong_ngay_${day}.xlsx`,
          "excel"
        );
        hideLoading(); 
      });

      // Nút In theo ngày
        $("btnPrintDay")?.addEventListener("click", async () => {
          const day = dayEl.value.trim();
          if (!day){
            alert("Anh chọn ngày trước đã.");
            return;
          }
          __openPrintTypeModal("DAY");
        });
    }

    // ---- Theo đợt/khóa
    const dotEl = $("dot");
    if (dotEl) {
      $("btnExportDot")?.addEventListener("click", async () => {
        const dot  = $("dot").value.trim();
        const khoa = $("dotKhoa")?.value.trim() || "";
        if (!dot){ alert("Nhập tên đợt trước đã"); return; }
        showLoading("Đang tải dữ liệu in, vui lòng đợi...");

        await journalTrack({ action:'EXPORT', detail:{ scope:'DOT', filters:{ dot, ...(khoa?{khoa}:{}) }, name_mode:'split', count:null }});
        let url = `/export/excel-dot?dot=${encodeURIComponent(dot)}&name=split`;
        if (khoa) url += `&khoa=${encodeURIComponent(khoa)}`;
        await fetchFileOrAlert(url, `tong_dot_${dot}${khoa?`_khoa_${khoa}`:""}.xlsx`, "excel");
        hideLoading(); 
      });

      $("btnPrintDot")?.addEventListener("click", async () => {
        const dot  = $("dot").value.trim();
        if (!dot){
          alert("Nhập tên đợt trước đã.");
          return;
        }
        __openPrintTypeModal("DOT");
      });
    }

    // ===== Sort header bindings =====
    function bindSortHandlers(){
      document.querySelectorAll('.th-sortable').forEach(th=>{
        const key = th.getAttribute('data-sort');
        const handler = ()=> toggleSort(key);
        th.addEventListener('click', handler);
        th.addEventListener('keydown', (e)=>{ if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handler(); } });
      });
    }

    // ===== Bind search/paging =====
    $("btnSearch").onclick = ()=>{ state.q = $("q").value.trim(); state.page = 1; runSearch(); };
    $("q").addEventListener("keydown", e=>{ if(e.key==="Enter") $("btnSearch").click(); });

    $("pageSize").addEventListener("change", ()=>{
      state.size = Number($("pageSize").value) || 10;
      localStorage.setItem("students.pageSize", String(state.size));
      state.page = 1; runSearch();
    });

    function bindPager(container){
      container.querySelector('.pager-first').onclick = ()=> { state.page = 1; runSearch(); };
      container.querySelector('.pager-prev').onclick  = ()=> { if (state.page > 1) { state.page--; runSearch(); } };
      container.querySelector('.pager-next').onclick  = ()=> { state.page++; runSearch(); };
      container.querySelector('.pager-last').onclick  = ()=> { state.page = pagesTotal(); runSearch(); };
    }
    document.querySelectorAll('.pager').forEach(bindPager);

    // Lọc client theo đợt/khóa (debounce)
    ["filterDot","filterKhoa"].forEach(id=>{
      $(id).addEventListener("change", async ()=>{
        state.page = 1;
        await runSearch();
      });
    });

    // ===== init =====
    window.addEventListener('load', async () => {
      await ensureLoggedIn();
      await detectComposePage();
      (function checkRestoredFallback(){
        try {
          const id = localStorage.getItem('restored.mssv');
          if (id) {
            deletedMshv.delete(String(id));
            persistDeletedMshv();
            localStorage.removeItem('restored.mssv');
            state.page = 1;
            runSearch();
          }
        } catch(_) {}
      })();
      $("q").focus();
      (function checkPurgedFallback(){
        try {
          const id = localStorage.getItem('purged.mssv');
          if (id) {
            deletedMshv.delete(String(id));
            persistDeletedMshv();
            localStorage.removeItem('purged.mssv');
            state.page = 1;
            runSearch();
          }
        } catch(_) {}
      })();
      const defaultSize = 10;
      $("pageSize").value = String(defaultSize);
      state.size = defaultSize;

      bindSortHandlers();
      if (state.page > 1 && (state.total - 1) % state.size === 0) {
        state.page--;
      }
      await runSearch();
    });

    // lưu base khi sửa
    $("apiBase").addEventListener("change", ()=>{
      localStorage.setItem(STORAGE_KEY, $("apiBase").value.trim());
    });

    // ENTER to search for Đợt / Khóa
    (function bindEnterForFilters(){
      const dotInput  = document.getElementById('filterDot');
      const khoaInput = document.getElementById('filterKhoa');
      const triggerSearch = () => runSearch();
      [dotInput, khoaInput].forEach(el => {
        if (!el) return;
        el.addEventListener('keydown', (e) => {
          if (e.key === 'Enter'){ e.preventDefault(); triggerSearch(); }
        });
      });
    })();

    // Nút vào Journal theo quyền
    (async function controlJournalButton(){
      await detectPrefix();
      const link = document.getElementById('journalLink');
      if (!link) return;

      let role = null;
      try {
        const r = await apiFetch('/me');
        if (r && r.ok) {
          const me = await r.json();
          role = me?.role || null;
        }
      } catch (_) {}

      if (role === 'Admin' || role === 'NhanVien') {
        link.hidden = false;
        link.onclick = null;
      } else {
        link.hidden = true;
        link.addEventListener('click', (e)=>{
          e.preventDefault();
          alert('Quyền tài khoản không được phép truy cập Nhật ký.');
        });
      }
    })();

    // Ép link Journal sạch
    (function forceCleanJournalLink(){
      const link = document.getElementById('journalLink');
      if (!link) return;
      link.href = '/journal.html';
      link.addEventListener('click', (e)=>{
        e.preventDefault();
        window.location.assign('/journal.html');
      });
    })();

    // Live-search cho ô #q (Họ tên / MSHV) — không cần bấm Tìm
    $('q').addEventListener('input', debounce(async () => {
      const v = $('q').value.trim();

      if (v.length < 2) {
        state.q = '';
        state.page = 1;
        await runSearch(); // Trả về danh sách đã lọc
        return;
      }

      state.q = v;
      state.page = 1;
      await runSearch();
    }, 250));

    (function () {
    // Ưu tiên query expired=1 (khi bị redirect)
    const params = new URLSearchParams(location.search);
    const byQuery = params.get('expired') === '1';

    // Hoặc cookie cờ do BE set
    const byCookie = document.cookie.split(';').some(c => c.trim().startsWith('__session_expired=1'));

    if (byQuery || byCookie) {
      // Hiện thông báo rộng rãi
      if (typeof showToast === 'function') {
        showToast('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.', 'warn', 4500);
      } else {
        // Fallback nếu trang không có showToast
        alert('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.');
      }
      // Xóa cookie cờ để khỏi lặp lại
      document.cookie = '__session_expired=; Max-Age=0; Path=/; SameSite=Lax';
    }
  })();

  // ===== Modal logout (dùng apiFetch của trang này) =====
  (function(){
    const wrap = document.getElementById('logoutModal');
    const box  = document.getElementById('logoutBox');
    const ok   = document.getElementById('lgOK');
    const cxl  = document.getElementById('lgCancel');
    const x    = document.getElementById('lgClose');
    let last = null;

    if (!wrap || !box) return;

    function open(){
      last = document.activeElement;
      wrap.classList.add('show');
      document.body.classList.add('overflow-hidden');
      requestAnimationFrame(()=> box.focus());
    }
    function close(){
      wrap.classList.remove('show');
      document.body.classList.remove('overflow-hidden');
      last && last.focus && last.focus();
    }
    function trap(e){
      if (e.key !== 'Tab') return;
      const f = box.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
      if (!f.length) return;
      const first = f[0], lastEl = f[f.length-1];
      if (e.shiftKey && document.activeElement === first){ e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl){ e.preventDefault(); first.focus(); }
    }

    window.openLogout = open;

    ok.addEventListener('click', async ()=>{
      try { await apiFetch('/logout', {method:'POST'}); } catch(_){}
      location.href = '/login';
    });
    cxl.addEventListener('click', close);
    x.addEventListener('click', close);
    wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
    box.addEventListener('keydown', trap);
  })();

  // --- Tải mẫu XLSX ---
  function downloadXlsxTemplate() {
    const rows = [
      [
        "ma_so_hv","ho_dem","ten","ho_ten","gioi_tinh","dan_toc",
        "ngay_sinh","so_dt","email_hoc_vien","nganh_nhap_hoc","dot","khoa","ghi_chu"
      ],
      // ví dụ 1
      ["2510000123","Nguyen Van","An","","Nam","Kinh","01/01/2005","0912345678","an@example.com","CNTT","1","27",""],
      // ví dụ 2
      ["2510000456","","","Nguyen Thi B","Nu","Kinh","2004-12-31","","b@example.com","Marketing","2","27","Cập nhật email"]
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "batch_update_template");
    ws['!cols'] = [
      {wch:12}, {wch:14}, {wch:10}, {wch:22}, {wch:8}, {wch:8},
      {wch:12}, {wch:14}, {wch:28}, {wch:20}, {wch:8}, {wch:8}, {wch:22}
    ];
    XLSX.writeFile(wb, "batch_update_template.xlsx");
  }
  document.getElementById("btnDownloadTemplate")?.addEventListener("click", downloadXlsxTemplate);

  // ===== Toggle khối "TOOL EDIT INFO • Excel" =====
  (function bindExcelToggle(){
    const btn = document.getElementById('btnExcelToggle');
    const box = document.getElementById('excelBox');
    if (!btn || !box) return;

    btn.addEventListener('click', () => {
      const isHidden = box.classList.contains('hidden');
      // đảo trạng thái
      box.classList.toggle('hidden', !isHidden);

      // cập nhật aria-expanded + text nút cho dễ hiểu
      btn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
      btn.textContent = isHidden
        ? '⬆️ Thu gọn khu Excel'
        : '⚙️ Cập nhật từ Excel';
    });
  })();

  // Đọc file XLSX
  async function readFileToRows(file){
    if (!file) throw new Error('Chưa chọn file.');
    const name = (file.name||'').toLowerCase();
    if (!name.endsWith('.xlsx')) throw new Error('Chỉ nhận .xlsx');
    if (typeof XLSX === 'undefined') throw new Error('Thiếu thư viện XLSX.');
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(buf, {type:'array', cellDates:false, raw:false});
    const ws = wb.Sheets[wb.SheetNames[0]];
    return XLSX.utils.sheet_to_json(ws, {defval:''});
  }

  // Chuẩn hoá MSHV về 10 số
  function normMssv(v){
    if (v == null) return '';
    if (typeof v === 'number') v = String(Math.trunc(v));
    let s = String(v).trim();
    if (/e\+/i.test(s)) { // dạng 2.51E+09
      const n = Number(s);
      if (!Number.isNaN(n)) s = String(Math.trunc(n));
    }
    s = s.replace(/\D/g, '');       // bỏ ký tự không phải số
    if (s.length === 9) s = '0' + s; // hay gặp mất '0' đầu
    return s;
  }

  // Map giới tính hay gặp
  function normGender(v){
    if (!v) return v;
    const s = String(v).trim().toLowerCase();
    if (s === 'nu' || s === 'nữ') return 'Nữ';
    if (s === 'nam') return 'Nam';
    if (s === 'khac' || s === 'khác') return 'Khác';
    return v; // để BE validate tiếp
  }

  // Render preview
  function renderBatchPreview(resp){
    const wrap = $('batchPreviewWrap'), body = $('batchPreviewBody');
    if (!wrap || !body) return;
    wrap.classList.remove('hidden'); body.innerHTML = '';
    (resp.results||[]).forEach(r=>{
      const tr = document.createElement('tr');
      const fields = r.changed_fields ? Object.keys(r.changed_fields).join(', ') : '—';
      const statusClass =
        r.status === 'UPDATED' ? 'text-green-700' :
        r.status === 'SKIPPED' ? 'text-gray-600' :
        r.status === 'NOT_FOUND' ? 'text-orange-700' :
        r.status === 'SOFT_DELETED' ? 'text-purple-700' :
        r.status === 'INVALID' ? 'text-red-700' : 'text-gray-700';
      tr.innerHTML = `
        <td class="p-2 border-b font-medium">${r.ma_so_hv || ''}</td>
        <td class="p-2 border-b ${statusClass}">${r.status}${r.errors ? ' • ' + (r.errors||[]).join('; ') : ''}</td>
        <td class="p-2 border-b">${fields}</td>`;
      body.appendChild(tr);
    });
    $('batchMsg').textContent =
      `Tổng: ${resp.total} • UPDATED: ${resp.updated} • SKIPPED: ${resp.skipped} • NOT_FOUND: ${resp.not_found} • SOFT_DELETED: ${resp.soft_deleted} • INVALID: ${resp.invalid}`;
  }

  // Chuẩn hoá và gửi batch
  async function callBatch(dry){
    const file = document.getElementById('batchFile')?.files?.[0];
    if (!file){ alert('Chọn file XLSX trước đã.'); return; }

    const stop = document.getElementById('stopOnError')?.checked ? true : false;

    // khoá nút trong lúc chạy
    const btnPrev = document.getElementById('btnBatchPreview');
    const btnApply = document.getElementById('btnBatchApply');
    btnPrev?.setAttribute('disabled','');
    btnApply?.setAttribute('disabled','');

    try{
      document.getElementById('batchMsg').textContent = dry ? 'Đang chạy dry-run…' : 'Đang cập nhật…';

      const rows  = await readFileToRows(file);
      const items = (function normalizeItems(rawList){
        const fields = ["ma_so_hv","ho_dem","ten","ho_ten","gioi_tinh","dan_toc",
                        "ngay_sinh","so_dt","email_hoc_vien","nganh_nhap_hoc","dot","khoa","ghi_chu"];
        return rawList.map(r=>{
          const o = {};
          fields.forEach(f=>{ if (r[f] !== undefined && String(r[f]).trim() !== '') o[f] = String(r[f]).trim(); });
          return o;
        });
      })(rows);

      const miss  = items.findIndex(x=>!x.ma_so_hv);
      if (miss >= 0) throw new Error(`Dòng ${miss+1}: thiếu ma_so_hv`);

      const payload = JSON.stringify({ items, stop_on_error: stop });

      // ---- thử nhiều endpoint/method như trước
      const qs    = dry ? '?dry_run=true' : '?dry_run=false';
      const paths = [
        `/applicants/batch-update${qs}`,
        `/applicants/batch-update/${qs}`,
        `/applicants/batch_update${qs}`,
        `/applicants/batch_update/${qs}`,
        `/batch/update${qs}`,
        `/applicants/batch${qs}`
      ];
      const methods = ['POST','PUT','PATCH'];

      let lastText = '', lastStatus = 0, respJson = null, ok = false;

      for (const p of paths) {
        for (const m of methods) {
          let r = null;
          try {
            r = await apiFetch(p, {
              method: m,
              headers: { 'Content-Type':'application/json' },
              body: payload
            });
          } catch(_) {}
          if (r && r.ok) {
            respJson = await r.json();
            ok = true;
            break;
          }
          if (r) {
            lastStatus = r.status;
            try { lastText = await r.text(); } catch { lastText = ''; }
            if (r.status !== 404 && r.status !== 405) break;
          }
        }
        if (ok) break;
      }

      if (!ok) {
        const msg = lastText || `Batch update thất bại (HTTP ${lastStatus||'???'})`;
        document.getElementById('batchMsg').textContent = msg;
        showToast(msg, 'error');
        return;
      }

      // Hiển thị preview kết quả (cả dry-run & apply)
      renderBatchPreview(respJson);
      const totalChanged = (respJson?.results||[]).filter(r=>r.status==='UPDATED').length;

      if (dry) {
        showToast('Dry-run OK', 'info');
        document.getElementById('batchMsg').textContent = `Dry-run OK • ${totalChanged} bản ghi sẽ thay đổi`;
      } else {
        showToast('Cập nhật xong!', 'success');
        document.getElementById('batchMsg').textContent = `Đã cập nhật ${respJson?.updated ?? totalChanged} bản ghi`;

        // ⟳ làm mới danh sách kết quả phía dưới sau khi áp dụng
        await runSearch();

        // Thu gọn khu preview + reset file để tránh lẫn
        document.getElementById('batchPreviewWrap')?.classList.add('hidden');
        document.getElementById('batchFile').value = '';
      }
    } catch(e){
      document.getElementById('batchMsg').textContent = e.message || 'Lỗi batch update';
      showToast(e.message || 'Lỗi batch update', 'error');
    
    } finally {
      btnPrev?.removeAttribute('disabled');
      btnApply?.removeAttribute('disabled');
    }
  }
  $('btnBatchPreview')?.addEventListener('click', ()=> callBatch(true));
  $('btnBatchApply')?.addEventListener('click',  ()=> callBatch(false));

  function prettifyError(msg){
  if (!msg) return '';
  if (/write_audit\(\).*unexpected keyword argument 'correlation_id'/.test(msg)) {
    return 'Mô-đun nhật ký (audit) đang dùng phiên bản cũ – đã bỏ qua ghi nhật ký. Dữ liệu vẫn được xem thử/cập nhật bình thường.';
  }
  return msg;
}

function renderBatchPreview(resp){
  const wrap = $('batchPreviewWrap'), body = $('batchPreviewBody');
  if (!wrap || !body) return;
  wrap.classList.remove('hidden'); body.innerHTML = '';

  (resp.results||[]).forEach(r=>{
    const tr = document.createElement('tr');
    const fields = r.changed_fields ? Object.keys(r.changed_fields).join(', ') : '—';
    const statusClass =
      r.status === 'UPDATED' ? 'text-green-700' :
      r.status === 'SKIPPED' ? 'text-gray-600' :
      r.status === 'NOT_FOUND' ? 'text-orange-700' :
      r.status === 'SOFT_DELETED' ? 'text-purple-700' :
      r.status === 'INVALID' ? 'text-red-700' : 'text-gray-700';

    const errText = (r.errors||[]).map(prettifyError).join('; ');

    tr.innerHTML = `
      <td class="p-2 border-b font-medium">${r.ma_so_hv || ''}</td>
      <td class="p-2 border-b ${statusClass}">
        ${r.status}${errText ? ' • ' + errText : ''}
      </td>
      <td class="p-2 border-b">${fields}</td>`;
    body.appendChild(tr);
  });

  // Tóm tắt phần đầu cũng “dịch” lỗi audit nếu có
  const hasAuditWarn = (resp.results||[]).some(x => (x.errors||[]).some(e => /write_audit\(\).*unexpected keyword argument/.test(e)));
  const extra = hasAuditWarn ? ' • ⚠️ Đã bỏ qua ghi nhật ký do phiên bản cũ (không ảnh hưởng tới dữ liệu).' : '';

  $('batchMsg').textContent =
    `Tổng: ${resp.total} • UPDATED: ${resp.updated} • SKIPPED: ${resp.skipped} • NOT_FOUND: ${resp.not_found} • SOFT_DELETED: ${resp.soft_deleted} • INVALID: ${resp.invalid}${extra}`;
}
// ======= EMAIL FEATURES (Preview-only + Template select + Inline-logo preview) =======

// Helper map template FE -> BE
function mapTplKey(t) {
  return (t || 'confirmation'); // 'confirmation' | 'student_card' | ...
}
// Tập chọn MSHV ở bảng
const selectedMSHV = new Set();

function updateBulkUI() {
  const count = selectedMSHV.size;
  const countEl = document.getElementById('bulkCount');
  const btnBulk = document.getElementById('btnSendBulk');
  if (countEl) countEl.textContent = String(count);
  if (btnBulk) {
    btnBulk.disabled = count === 0;
    btnBulk.classList.toggle('disabled:opacity-50', count === 0);
    btnBulk.classList.toggle('disabled:pointer-events-none', count === 0);
  }
}

function toggleSelectAll(on) {
  document.querySelectorAll('.rowChk').forEach(ch => {
    ch.checked = !!on;
    const id = decodeURIComponent(ch.dataset.mshv || '');
    if (id) { if (on) selectedMSHV.add(id); else selectedMSHV.delete(id); }
  });
  updateBulkUI();
}

document.addEventListener('change', (e) => {
  const chkAll = e.target.closest('#chkAll');
  if (chkAll) { toggleSelectAll(chkAll.checked); return; }

  const rowChk = e.target.closest('.rowChk');
  if (rowChk) {
    const id = decodeURIComponent(rowChk.dataset.mshv || '');
    if (!id) return;
    if (rowChk.checked) selectedMSHV.add(id); else selectedMSHV.delete(id);
    updateBulkUI();
  }
});

// ===== Modal helpers =====
function showEmailModal() {
  const overlay = document.getElementById('emailModal');
  if (!overlay) return console.warn('Missing #emailModal');
  overlay.classList.remove('hidden');
  overlay.classList.add('flex'); // center
}
function closeEmailModal() {
  const overlay = document.getElementById('emailModal');
  if (!overlay) return;
  overlay.classList.add('hidden');
  overlay.classList.remove('flex');
}
window.closeEmailModal = closeEmailModal;

// ===== Preview helpers (thay CID -> URL tĩnh cho khung xem trước) =====
function resolvePreviewCIDs(html) {
  const logoUrl = '/web/assets/logohutech_chu.png';
  return String(html || '')
    .replace(/src\s*=\s*["']cid:logohutech_chu\.png["']/gi, `src="${logoUrl}"`);
}

function renderPreview(html) {
  const iframe = document.getElementById('email_preview');
  if (!iframe) return;
  const body = resolvePreviewCIDs(html);
  iframe.srcdoc = `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{font-family:Arial,Helvetica,sans-serif;padding:16px;background:#fff;color:#111}
  img{max-width:100%;height:auto}
</style>
</head><body>${body||''}</body></html>`;
}

// ===== Mở modal gửi email (preview-only) =====
async function openEmailModal(mshv) {
  const em_to   = document.getElementById('email_to');
  const em_mshv = document.getElementById('email_mshv');
  const em_sub  = document.getElementById('email_subject');
  const em_html = document.getElementById('email_body');
  const chkAttach = document.getElementById('chk_attach');
  const chkA5     = document.getElementById('chk_a5');
  const linkView  = document.getElementById('view_attach');
  const selTpl    = document.getElementById('email_tpl');

  try {
    const rawTpl = (selTpl?.value || 'confirmation').trim();
    const tplKey = mapTplKey(rawTpl);            // giờ sẽ là 'confirmation' hoặc 'student_card'
    const a5on   = rawTpl === 'confirmation'; // chỉ khi là template Biên nhận HS mới có A5

    // nhật ký: mở nháp (log theo FE chọn cho dễ đọc)
    // journalTrack({
    //   action: 'EMAIL_DRAFT_OPEN',
    //   detail: { scope: 'SINGLE', mshv, tpl: rawTpl, a5: a5on }
    // });

    const r = await apiFetch(
      `/applicants/${encodeURIComponent(mshv)}/email-draft?a5=${a5on?'true':'false'}&tpl=${encodeURIComponent(tplKey)}`
    );
    if (!r || !r.ok) throw new Error(`Không tạo được bản nháp (HTTP ${r?.status||'???'})`);
    const draft = await r.json();

    em_to && (em_to.value   = draft.to_email || '');
    em_mshv && (em_mshv.value = mshv);
    em_sub && (em_sub.value  = draft.subject || '');
    em_html && (em_html.value = draft.html_body || '');
    if (chkA5) chkA5.checked = !!draft.a5;

    // ✅ “Đính kèm” chỉ bật nếu là Biên nhận HS
    if (chkAttach) chkAttach.checked = a5on;

    if (linkView) {
      if (a5on && draft.attachment_url) {
        linkView.classList.remove('hidden');
        linkView.href = draft.attachment_url;
        linkView.target = '_blank';
      } else {
        linkView.classList.add('hidden');
        linkView.removeAttribute('href');
        linkView.removeAttribute('target');
      }
    }

    renderPreview(draft.html_body);
    showEmailModal();

    if (selTpl && !selTpl._boundChange) {
      selTpl.addEventListener('change', async () => {
        const raw2  = (selTpl.value || 'confirmation').trim();
        const tpl2  = mapTplKey(raw2);
        const a5_2  = raw2 === 'confirmation';

        if (chkAttach) chkAttach.checked = a5_2;
        if (chkA5)     chkA5.checked     = a5_2;

        try {
          const r2 = await apiFetch(
            `/applicants/${encodeURIComponent(mshv)}/email-draft?a5=${a5_2?'true':'false'}&tpl=${encodeURIComponent(tpl2)}`
          );
          if (!r2 || !r2.ok) throw new Error(`Không tạo được bản nháp (HTTP ${r2?.status||'???'})`);
          const d2 = await r2.json();
          em_sub && (em_sub.value  = d2.subject || '');
          em_html && (em_html.value = d2.html_body || '');
          renderPreview(d2.html_body);

          if (linkView) {
            if (a5_2 && d2.attachment_url) {
              linkView.classList.remove('hidden');
              linkView.href = d2.attachment_url;
              linkView.target = '_blank';
            } else {
              linkView.classList.add('hidden');
              linkView.removeAttribute('href');
              linkView.removeAttribute('target');
            }
          }
        } catch (e) {
          showToast(e.message || 'Lỗi tải template', 'error');
        }
      });
      selTpl._boundChange = true;
    }
  } catch (e) {
    showToast(e.message || 'Lỗi tạo/ tải bản nháp email', 'error');
  }
} // <-- đóng hàm openEmailModal

// gắn nút ✉️ ở mỗi hàng
document.addEventListener('click', (e) => {
  const btnEmail = e.target.closest('.btn-email');
  if (!btnEmail) return;
  const mshv = decodeURIComponent(btnEmail.dataset.mshv || '');
  if (mshv) openEmailModal(mshv);
});

// Bắt click vào các nút xem chi tiết
document.addEventListener('click', (e) => {
  const btnDetail = e.target.closest('.link-detail');
  if (!btnDetail) return;
  const mshv = decodeURIComponent(btnDetail.dataset.mshv || '');
  if (!mshv) return;
  openDetailByMSHV(mshv);
});

// ===== Nút Gửi trong modal =====
async function sendEmail(){
  const mshv   = $('email_mshv')?.value.trim();
  const subj   = $('email_subject')?.value || '';
  const html   = $('email_body')?.value || '';
  const rawTpl = ($('email_tpl')?.value || 'confirmation').trim(); // 'confirmation' | 'student_card' | ...
  const tplKey = mapTplKey(rawTpl);
  const isHS   = (rawTpl === 'confirmation');                      // chỉ Biên nhận HS mới có A5/đính kèm
  const attach = isHS ? !!$('chk_attach')?.checked : false;

  const to   = $('email_to')?.value || '';
  const msgEl = $('msg');

  // 🟡 1. Báo trạng thái "đang gửi"
  if (msgEl) {
    msgEl.textContent = `📨 Đang gửi email tới ${to || 'học viên'} (MSHV ${mshv})...`;
  }
  showToast('Đang gửi email, vui lòng đợi...', 'info', 2000);

  try {
    const path = `/applicants/${encodeURIComponent(mshv)}/send-email?tpl=${encodeURIComponent(tplKey)}&a5=${isHS?'true':'false'}`;
    const r = await apiFetch(path, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ subject: subj, html_body: html, attach_receipt: attach })
    });

    if (!r || !r.ok){
      let msg = `Gửi thất bại (HTTP ${r?.status||'???'})`;
      try { const t = await r.text(); const j = JSON.parse(t); if (j?.detail) msg = j.detail; } catch {}
      throw new Error(msg);
    }

    // Ghi journal đúng biến
    await journalTrack({
      action: 'EMAIL_SENT',
      detail: { scope:'SINGLE', mshv, subject:subj, tpl: rawTpl, attach, a5: isHS, status:'OK' }
    });

    // 🟢 2. Báo đã gửi thành công
    if (msgEl) {
      msgEl.textContent = `✅ Đã gửi email tới ${to || 'học viên'} (MSHV ${mshv})`;
    }
    showToast('✅ Đã gửi email thành công', 'success', 2600);

    closeEmailModal();
  } catch(e){
    // 🔴 3. Báo lỗi
    if (msgEl) {
      msgEl.textContent = `❌ Gửi email thất bại${mshv ? ` (MSHV ${mshv})` : ''}: ${e.message || ''}`;
    }
    showToast(e.message || 'Lỗi gửi email', 'error', 2800);
  }
}
window.sendEmail = sendEmail;

// ===== Email hàng loạt (bulk) =====
// Modal bulk helpers
function showBulkModal(){ const o=$('bulkEmailModal'); if(!o) return; o.classList.remove('hidden'); o.classList.add('flex'); }
function closeBulkModal(){ const o=$('bulkEmailModal'); if(!o) return; o.classList.add('hidden'); o.classList.remove('flex'); }
window.closeBulkModal = closeBulkModal;

// Render preview hàng loạt
function renderBulkPreviewHTML(html) {
  const iframe = $('bulk_preview');
  if (!iframe) return;
  const body = resolvePreviewCIDs(html);
  iframe.srcdoc = `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:Arial,Helvetica,sans-serif;padding:16px;background:#fff;color:#111}img{max-width:100%;height:auto}</style>
</head><body>${body||''}</body></html>`;
}

// Nút “Gửi email hàng loạt” -> mở preview
$('btnSendBulk')?.addEventListener('click', async ()=>{
  const list = [...selectedMSHV];
  if (!list.length) { alert('Chưa chọn học viên nào.'); return; }

  // Đọc template đang chọn ở modal đơn (reuse)
  const rawTpl = (document.getElementById('email_tpl')?.value || 'confirmation').trim(); // FE
  const tplKey = mapTplKey(rawTpl);                                                      // BE
  const a5     = rawTpl === 'confirmation'; // Chỉ biên nhận HS mới cần A5/đính kèm
  const first  = list[0];

  try {
    // Lấy nháp có kèm tpl + a5 (map key khi gọi BE)
    const r = await apiFetch(
      `/applicants/${encodeURIComponent(first)}/email-draft?a5=${a5?'true':'false'}&tpl=${encodeURIComponent(tplKey)}`
    );
    if (!r || !r.ok) {
      let msg = `Không lấy được bản nháp (HTTP ${r?.status||'???'})`;
      try { const t = await r.text(); const j = JSON.parse(t); if (j?.detail) msg = j.detail; } catch {}
      throw new Error(msg);
    }
    const draft = await r.json();

    // fill UI
    $('bulkCountLabel').textContent = String(list.length);
    $('bulkListLabel').textContent  = list.join(', ');
    $('bulk_subject').value         = draft.subject || '';
    renderBulkPreviewHTML(draft.html_body);

    // Đổ dropdown chọn người xem mẫu + bind change (kèm tpl)
    const sel = $('bulkPreviewSelect');
    if (sel) {
      sel.innerHTML = list.map(id => `<option value="${id}">${id}</option>`).join('');
      sel.value = first;

      if (!sel._boundChange) {
        sel.addEventListener('change', async () => {
          const id = sel.value;
          try {
            const r3 = await apiFetch(
              `/applicants/${encodeURIComponent(id)}/email-draft?a5=${a5?'true':'false'}&tpl=${encodeURIComponent(tplKey)}`
            );
            if (!r3 || !r3.ok) {
              let msg = `Không lấy được bản nháp (HTTP ${r3?.status||'???'})`;
              try { const t = await r3.text(); const j = JSON.parse(t); if (j?.detail) msg = j.detail; } catch {}
              throw new Error(msg);
            }
            const d3 = await r3.json();
            renderBulkPreviewHTML(d3.html_body);
          } catch (e) {
            showToast(e.message || 'Lỗi tải mẫu xem trước', 'error');
          }
        });
        sel._boundChange = true;
      }
    }

      // Bind nút “Gửi” (chọn endpoint theo FE selection)
    const btn = $('bulkSendBtn');
    btn.onclick = async ()=>{
      const ids = [...selectedMSHV];
      const subject = $('bulk_subject').value;
      const msgEl = $('msg');

      // 🟡 1. Báo đang gửi hàng loạt
      if (msgEl) {
        msgEl.textContent = `📨 Đang gửi email cho ${ids.length} học viên...`;
      }
      showToast('Đang gửi email hàng loạt, vui lòng đợi...', 'info', 2200);

      btn.disabled = true;
      try{
        const rawTpl = ($('email_tpl')?.value || 'confirmation').trim();
        const tplKey = mapTplKey(rawTpl);
        const a5 = rawTpl === 'confirmation';

        const r2 = await apiFetch(`/applicants/send-email-batch?tpl=${encodeURIComponent(tplKey)}`, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ ma_so_hv_list: ids, subject, a5 })
        });
        if (!r2 || !r2.ok){
          let msg = `Batch gửi thất bại (HTTP ${r2?.status||'???'})`;
          try { const t = await r2.text(); const j = JSON.parse(t); if (j?.detail) msg = j.detail; } catch {}
          throw new Error(msg);
        }

        await journalTrack({
          action: 'EMAIL_SENT',
          detail: { scope: 'BATCH', count: ids.length, sample: ids.slice(0, 10), subject, tpl: rawTpl, a5, status: 'OK' }
        });

        // 🟢 2. Báo xong hàng loạt
        if (msgEl) {
          msgEl.textContent = `✅ Đã gửi email cho ${ids.length} học viên.`;
        }
        showToast('✅ Đã gửi email hàng loạt thành công.', 'success', 2800);
        closeBulkModal();
      }catch(e){
        if (msgEl) {
          msgEl.textContent = `❌ Gửi email hàng loạt thất bại: ${e.message || ''}`;
        }
        showToast(e.message || 'Lỗi batch gửi', 'error');
      } finally { btn.disabled = false; }
    };
    // mở modal sau khi chuẩn bị xong
    showBulkModal();
  } catch (e) {
    showToast(e.message || 'Lỗi chuẩn bị email hàng loạt', 'error');
  }
});
// ===== Sidebar user dropdown + mở modal logout =====
(function menuSetup(){
  const btn  = document.getElementById('userMenuBtn');
  const menu = document.getElementById('userMenu');
  if (!btn || !menu) return;

  function openMenu(on){
    if (on) menu.classList.add('show'); else menu.classList.remove('show');
    btn.setAttribute('aria-expanded', String(on));
  }

  btn.addEventListener('click', (e)=>{
    e.stopPropagation();
    openMenu(!menu.classList.contains('show'));
  });

  document.addEventListener('click', ()=>{
    if (menu.classList.contains('show')) openMenu(false);
  });
  document.addEventListener('keydown', (e)=>{
    if (e.key === 'Escape') openMenu(false);
  });

  // Nút "Đăng xuất" trong dropdown gọi modal
  document.getElementById('btnMenuLogout')?.addEventListener('click', ()=>{
    openMenu(false);
    if (typeof window.openLogout === 'function') {
      window.openLogout();
    }
  });
})();

// Nút mở trang Sửa hồ sơ
detailOpenEditBtn?.addEventListener('click', () => {
  if (!currentDetailMSHV) return;
  // Dùng COMPOSE_BASE đã detect sẵn
  location.href = `${COMPOSE_BASE}?mshv=${encodeURIComponent(currentDetailMSHV)}&action=edit`;
});

// Nút In A5 / A4 (reuse logic hiện tại)
detailPrintA5Btn?.addEventListener('click', async () => {
  if (!currentDetailMSHV) return;
  await journalTrack({
    action: 'PRINT_IN',
    detail: { scope:'SINGLE', filters:{ mshv: currentDetailMSHV }, name_mode:'A5', count:1 }
  });
  await openPdfOrAlert(`/print/a5/${encodeURIComponent(currentDetailMSHV)}`);
});

detailPrintA4Btn?.addEventListener('click', async () => {
  if (!currentDetailMSHV) return;
  await journalTrack({
    action: 'PRINT_IN',
    detail: { scope:'SINGLE', filters:{ mshv: currentDetailMSHV }, name_mode:'A4', count:1 }
  });
  await openPdfOrAlert(`/print/a4/${encodeURIComponent(currentDetailMSHV)}`);
});

function showLoading(msg = "Đang tải dữ liệu, vui lòng đợi...") {
  const box = document.getElementById("globalLoading");
  if (!box) return;
  box.classList.remove("hidden");
  box.querySelector("div div:last-child").textContent = msg;
}

function hideLoading() {
  const box = document.getElementById("globalLoading");
  if (!box) return;
  box.classList.add("hidden");
}
// Nút In Email Receipt
document.getElementById('detailPrintA4Btn')?.addEventListener('click', async () => {
  if (!currentDetailMSHV) return;
  await journalTrack({
    action: 'PRINT_IN',
    detail: { scope:'SINGLE', filters:{ mshv: currentDetailMSHV }, name_mode:'A4', count:1 }
  });
  await openPdfOrAlert(`/print/a4/${encodeURIComponent(currentDetailMSHV)}`);
});
// Nút In Email Receipt
document.getElementById('detailPrintPostalBtn')?.addEventListener('click', async () => {
  if (!currentDetailMSHV) return;
  await journalTrack({
    action: 'PRINT_IN',
    detail: { scope:'SINGLE', filters:{ mshv: currentDetailMSHV }, name_mode:'POSTAL', count:1 }
  });
  await openPdfOrAlert(`/applicants/${encodeURIComponent(currentDetailMSHV)}/postal-print`);
});
// Nút In biên nhận Email (A5)
document.getElementById('detailPrintEmailReceiptBtn')?.addEventListener('click', async () => {
  if (!currentDetailMSHV) return;
  await journalTrack({
    action: 'PRINT_IN',
    detail: { scope:'SINGLE', filters:{ mshv: currentDetailMSHV }, name_mode:'EMAIL', count:1 }
  });
  await openPdfOrAlert(`/applicants/print/email-receipt/${encodeURIComponent(currentDetailMSHV)}`);
});



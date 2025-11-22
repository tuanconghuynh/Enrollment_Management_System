 /* ===== Helpers chung ===== */
  async function api(path, opt = {}) {
    try {
      return await fetch('/api' + path, { credentials: 'include', ...opt });
    } catch (e) {
      console.error('API error:', e);
      return null;
    }
  }

  function showToast(msg,type='info',ms=3200){
    const wrap=document.getElementById('toast-wrap'); if(!wrap) return alert(msg);
    const el=document.createElement('div'); el.className=`toast ${type}`; el.textContent=String(msg);
    wrap.appendChild(el); requestAnimationFrame(()=>el.classList.add('show'));
    const close=()=>{ el.classList.remove('show'); el.addEventListener('transitionend',()=>el.remove(),{once:true}); };
    const t=setTimeout(close,ms); el.addEventListener('click',()=>{clearTimeout(t); close();});
  }

  /* ===== Dropdown menu ===== */
  (function menuSetup(){
    const btn = document.getElementById('userMenuBtn');
    const menu = document.getElementById('userMenu');
    if(!btn || !menu) return;
    function openMenu(on){ menu.classList.toggle('show', on); btn.setAttribute('aria-expanded', String(on)); }
    btn.addEventListener('click', (e)=>{ e.stopPropagation(); openMenu(!menu.classList.contains('show')); });
    document.addEventListener('click', ()=> menu.classList.contains('show') && openMenu(false));
    document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') openMenu(false); });
    document.getElementById('btnMenuLogout')?.addEventListener('click', ()=>{ openMenu(false); openLogout(); });
  })();

  /* ===== Modal logout ===== */
  (function(){
    const wrap = document.getElementById('logoutModal');
    const box  = document.getElementById('logoutBox');
    const ok   = document.getElementById('lgOK');
    const cxl  = document.getElementById('lgCancel');
    const x    = document.getElementById('lgClose');
    let last=null;
    function open(){ last=document.activeElement; wrap.classList.add('show'); requestAnimationFrame(()=>box.focus()); document.body.classList.add('overflow-hidden'); }
    function close(){ wrap.classList.remove('show'); document.body.classList.remove('overflow-hidden'); last?.focus?.(); }
    function trap(e){
      if(e.key!=='Tab') return;
      const f=box.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
      if(!f.length) return;
      const first=f[0], last=f[f.length-1];
      if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
      else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); }
    }
    window.openLogout=open;
    ok.addEventListener('click', async ()=>{ try{ await api('/logout',{method:'POST'});}catch{} location.href='/auth_login.html'; });
    cxl.addEventListener('click', close); x.addEventListener('click', close);
    wrap.addEventListener('click', e=>{ if(e.target===wrap) close(); });
    box.addEventListener('keydown', trap);
  })();

  /* ===== Boot (load /me) ===== */
  async function boot(){
    const r = await api('/me');
    if (!r || !r.ok) { location.href = '/auth_login.html'; return; }
    const me = await r.json();
    const name = me.full_name || me.username || 'Người dùng';
    (document.getElementById('helloName')||{}).textContent = name;
    (document.getElementById('helloRole')||{}).textContent = me.role || '';
    (document.getElementById('dashName')||{}).textContent  = name;

    if (me.must_change_password) {
      location.href = '/account?first=1';
      return;
    }
  }
  boot();

  /* ================== HÀM VẼ DASHBOARD GỐC =================== */

  function updateTopCards(total, majors, done, pending) {
    document.getElementById("countTotal").textContent   = String(total);
    document.getElementById("countMajors").textContent  = String(majors);
    document.getElementById("countDone").textContent    = String(done);
    document.getElementById("countPending").textContent = String(pending);
  }

  function renderMajorsTooltip(majorCounts) {
    const tip = document.getElementById("majorsTooltip");
    if (!tip) return;

    const entries = Object.entries(majorCounts || {});

    if (!entries.length) {
      tip.innerHTML = '<div class="text-gray-500 text-xs">Chưa có dữ liệu ngành.</div>';
      return;
    }

    entries.sort((a, b) => a[0].localeCompare(b[0], 'vi'));

    tip.innerHTML = `
      <div class="text-xs text-gray-500 mb-2">
        Chi tiết số lượng hồ sơ theo ngành:
      </div>
      <div class="max-h-72 overflow-auto space-y-1">
        ${entries.map(([name, count]) => `
          <div class="flex items-center justify-between gap-2">
            <span class="truncate" title="${name}">${name}</span>
            <span class="font-semibold tabular-nums">${count}</span>
          </div>
        `).join('')}
      </div>
    `;
  }

  function renderDoneTooltip(statsByMajor) {
    const tip = document.getElementById("doneTooltip");
    if (!tip) return;

    const entries = Object.entries(statsByMajor || {});
    const havingDone = entries.filter(([_, s]) => (s.done || 0) > 0);

    if (!havingDone.length) {
      tip.innerHTML = '<div class="text-gray-500 text-xs">Chưa có ngành nào được xử lý hồ sơ.</div>';
      return;
    }

    havingDone.sort((a, b) => (b[1].done || 0) - (a[1].done || 0));

    tip.innerHTML = `
      <div class="text-xs text-gray-500 mb-2">
        Chi tiết hồ sơ <b>đã xử lý</b> theo ngành:
      </div>
      <div class="max-h-72 overflow-auto space-y-1">
        ${havingDone.map(([name, s]) => {
          const total = s.total || 0;
          const done  = s.done || 0;
          const rate  = total ? Math.round(done * 1000 / total) / 10 : 0;
          return `
            <div class="flex flex-col gap-0.5">
              <div class="flex items-center justify-between gap-2">
                <span class="truncate" title="${name}">${name}</span>
                <span class="font-semibold tabular-nums">${done}/${total}</span>
              </div>
              <div class="text-[11px] text-gray-500 text-right">
                Đã xử lý ~ <span class="font-semibold">${rate}%</span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  function renderMajorStatsTable(statsByMajor) {
    const body = document.getElementById("majorStatsBody");
    if (!body) return;

    const entries = Object.entries(statsByMajor || {});
    if (!entries.length) {
      body.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-gray-500 py-3">
            Chưa có dữ liệu hồ sơ.
          </td>
        </tr>
      `;
      return;
    }

    entries.sort((a, b) => (b[1].total || 0) - (a[1].total || 0));

    body.innerHTML = entries.map(([name, s], idx) => {
      const total   = s.total || 0;
      const done    = s.done || 0;
      const pending = total - done;
      const rate    = total ? Math.round(done * 1000 / total) / 10 : 0;
      return `
        <tr class="${idx % 2 ? 'bg-slate-50/60' : ''}">
          <td class="px-3 py-2 border-b text-gray-500 text-center">${idx + 1}</td>
          <td class="px-3 py-2 border-b text-gray-800 text-left">
            <span title="${name}">${name}</span>
          </td>
          <td class="px-3 py-2 border-b text-center tabular-nums">${total}</td>
          <td class="px-3 py-2 border-b text-center tabular-nums text-green-700 font-semibold">${done}</td>
          <td class="px-3 py-2 border-b text-center tabular-nums text-amber-700">${pending}</td>
          <td class="px-3 py-2 border-b text-center tabular-nums">
            ${total ? rate.toFixed(1) : '0.0'}%
          </td>
        </tr>
      `;
    }).join('');

  }

  /* ================= DASHBOARD + FILTER ================= */

  // Lưu toàn bộ applicants để filter lại theo khoá/đợt trên client
  let ALL_APPLICANTS = [];

  function uniqueSorted(arr) {
    return [...new Set(arr)].sort((a, b) => {
      const na = Number(a), nb = Number(b);
      if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
      return String(a).localeCompare(String(b), 'vi');
    });
  }

  function fillSelectOptions(selectEl, values, labelAll) {
    if (!selectEl) return;
    const opts = ['<option value="">' + (labelAll || 'Tất cả') + '</option>']
      .concat(values.map(v => `<option value="${v}">${v}</option>`));
    selectEl.innerHTML = opts.join('');
  }

    // ===== Helper lấy Niên khóa / Đợt từ object applicant =====
  function getNienKhoa(a) {
    return (
      a?.nien_khoa ??
      a?.khoa ??
      a?.khoa_hoc ??
      a?.khoa_hv ??
      ''
    ).toString().trim();
  }

  function getDot(a) {
    return (
      a?.dot ??
      a?.dot_nhap ??
      a?.dot_nhap_hoc ??
      a?.dot_tuyen_sinh ??
      ''
    ).toString().trim();
  }

  function buildFilterOptions(rebuildKhoa = true) {
    const selKhoa = document.getElementById('filterKhoa');
    const selDot  = document.getElementById('filterDot');
    if (!selKhoa || !selDot) return;

    const all = ALL_APPLICANTS || [];

    // Lưu lại lựa chọn hiện tại
    const oldKhoa = selKhoa.value;
    const oldDot  = selDot.value;

    // ----- 1. Build list NIÊN KHOÁ (nếu cần) -----
    if (rebuildKhoa) {
      const listKhoa = uniqueSorted(
        all
          .map(a => getNienKhoa(a))
          .filter(v => v !== '')
      );
      fillSelectOptions(selKhoa, listKhoa, 'Tất cả');

      // cố gắng giữ lại lựa chọn cũ nếu vẫn tồn tại
      if (oldKhoa && listKhoa.includes(oldKhoa)) {
        selKhoa.value = oldKhoa;
      } else {
        selKhoa.value = ""; // mặc định "Tất cả"
      }
    }

    // ----- 2. Build list ĐỢT theo khoá đang chọn -----
    const currentKhoa = selKhoa.value;
    const filteredForDot = currentKhoa
      ? all.filter(a => getNienKhoa(a) === currentKhoa)
      : all;

    const listDot = uniqueSorted(
      filteredForDot
        .map(a => getDot(a))
        .filter(v => v !== '')
    );
    fillSelectOptions(selDot, listDot, 'Tất cả');

    // giữ lại đợt cũ nếu còn
    if (oldDot && listDot.includes(oldDot)) {
      selDot.value = oldDot;
    } else {
      selDot.value = "";
    }
  }

  function computeStats(list) {
    const statsByMajor = {};
    let totalDone = 0;

    for (const a of list) {
      let m = (a.nganh_nhap_hoc || "").trim();
      if (!m) m = "Chưa chọn ngành";

      if (!statsByMajor[m]) {
        statsByMajor[m] = { total: 0, done: 0 };
      }
      statsByMajor[m].total++;

      const hasCode = a.ma_ho_so && String(a.ma_ho_so).trim() !== "";
      if (hasCode) {
        statsByMajor[m].done++;
        totalDone++;
      }
    }

    const total   = list.length;
    const pending = total - totalDone;
    const majorsCount = Object.keys(statsByMajor).filter(k => k !== "Chưa chọn ngành").length;

    return { statsByMajor, total, totalDone, pending, majorsCount };
  }

  function applyFilterAndRender() {
    const selKhoa = document.getElementById('filterKhoa');
    const selDot  = document.getElementById('filterDot');
    const summary = document.getElementById('filterSummary');

    const k = selKhoa ? selKhoa.value.trim() : "";
    const d = selDot ? selDot.value.trim() : "";

    let filtered = ALL_APPLICANTS;
    if (!Array.isArray(filtered)) filtered = [];

    filtered = filtered.filter(a => {
      const okK = !k || getNienKhoa(a) === k;
      const okD = !d || getDot(a)      === d;
      return okK && okD;
    });


    const { statsByMajor, total, totalDone, pending, majorsCount } = computeStats(filtered);

    updateTopCards(total, majorsCount, totalDone, pending);

    const majorTotals = {};
    for (const [name, s] of Object.entries(statsByMajor)) {
      majorTotals[name] = s.total;
    }

    renderMajorsTooltip(majorTotals);
    renderDoneTooltip(statsByMajor);
    renderMajorStatsTable(statsByMajor);

    if (summary) {
      if (!k && !d) summary.textContent = 'Đang xem: tất cả khóa/đợt';
      else {
        summary.textContent = `Đang xem: ${
          k ? ('Khóa ' + k) : 'tất cả khóa'
        }, ${
          d ? ('Đợt ' + d) : 'tất cả đợt'
        }`;
      }
    }
  }

  async function loadDashboardStats() {
    try {
      const PAGE_SIZE = 500;
      let page = 1;
      let all = [];

      while (true) {
        const res = await api(`/applicants/search?page=${page}&size=${PAGE_SIZE}`);
        if (!res || !res.ok) {
          console.warn('Stop fetching at page', page, 'status =', res && res.status);
          break;
        }

        const js = await res.json();
        const items = Array.isArray(js.items) ? js.items
                     : Array.isArray(js.results) ? js.results
                     : Array.isArray(js.data) ? js.data
                     : Array.isArray(js) ? js
                     : [];
        if (!items.length) break;

        all = all.concat(items);
        if (items.length < PAGE_SIZE) break;
        page++;
      }

      console.log('Dashboard applicants loaded:', all.length);
      ALL_APPLICANTS = all;

      if (!ALL_APPLICANTS.length) {
        updateTopCards(0, 0, 0, 0);
        renderMajorsTooltip({});
        renderDoneTooltip({});
        renderMajorStatsTable({});
        return;
      }

      buildFilterOptions(true);  // build cả Khoa + Đợt lần đầu
      applyFilterAndRender();

    } catch (err) {
      console.error("Lỗi dashboard:", err);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const selKhoa = document.getElementById('filterKhoa');
    const selDot  = document.getElementById('filterDot');
    const btnClear = document.getElementById('btnClearFilter');

    if (selKhoa) {
      selKhoa.addEventListener('change', () => {
        // chỉ cần build lại ĐỢT, giữ nguyên giá trị KHOÁ vừa chọn
        buildFilterOptions(false);
        applyFilterAndRender();
      });
    }

    if (selDot) {
      selDot.addEventListener('change', () => {
        applyFilterAndRender();
      });
    }
    if (btnClear) {
      btnClear.addEventListener('click', () => {
        if (selKhoa) selKhoa.value = "";
        if (selDot)  selDot.value  = "";
        buildFilterOptions(true);   // về lại tất cả khóa/đợt
        applyFilterAndRender();
      });
    }

  });

  // Gọi dashboard
  loadDashboardStats();

    /* ===== Login thành công -> toast ===== */
  (function () {
    // kiểm tra cookie báo login thành công
    const hasLoginCookie = document.cookie
      .split(';')
      .some(c => c.trim().startsWith('__login_success=1'));

    if (hasLoginCookie) {
      if (typeof showToast === 'function') {
        showToast('Đăng nhập thành công ✅', 'success', 3500);
      }

      // xoá cookie để chỉ hiện 1 lần
      document.cookie = '__login_success=; Max-Age=0; Path=/; SameSite=Lax';
    }
  })();

/* API 价格表：统一规格横向比较各厂商报价。
   数据只有 35 款有定价，页面只展示有价模型；缺失值写「—」并解释。 */
(function () {
  'use strict';
  var R = window.MRank;
  var state = {
    key: 'priceIn', dir: 1,
    query: '',
    filters: { region: [], source: [], cache: [] }
  };

  function pricedModels() {
    return R.getModels().filter(function (m) {
      return m.priceIn != null || m.priceOut != null;
    });
  }

  function filtered() {
    var list = pricedModels();
    var f = state.filters;
    if (f.region.length) {
      list = list.filter(function (m) { return f.region.indexOf(m.region) > -1; });
    }
    if (f.source.length) {
      list = list.filter(function (m) { return f.source.indexOf(m.priceSource) > -1; });
    }
    if (f.cache.length) {
      list = list.filter(function (m) { return m.priceCacheHit != null; });
    }
    var q = state.query.trim().toLowerCase();
    if (q) {
      list = list.filter(function (m) {
        return (m.name || '').toLowerCase().indexOf(q) > -1
          || (m.provider || '').toLowerCase().indexOf(q) > -1
          || (m.id || '').toLowerCase().indexOf(q) > -1;
      });
    }
    var k = state.key, dir = state.dir;
    return list.sort(function (a, b) {
      var av, bv;
      if (k === 'context') {
        av = a.context || 0; bv = b.context || 0;
      } else {
        av = R.priceToCny(a, k); bv = R.priceToCny(b, k);
        if (av == null) av = Infinity * dir;  /* 缺失排最后 */
        if (bv == null) bv = Infinity * dir;
      }
      return dir > 0 ? av - bv : bv - av;
    });
  }

  function cellPrice(m, field) {
    if (m[field] == null) return '<span class="price-missing" title="未收录官方定价：不代表免费">—</span>';
    /* 海外模型保留官方美元价：折算 ¥ 用于统一比较，原币括注避免失真 */
    var usd = (m.priceCurrency !== 'CNY' && m[field] !== 0)
      ? '<span class="price-usd" title="厂商官方美元报价">$' + (+m[field]).toFixed(2) + '</span>'
      : '';
    return R.priceCell(m, field) + usd;
  }

  function render() {
    var list = filtered();
    var tbody = document.getElementById('priceBody');
    document.getElementById('matchHint').textContent =
      list.length + ' / ' + pricedModels().length + ' 款有定价模型';
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">没有匹配的模型</td></tr>';
      return;
    }
    tbody.innerHTML = list.map(function (m) {
      var note = m.priceNote
        ? '<div class="p-note" title="' + R.esc(m.priceNote) + '">' + R.esc(m.priceNote) + '</div>'
        : '';
      var cache = m.priceCacheHit != null
        ? R.priceCell(m, 'priceCacheHit')
        : '<span class="price-missing" title="未收录缓存命中价：仅官网直采模型有该字段">—</span>';
      return '<tr>'
        + '<td><a href="model.html?id=' + encodeURIComponent(m.id) + '">' + R.esc(m.name) + '</a>'
        + '<div class="mprov">' + R.esc(m.provider) + '</div>' + note + '</td>'
        + '<td class="num">' + R.fmtCtx(m.context) + '</td>'
        + '<td class="num">' + cellPrice(m, 'priceIn') + '</td>'
        + '<td class="num">' + cellPrice(m, 'priceOut') + '</td>'
        + '<td class="num">' + cache + '</td>'
        + '<td class="num">' + R.esc(R.priceDateText(m)) + '</td>'
        + '<td>' + (m.priceSource === '官网'
            ? '<span class="src-official" title="直采自厂商官方定价页">官网</span>'
            : '<span class="src-sc" title="SuperCLUE 价格库">价格表</span>') + '</td>'
        + '</tr>';
    }).join('');
  }

  function renderFreshness() {
    var meta = R.getMeta();
    var el = document.getElementById('dataFreshness');
    if (!el || !meta) return;
    var priced = pricedModels();
    /* 按来源分组，取各组自身模型的核验月（混源时单一全站日期会失真） */
    var official = priced.filter(function (m) { return m.priceSource === '官网'; });
    var fromTable = priced.filter(function (m) { return m.priceSource !== '官网'; });
    function groupDate(list) {
      var count = {};
      list.forEach(function (m) {
        var d = R.priceDateText(m);
        count[d] = (count[d] || 0) + 1;
      });
      var best = null, n = 0;
      Object.keys(count).forEach(function (d) {
        if (count[d] > n) { n = count[d]; best = d; }
      });
      return best;
    }
    var cov = R.priceCoverage();
    var items = [];
    if (official.length) {
      items.push({ label: '官网直采 ' + official.length + ' 款', date: groupDate(official) });
    }
    if (fromTable.length) {
      items.push({ label: '价格表 ' + fromTable.length + ' 款', date: groupDate(fromTable), stale: true });
    }
    items.push({ label: '有定价模型', date: cov.priced + ' / ' + cov.total + ' 款' });
    var html = items.map(function (it) {
      return '<span class="df-item">' + R.esc(it.label) + ' <b>' + R.esc(it.date) + '</b>'
        + (it.stale ? '<span class="df-mark" aria-hidden="true">※</span>' : '') + '</span>';
    });
    el.innerHTML = '各来源价格核验时间不同：' + html.join('<span class="df-sep">·</span>')
      + '<span class="df-hint" title="快照日期不代表每款模型价格都更新到同一天">什么是快照日？</span>';
    el.hidden = false;
  }

  function applyFiltersUI() {
    document.querySelectorAll('.filter-chip').forEach(function (chip) {
      var f = chip.getAttribute('data-filter');
      var v = chip.getAttribute('data-value');
      var on = f === 'cache'
        ? state.filters.cache.length > 0
        : state.filters[f].indexOf(v) > -1;
      chip.classList.toggle('on', on);
      chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    var clearBtn = document.getElementById('filterClear');
    if (clearBtn) clearBtn.hidden = (state.filters.region.length === 0
      && state.filters.source.length === 0 && state.filters.cache.length === 0
      && !state.query);
  }

  function bind() {
    document.getElementById('searchBox').addEventListener('input', function (e) {
      state.query = e.target.value;
      render();
      applyFiltersUI();
    });
    document.querySelectorAll('.filter-chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var f = chip.getAttribute('data-filter');
        var v = chip.getAttribute('data-value');
        if (f === 'cache') {
          state.filters.cache = state.filters.cache.length ? [] : ['1'];
        } else {
          var arr = state.filters[f];
          var i = arr.indexOf(v);
          if (i > -1) arr.splice(i, 1); else arr.push(v);
        }
        render();
        applyFiltersUI();
      });
    });
    var clearBtn = document.getElementById('filterClear');
    if (clearBtn) clearBtn.addEventListener('click', function () {
      state.filters = { region: [], source: [], cache: [] };
      state.query = '';
      document.getElementById('searchBox').value = '';
      render();
      applyFiltersUI();
    });
    document.querySelectorAll('#priceTable th.sortable').forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.getAttribute('data-key');
        if (state.key === k) { state.dir = -state.dir; }
        else { state.key = k; state.dir = 1; }
        document.querySelectorAll('#priceTable th.sortable').forEach(function (t) {
          t.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(state.dir > 0 ? 'sort-asc' : 'sort-desc');
        render();
      });
    });
    /* nav 折叠（与其他页面一致） */
    var toggle = document.querySelector('.nav-toggle');
    if (toggle) toggle.addEventListener('click', function () {
      var nav = document.querySelector('.nav nav');
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  R.loadData().then(function () {
    var meta = R.getMeta();
    document.getElementById('pricedCount').textContent = R.priceCoverage().priced;
    document.getElementById('officialCount').textContent =
      pricedModels().filter(function (m) { return m.priceSource === '官网'; }).length;
    var footDate = document.getElementById('footDate');
    if (footDate) footDate.textContent = meta.updated;
    /* 默认按输入价升序：与「输入价最低」语义一致 */
    var th = document.querySelector('#priceTable th[data-key="priceIn"]');
    if (th) th.classList.add('sort-asc');
    bind();
    applyFiltersUI();
    render();
    renderFreshness();
  });
})();

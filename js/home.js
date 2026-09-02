/* 首页（总览）逻辑：Top 3 / 本周变化 / 关键冠军卡片 */
  /* eslint-disable no-var */
(function () {
  'use strict';
  var R = window.MRank;

  /* 本周竞技场 Top 3 大卡片 */
  function renderTop3() {
    var list = R.getModels().slice()
      .sort(function (a, b) { return (b.elo || 0) - (a.elo || 0); })
      .slice(0, 3);
    var meta = list.length ? '快照 ' + R.getMeta().updated : '暂无数据';
    document.getElementById('top3Meta').textContent = meta;
    var grid = document.getElementById('top3Grid');
    grid.innerHTML = list.map(function (m, i) {
      var rank = i + 1, rcls = 'r' + rank;
      return '<a class="top3-item ' + rcls + '" href="model.html?id=' + R.esc(m.id) + '">'
        + '<div class="top3-medal">' + rank + '</div>'
        + '<div class="top3-info">'
        +   '<div class="top3-rank">NO.' + rank + '</div>'
        +   '<div class="top3-name">' + R.esc(m.name) + '</div>'
        +   '<div class="top3-meta">' + R.esc(m.provider || '–') + ' · ' + R.esc(R.regionName(m.region)) + '</div>'
        + '</div>'
        + '<div class="top3-elo">' + (m.elo || '–') + '<small>Elo</small></div>'
        + '</a>';
    }).join('');
  }

  /* 「关键冠军 4 卡片」：竞技场 Elo / 中文能力 / 输入价最低 / 上下文最大，点击跳转完整榜单对应排序 */
  function renderKpi() {
    var models = R.getModels();
    var pickBy = function (key, dir) {
      return models.filter(function (m) { return m[key] != null; })
        .reduce(function (best, m) {
          if (!best) return m;
          return dir > 0 ? (m[key] < best[key] ? m : best) : (m[key] > best[key] ? m : best);
        }, null);
    };
    var fmtPrice = function (v) { return v == null ? '–' : '¥' + v.toFixed(2); };
    var fmtCtx = function (v) {
      if (v == null) return '–';
      if (v >= 10000) return (v / 10000).toFixed(0) + '万';
      return v.toLocaleString('zh-CN');
    };
    var cards = [
      { label: '竞技场 Elo 第一',   pick: pickBy('elo', -1),       val: function (m) { return m.elo; },       unit: 'Elo',     tab: 'elo' },
      { label: '综合能力第一',       pick: pickBy('bench', -1),    val: function (m) { return R.fmtBench(m.bench); }, unit: '分', tab: 'bench' },
      { label: '中文能力第一',        pick: pickBy('superclue', -1), val: function (m) { return m.superclue; }, unit: '分',      tab: 'superclue' },
      { label: '输入价最低',         pick: pickBy('priceIn', 1),   val: function (m) { return fmtPrice(m.priceIn); }, unit: '/ 百万tok', tab: 'priceIn' },
      { label: '上下文最长',         pick: pickBy('context', -1),  val: function (m) { return fmtCtx(m.context); }, unit: 'tokens', tab: 'context' }
    ];
    var grid = document.getElementById('kpiSection');
    grid.innerHTML = cards.map(function (c) {
      if (!c.pick) return '';
      var m = c.pick, v = c.val(m);
      return '<div class="card kpi-card kpi" data-tab="' + c.tab + '">'
        + '<a href="model.html?id=' + R.esc(m.id) + '">'
        + '<div class="kpi-label">' + c.label + '</div>'
        + '<div class="kpi-num">' + (typeof v === 'number' ? v : R.esc(String(v))) + '<span class="kpi-unit"> ' + c.unit + '</span></div>'
        + '<div class="kpi-name">' + R.esc(m.name) + '</div>'
        + '<div class="kpi-sub">' + R.esc(m.provider || '–') + ' · ' + R.esc(R.regionName(m.region)) + '</div>'
        + '</a></div>';
    }).join('');
    /* KPI 卡片点击：跳转完整榜单对应排序 tab */
    grid.querySelectorAll('[data-tab]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        if (e.target.closest('a')) return;
        e.preventDefault();
        window.location.href = 'rank.html?key=' + encodeURIComponent(el.dataset.tab);
      });
    });
  }

  /* 本周榜单变化摘要（对比 data/prev.json 快照） */
  function renderWeekly(prev) {
    var grid = document.getElementById('weeklyGrid');
    var subEl = document.getElementById('weeklySub');
    var rangeEl = document.getElementById('weeklyRange');
    if (!prev || !prev.models || !prev.date) {
      grid.innerHTML = '<div class="weekly-empty" style="grid-column: 1 / -1;">本周首次同步 LMArena 全量榜单，<b>下周一开始记录周对比</b>。</div>';
      if (subEl) subEl.textContent = '本次扩容覆盖全量 LMArena 模型，未有历史周对比数据。';
      return;
    }
    var cur = R.getModels();
    var curMap = {}; cur.forEach(function (m) { curMap[m.id] = m; });
    var prevMap = {}; prev.models.forEach(function (m) { prevMap[m.id] = m; });

    var upList = [], newList = [], downList = [], outList = [];
    cur.forEach(function (m) {
      var prevM = prevMap[m.id];
      if (!prevM) {
        newList.push(m);
        return;
      }
      var dElo = (m.elo || 0) - (prevM.elo || 0);
      if (dElo >= 1) upList.push({ m: m, d: dElo });
      else if (dElo <= -1) downList.push({ m: m, d: dElo });
    });
    Object.keys(prevMap).forEach(function (id) {
      if (!curMap[id]) outList.push(prevMap[id]);
    });
    upList.sort(function (a, b) { return b.d - a.d; });
    downList.sort(function (a, b) { return a.d - b.d; });
    newList.sort(function (a, b) { return (b.elo || 0) - (a.elo || 0); });
    outList.sort(function (a, b) { return (b.elo || 0) - (a.elo || 0); });

    var today = R.getMeta().updated || '';
    if (rangeEl) rangeEl.textContent = prev.date + ' → ' + today;

    var renderList = function (ulId, items, kind) {
      var ul = document.getElementById(ulId);
      if (!items.length) {
        ul.innerHTML = '<li class="weekly-empty" style="border:none;padding:8px 0">暂无</li>';
        return;
      }
      ul.innerHTML = items.slice(0, 5).map(function (it) {
        var m = it.m || it;
        var d = it.d != null ? it.d : null;
        var dStr = d == null ? ''
          : (kind === 'up'   ? '+' + d
            : kind === 'down' ? d
            : kind === 'new'  ? '+新'
            : '');
        return '<li>'
          + '<span class="wk-name"><a href="model.html?id=' + R.esc(m.id) + '">' + R.esc(m.name) + '</a>'
          + '<small>' + R.esc(m.provider || '') + '</small></span>'
          + (dStr ? '<span class="wk-delta">' + dStr + (kind === 'new' || kind === 'out' ? '' : ' Elo') + '</span>' : '')
          + '</li>';
      }).join('');
    };

    if (subEl) {
      var totalChanges = upList.length + downList.length + newList.length + outList.length;
      subEl.textContent = totalChanges === 0
        ? '与上周快照相比，本期榜单保持稳定'
        : '对比 ' + prev.date + ' 快照：' + upList.length + ' 涨 / ' + downList.length + ' 跌 / ' + newList.length + ' 新进 / ' + outList.length + ' 退出。';
    }

    if (totalChanges === 0) {
      renderStableFallback(cur);
      return;
    }

    renderList('weeklyUp', upList, 'up');
    renderList('weeklyNew', newList, 'new');
    renderList('weeklyDown', downList.length ? downList : outList, downList.length ? 'down' : 'out');
    /* 退出模型用同一卡片展示：当 downList 为空但有 outList，标题改为「退出模型」 */
    if (downList.length === 0 && outList.length) {
      document.querySelector('#weeklySection .weekly-cell:nth-child(3) h3').textContent = '退出模型 Top 5';
    }
  }

  /* 周对比无变化时：用静态 Top 3 榜单兜底，避免大面积「暂无」 */
  function renderStableFallback(cur) {
    var grid = document.getElementById('weeklyGrid');
    if (!grid) return;
    function miniList(list, key, unit, tab) {
      if (!list.length) {
        return '<li class="weekly-empty" style="border:none;padding:8px 0">暂无数据</li>';
      }
      return list.slice(0, 3).map(function (m, i) {
        var v = key === 'bench' ? R.fmtBench(m.bench)
          : key === 'priceIn' ? R.fmtCny(m.priceIn)
          : R.fmtNum(m[key]);
        return '<li>'
          + '<span class="wk-name"><span class="wk-rank">' + (i + 1) + '</span>'
          + '<a href="model.html?id=' + R.esc(m.id) + '">' + R.esc(m.name) + '</a>'
          + '<small>' + R.esc(m.provider || '') + '</small></span>'
          + '<span class="wk-delta">' + v + (unit ? ' ' + unit : '') + '</span>'
          + '</li>';
      }).join('');
    }
    var topElo = cur.slice().sort(function (a, b) { return (b.elo || 0) - (a.elo || 0); });
    var topBench = cur.filter(function (m) { return m.bench != null; })
      .sort(function (a, b) { return b.bench - a.bench; });
    var lowPrice = cur.filter(function (m) { return m.priceIn != null; })
      .sort(function (a, b) { return a.priceIn - b.priceIn; });
    grid.innerHTML = '<div class="weekly-stable-note">'
      + '<b>本期榜单保持稳定</b> · 与上周快照相比，竞技场 Elo、综合能力分与 API 价格均无变化。'
      + 'LMArena 官方数据更新较慢时，这种情况会偶尔出现。'
      + '<a href="report.html">查看完整周报 →</a></div>'
      + '<div class="weekly-cell"><h3>Elo Top 3</h3><ol class="weekly-list weekly-up-list">' + miniList(topElo, 'elo', 'Elo', 'elo') + '</ol></div>'
      + '<div class="weekly-cell"><h3>综合能力 Top 3</h3><ol class="weekly-list weekly-new-list">' + miniList(topBench, 'bench', '分', 'bench') + '</ol></div>'
      + '<div class="weekly-cell"><h3>输入价最低 Top 3</h3><ol class="weekly-list weekly-down-list">' + miniList(lowPrice, 'priceIn', '/Mtok', 'priceIn') + '</ol></div>';
  }

  /* 最新解读：从 data/articles.json 取最近 3 篇（过滤草稿），与文章中心同一数据源 */
  function renderLatest() {
    var section = document.getElementById('latestSection');
    if (!section) return;
    fetch('data/articles.json')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (arts) {
        var list = (arts || []).filter(function (a) { return !a.draft; }).slice(0, 3);
        if (!list.length) { section.style.display = 'none'; return; }
        var grid = document.getElementById('latestGrid');
        grid.innerHTML = list.map(function (a) {
          var tags = (a.tags || []).map(function (t) {
            return '<span class="art-tag">' + R.esc(t) + '</span>';
          }).join('');
          return '<a class="art-card" href="articles/' + encodeURIComponent(a.file) + '">'
            + '<div class="art-date">' + R.esc(a.date) + (a.issue ? ' · 第 ' + a.issue + ' 期' : '') + '</div>'
            + '<h2 class="art-title">' + R.esc(a.title) + '</h2>'
            + '<p class="art-summary">' + R.esc(a.summary) + '</p>'
            + (tags ? '<div class="art-tags">' + tags + '</div>' : '')
            + '</a>';
        }).join('');
        var dateEl = document.getElementById('latestDate');
        if (dateEl) dateEl.textContent = '最近更新 ' + list[0].date;
      })
      .catch(function () { section.style.display = 'none'; });
  }

  function init() {
    renderTop3();
    renderKpi();
    renderLatest();
    fetch('data/prev.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { renderWeekly(data); })
      .catch(function () { renderWeekly(null); });
  }

  R.loadData().then(function () {
    var meta = R.getMeta();
    document.getElementById('dataDate').textContent = meta.updated;
    document.getElementById('modelCount').textContent = R.getModels().length;
    document.getElementById('footDate').textContent = meta.updated;
    var ul = document.getElementById('sources');
    ul.innerHTML = meta.sources.map(function (s) {
      return '<li><span class="src-name">' + R.esc(s.name) + '</span>'
        + '<span class="src-desc">' + R.esc(s.desc) + (s.url ? ' · <a href="' + R.esc(s.url) + '" target="_blank" rel="noopener">访问官网</a>' : '') + '</span></li>';
    }).join('');
    init();
  }).catch(function (err) {
    document.getElementById('top3Grid').innerHTML =
      '<div class="weekly-empty" style="grid-column: 1 / -1;">数据加载失败：' + R.esc(err.message) + '。请通过本地服务器访问（如 python3 -m http.server）。</div>';
  });
})();

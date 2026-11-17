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
    var pickBy = function (key, dir, useConverted) {
      return models.filter(function (m) { return m[key] != null; })
        .reduce(function (best, m) {
          if (!best) return m;
          var mv = useConverted ? R.priceToCny(m, key) : m[key];
          var bv = useConverted ? R.priceToCny(best, key) : best[key];
          if (mv === bv) {
            /* 同分/同价时选资料更完整的一条，避免把自动生成的同名列到首页 */
            return Object.keys(m).length > Object.keys(best).length ? m : best;
          }
          return dir > 0 ? (mv < bv ? m : best) : (mv > bv ? m : best);
        }, null);
    };
    var fmtPrice = function (m, field) { return m[field] === 0 ? '限时免费' : R.fmtPrice(m, field); };
    var fmtCtx = function (v) {
      if (v == null) return '–';
      if (v >= 10000) return (v / 10000).toFixed(0) + '万';
      return v.toLocaleString('zh-CN');
    };
    var cards = [
      { label: '竞技场 Elo 第一',   pick: pickBy('elo', -1),       val: function (m) { return m.elo; },       unit: 'Elo',     tab: 'elo' },
      { label: '综合能力第一',       pick: pickBy('bench', -1),    val: function (m) { return R.fmtBench(m.bench); }, unit: '分', tab: 'bench' },
      { label: '中文能力第一',        pick: pickBy('superclue', -1), val: function (m) { return m.superclue; }, unit: '分',      tab: 'superclue' },
      { label: '输入价最低',         pick: pickBy('priceIn', 1, true), val: function (m) { return fmtPrice(m, 'priceIn'); }, unit: '/ 百万输入 tok', tab: 'priceIn',
        foot: function (m) { return (m.priceIn === 0 ? '官方限时免费，恢复收费请以官网为准 · ' : '输入价，不含输出与缓存 · ') + '该模型价格核验于 ' + R.priceDateText(m) + ' · 仅 ' + R.priceCoverage().priced + ' 款有公开定价'; } },
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
        + (c.foot ? '<div class="kpi-foot">' + R.esc(typeof c.foot === 'function' ? c.foot(m) : c.foot) + '</div>' : '')
        + '</a></div>';
    }).join('');
    /* 各「第一」的候选池并不相同：不写清楚会让人以为是 444 款里的第一 */
    var caveat = document.getElementById('kpiCaveat');
    if (caveat) {
      var n = function (key) { return models.filter(function (m) { return m[key] != null; }).length; };
      caveat.textContent = '各项「第一」仅在有对应数据的模型中比较：竞技场 Elo '
        + n('elo') + ' 款、综合能力 ' + n('bench') + ' 款、中文能力 ' + n('superclue')
        + ' 款、价格 ' + n('priceIn') + ' 款、上下文 ' + n('context') + ' 款。'
        + '收录模型共 ' + models.length + ' 款，未收录指标不代表该模型能力为零。';
    }
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
      if (rangeEl) rangeEl.textContent = '暂无对比数据';
      grid.innerHTML = '<div class="weekly-empty" style="grid-column: 1 / -1;">本次未能读取上期快照（data/prev.json），暂时无法计算周变化。'
        + '这通常是数据尚未加载完成或网络请求被拦截，<b>刷新页面</b>即可重试。</div>';
      if (subEl) subEl.textContent = '周对比依赖上一期快照；加载失败时不会用「无变化」代替，以免误导。';
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
        /* 单周涨跌超过 100 分基本不是能力变化，而是 LMArena 调整评测样本池、
           或同一家族的不同版本被归并后取了最高分。加 † 提示，避免被当成真进步。 */
        var jump = d != null && Math.abs(d) >= 100;
        var dStr = d == null ? ''
          : (kind === 'up'   ? '+' + d
            : kind === 'down' ? d
            : kind === 'new'  ? '+新'
            : '');
        return '<li>'
          + '<span class="wk-name"><a href="model.html?id=' + R.esc(m.id) + '">' + R.esc(m.name) + '</a>'
          + '<small>' + R.esc(m.provider || '') + '</small></span>'
          + (dStr ? '<span class="wk-delta">' + dStr + (kind === 'new' || kind === 'out' ? '' : ' Elo') + (jump ? '†' : '') + '</span>' : '')
          + '</li>';
      }).join('');
    };

    var bigJumps = upList.concat(downList).some(function (it) { return Math.abs(it.d) >= 100; });

    if (subEl) {
      var totalChanges = upList.length + downList.length + newList.length + outList.length;
      subEl.textContent = totalChanges === 0
        ? '与上周快照相比，本期榜单保持稳定'
        : '对比 ' + prev.date + ' 快照：' + upList.length + ' 涨 / ' + downList.length + ' 跌 / ' + newList.length + ' 新进 / ' + outList.length + ' 退出。'
          + (bigJumps ? ' † 单周变动超过 100 分，多为评测样本调整或同家族版本归并所致，不代表模型能力突变。' : '');
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
          : key === 'priceIn' ? (m.priceIn === 0 ? '限时免费' : R.fmtPrice(m, 'priceIn'))
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
      .sort(function (a, b) {
        var d = (R.priceToCny(a, 'priceIn') || 0) - (R.priceToCny(b, 'priceIn') || 0);
        /* 同价时资料更全的排前面，后面按「厂商+价格+Elo」去重，避免同模型两个名字占两行 */
        return d || (Object.keys(b).length - Object.keys(a).length);
      })
      .filter(function (m, i, arr) {
        var key = [m.provider, m.priceIn, m.priceOut, m.elo].join('|');
        return arr.findIndex(function (x) {
          return [x.provider, x.priceIn, x.priceOut, x.elo].join('|') === key;
        }) === i;
      });
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
        var dateEl = document.getElementById('latestDate');
        if (!list.length) {
          if (dateEl) dateEl.textContent = '暂无已发布内容';
          document.getElementById('latestGrid').innerHTML =
            '<p class="dim-note">解读文章尚未生成，下次数据更新后会自动出现。</p>';
          return;
        }
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
        if (dateEl) dateEl.textContent = '最近更新 ' + list[0].date;
      })
      .catch(function () {
        var dateEl = document.getElementById('latestDate');
        if (dateEl) dateEl.textContent = '加载失败';
        document.getElementById('latestGrid').innerHTML =
          '<p class="dim-note">解读内容暂时无法加载，请刷新页面重试；<a href="articles.html">前往文章中心</a>。</p>';
      });
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

  /* 数据时效：把「快照日」和「各指标数据日」拆开显示。
     快照日只代表页面生成时间；Elo / 中文测评 / 价格各有自己的数据期，
     混成一个日期会让人误以为页面上的每个数字都是当天更新的。 */
  function renderFreshness(meta) {
    var fi = meta.fieldInfo || {};
    var items = [{ label: '快照', date: meta.updated }];
    function add(label, field) {
      if (!field || !field.date) return;
      items.push({
        label: label, date: field.date,
        // ※ 只标「沿用旧数据」；优先用后端显式 stale 标记（官网直采当期不算旧），
        //   「换口径」是已更新但不可比，用提示而非陈旧符号
        stale: field.stale != null
          ? !!field.stale
          : !!(field.note && field.note.indexOf('沿用') >= 0 && field.note.indexOf('官网直采') < 0),
        note: field.note
      });
    }
    add('Elo 数据期', fi.elo);
    add('中文测评', fi.superclue);
    add('价格数据截至', fi.price);
    var priceAge = R.priceAgeMonths();
    items.forEach(function (it) {
      if (it.label === '价格数据截至') it.age = priceAge;
    });

    var box = document.getElementById('dataFreshness');
    if (!box) return;
    var hasStale = items.some(function (it) { return it.stale; });
    box.innerHTML = '<span class="df-label">数据时效</span>' + items.map(function (it) {
      return '<span class="df-item' + (it.stale ? ' df-stale' : '') + '"'
        + (it.note ? ' title="' + R.esc(it.note) + '"' : '') + '>'
        + R.esc(it.label) + ' <b>' + R.esc(it.date) + '</b>'
        + (it.age != null ? '<span class="df-age">约 ' + it.age + ' 个月前</span>' : '')
        + (it.stale ? '<span class="df-mark" aria-hidden="true">※</span>' : '')
        + '</span>';
    }).join('<span class="df-sep" aria-hidden="true"> · </span>')
      + (hasStale ? '<span class="df-foot">注：带 ※ 的指标本期未更新，沿用最近一次可用数据</span>' : '');
    box.hidden = false;

    /* 免责声明同步成真实数据期（原来写死 2026-08-19，与实际数据不符） */
    var dd = document.getElementById('disclaimerDates');
    if (!dd) return;
    var elo = (fi.elo && fi.elo.date) || meta.updated;
    var sc = fi.superclue && fi.superclue.date;
    var pr = fi.price && fi.price.date;
    var basis = meta.basisChange && meta.basisChange.field === 'superclue' ? meta.basisChange : null;
    dd.textContent = 'Elo 来自 LMArena 公开快照（数据期 ' + elo + '）'
      + (sc ? '，中文能力来自 SuperCLUE ' + sc + '测评'
        + (basis ? '（本期起为新评分口径，与此前数值不可比）' : '') : '')
      + (pr ? '，API 价格核验于 ' + pr : '')
      + '，上下文窗口取自厂商公开资料，输出速度为公开评测汇总并标注为估算值。';
  }

  R.loadData().then(function () {
    var meta = R.getMeta();
    document.getElementById('dataDate').textContent = meta.updated;
    document.getElementById('modelCount').textContent = R.getModels().length;
    document.getElementById('footDate').textContent = meta.updated;
    renderFreshness(meta);
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

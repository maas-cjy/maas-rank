/* 榜单变化周报：对比最新历史快照与当前数据，渲染每周榜单变化 */
(function () {
  'use strict';
  var R = window.MRank;
  var SITE = 'https://maasrank.com/';

  /* ---------- 工具 ---------- */

  function rankMap(list, key) {
    var sorted = list.slice().sort(function (a, b) {
      var va = a[key] == null ? -Infinity : a[key];
      var vb = b[key] == null ? -Infinity : b[key];
      return vb - va;
    });
    var map = {};
    sorted.forEach(function (m, i) { map[m.id] = i + 1; });
    return map;
  }

  function d(oldV, newV) {
    if (oldV == null || newV == null) return null;
    return newV - oldV;
  }

  function diffBadge(v, unit) {
    if (v == null || v === 0 || v === '0.00' || v === '0') return '';
    var num = parseFloat(v);
    var up = num > 0;
    var cls = up ? 'diff-up' : 'diff-down';
    var arrow = up ? '▲' : '▼';
    var sign = up ? '+' : '';
    return '<span class="' + cls + '">' + arrow + ' ' + sign + v + (unit || '') + '</span>';
  }

  function rankBadge(delta) {
    if (delta == null || delta === 0) return '<span class="rank-flat">—</span>';
    if (delta < 0) return '<span class="rank-up">↑ ' + (-delta) + ' 位</span>';
    return '<span class="rank-down">↓ ' + delta + ' 位</span>';
  }

  function modelCell(m) {
    return '<a class="r-model" href="model.html?id=' + encodeURIComponent(m.id) + '">' + R.esc(m.name) + '</a>'
      + '<span class="r-vendor">' + R.esc(m.provider || '') + '</span>';
  }

  function tableCard(title, sub, heads, rowsHtml) {
    return '<section class="card r-section">'
      + '<h2>' + title + '</h2>'
      + (sub ? '<p class="sub">' + sub + '</p>' : '')
      + '<div class="table-wrap"><table class="r-table"><thead><tr>'
      + heads.map(function (h) { return '<th>' + h + '</th>'; }).join('')
      + '</tr></thead><tbody>' + rowsHtml + '</tbody></table></div></section>';
  }

  /* ---------- 视图切换 ---------- */

  function showContent() {
    document.getElementById('viewLoading').hidden = true;
    document.getElementById('viewContent').hidden = false;
  }

  /* ---------- 基线视图（尚无历史快照） ---------- */

  function renderBaseline() {
    var cur = R.getModels();
    var top = cur.slice().sort(function (a, b) { return (b.elo || -Infinity) - (a.elo || -Infinity); }).slice(0, 5);

    document.getElementById('rTitle').textContent = '榜单变化周报';
    document.getElementById('rDesc').textContent = '本期为首期基线快照，已完整记录当前榜单数据；下周起将在此展示与上一期的逐项变化。';
    document.getElementById('rRange').innerHTML = '基线快照 <b>' + R.esc(R.getMeta().updated) + '</b>';
    document.getElementById('rCount').innerHTML = '收录模型 <b>' + cur.length + '</b> 个';
    document.getElementById('rUpdated').innerHTML = '数据每周自动更新';

    var rows = top.map(function (m, i) {
      return '<tr><td>' + (i + 1) + '</td><td>' + modelCell(m) + '</td>'
        + '<td>' + R.fmtNum(m.elo) + '</td>'
        + '<td>' + (m.superclue == null ? '—' : R.fmtNum(m.superclue)) + '</td>'
        + '<td>' + (m.priceIn == null ? '—' : R.fmtCny(m.priceIn)) + '</td>'
        + '<td>' + (m.priceOut == null ? '—' : R.fmtCny(m.priceOut)) + '</td></tr>';
    }).join('');

    document.getElementById('rBody').innerHTML = tableCard(
      '当前榜单 Top 5',
      '首个周报周期的基线数据，便于后续对比排名与价格变化',
      ['排名', '模型', '竞技场 Elo', 'SuperCLUE', '输入价', '输出价'],
      rows
    );
  }

  /* ---------- 正式周报视图 ---------- */

  function renderReport(prev, hist) {
    var cur = R.getModels();
    var prevMap = {};
    prev.models.forEach(function (p) { prevMap[p.id] = p; });

    var prevDate = prev.date || '上期';
    var curDate = R.getMeta().updated;

    var eloChanges = [];
    var cnChanges = [];
    var priceChanges = [];
    var added = [];
    var removed = [];

    cur.forEach(function (m) {
      var p = prevMap[m.id];
      if (!p) { added.push(m); return; }
      var dv = d(p.elo, m.elo);
      if (dv != null && dv !== 0) eloChanges.push({ m: m, p: p, dv: dv });
      var dvcn = d(p.superclue, m.superclue);
      if (dvcn != null && dvcn !== 0) cnChanges.push({ m: m, p: p, dv: Math.round(dvcn * 100) / 100 });
      if ((p.priceIn != null && d(p.priceIn, m.priceIn)) || (p.priceOut != null && d(p.priceOut, m.priceOut))) {
        priceChanges.push({ m: m, p: p });
      }
    });
    prev.models.forEach(function (p) {
      if (!cur.some(function (m) { return m.id === p.id; })) removed.push(p);
    });

    var prevEloRank = rankMap(prev.models, 'elo');
    var curEloRank = rankMap(cur, 'elo');
    var prevCnRank = rankMap(prev.models, 'superclue');
    var curCnRank = rankMap(cur, 'superclue');

    eloChanges.sort(function (a, b) { return Math.abs(b.dv) - Math.abs(a.dv); });
    cnChanges.sort(function (a, b) { return Math.abs(b.dv) - Math.abs(a.dv); });

    /* —— 摘要 —— */
    var nUp = eloChanges.filter(function (x) { return x.dv > 0; }).length;
    var nDown = eloChanges.length - nUp;
    var nPrice = priceChanges.length;
    var summary = '本周 ' + curDate + ' 快照与 ' + prevDate + ' 相比：'
      + eloChanges.length + ' 个模型竞技场 Elo 变化（' + nUp + ' 升 ' + nDown + ' 降），'
      + cnChanges.length + ' 个模型中文能力变化，' + nPrice + ' 个模型调整 API 价格'
      + (added.length ? '，新增收录 ' + added.length + ' 个模型' : '')
      + (removed.length ? '，移出 ' + removed.length + ' 个模型' : '')
      + '。';

    document.getElementById('rTitle').textContent = '榜单变化周报';
    document.getElementById('rDesc').textContent = summary;
    document.getElementById('rRange').innerHTML = '对比区间 <b>' + R.esc(prevDate) + ' → ' + R.esc(curDate) + '</b>';
    document.getElementById('rCount').innerHTML = '收录模型 <b>' + cur.length + '</b> 个';
    document.getElementById('rUpdated').innerHTML = '数据快照 <b>' + R.esc(curDate) + '</b>';

    /* —— SEO —— */
    setSeo(prevDate, curDate, nUp, nDown, nPrice, added.length, summary);

    /* —— 各区块 —— */
    var html = '';

    if (eloChanges.length) {
      var eloRows = eloChanges.map(function (x) {
        var rankDelta = (prevEloRank[x.m.id] != null && curEloRank[x.m.id] != null)
          ? curEloRank[x.m.id] - prevEloRank[x.m.id] : null;
        return '<tr><td>' + modelCell(x.m) + '</td>'
          + '<td>' + R.fmtNum(x.p.elo) + '</td>'
          + '<td>' + R.fmtNum(x.m.elo) + '</td>'
          + '<td>' + diffBadge(x.dv, '') + '</td>'
          + '<td>' + rankBadge(rankDelta) + '</td></tr>';
      }).join('');
      html += tableCard('竞技场 Elo 变化',
        'LMArena 人类偏好盲测评分，按变化幅度排序',
        ['模型', '上期', '本期', '变化', '名次'], eloRows);
    }

    if (cnChanges.length) {
      var cnRows = cnChanges.map(function (x) {
        var rankDelta = (prevCnRank[x.m.id] != null && curCnRank[x.m.id] != null)
          ? curCnRank[x.m.id] - prevCnRank[x.m.id] : null;
        return '<tr><td>' + modelCell(x.m) + '</td>'
          + '<td>' + R.fmtNum(x.p.superclue) + '</td>'
          + '<td>' + R.fmtNum(x.m.superclue) + '</td>'
          + '<td>' + diffBadge(x.dv, '') + '</td>'
          + '<td>' + rankBadge(rankDelta) + '</td></tr>';
      }).join('');
      html += tableCard('中文能力（SuperCLUE）变化',
        '中文通用能力综合测评得分，按变化幅度排序',
        ['模型', '上期', '本期', '变化', '名次'], cnRows);
    }

    if (priceChanges.length) {
      var prRows = priceChanges.map(function (x) {
        var inCell = priceCell(x.p.priceIn, x.m.priceIn);
        var outCell = priceCell(x.p.priceOut, x.m.priceOut);
        return '<tr><td>' + modelCell(x.m) + '</td>'
          + '<td>' + inCell + '</td>'
          + '<td>' + outCell + '</td></tr>';
      }).join('');
      html += tableCard('API 价格调整',
        '每百万 tokens 价格，按人民币折算',
        ['模型', '输入价格', '输出价格'], prRows);
    }

    if (added.length) {
      html += tableCard('本期新增收录',
        '新进入榜单的模型',
        ['模型', '竞技场 Elo', 'SuperCLUE', '输入价', '输出价'],
        added.map(function (m) {
          return '<tr><td>' + modelCell(m) + '</td>'
            + '<td>' + R.fmtNum(m.elo) + '</td>'
            + '<td>' + (m.superclue == null ? '—' : R.fmtNum(m.superclue)) + '</td>'
            + '<td>' + (m.priceIn == null ? '—' : R.fmtCny(m.priceIn)) + '</td>'
            + '<td>' + (m.priceOut == null ? '—' : R.fmtCny(m.priceOut)) + '</td></tr>';
        }).join(''));
    }

    if (removed.length) {
      html += tableCard('本期移出榜单',
        '上一期收录但本期已不在榜单的模型',
        ['模型'],
        removed.map(function (p) {
          return '<tr><td>' + R.esc(p.name) + '</td></tr>';
        }).join(''));
    }

    if (!html) {
      html = renderStableSection(prev, hist);
    }

    document.getElementById('rBody').innerHTML = html;
  }

  /* ---------- 无变化时的兜底视图 ---------- */

  function renderStableSection(prev, hist) {
    var cur = R.getModels();
    var top = cur.slice().sort(function (a, b) { return (b.elo || -Infinity) - (a.elo || -Infinity); }).slice(0, 10);
    var rows = top.map(function (m, i) {
      return '<tr><td>' + (i + 1) + '</td><td>' + modelCell(m) + '</td>'
        + '<td>' + R.fmtNum(m.elo) + '</td>'
        + '<td>' + (m.bench == null ? '—' : R.fmtBench(m.bench)) + '</td>'
        + '<td>' + (m.superclue == null ? '—' : R.fmtNum(m.superclue)) + '</td>'
        + '<td>' + (m.priceIn == null ? '—' : R.fmtCny(m.priceIn)) + '</td></tr>';
    }).join('');

    var html = '<section class="card r-section">'
      + '<h2>本期榜单保持稳定</h2>'
      + '<p class="sub">与 ' + R.esc(prev.date || '上期') + ' 快照相比，竞技场 Elo、综合能力分与 API 价格均未变化。'
      + 'LMArena 官方数据更新较慢，或 SuperCLUE 尚未发布新一期榜单时，会出现这种情况。'
      + '下方提供当前 Top 10 与历史趋势作为参考。</p>'
      + '</section>';

    html += tableCard('当前榜单 Top 10', '本期各维度领先模型一览，便于横向对比', ['排名', '模型', '竞技场 Elo', '综合能力', 'SuperCLUE', '输入价'], rows);

    if (hist && hist.snapshots && hist.snapshots.length > 1) {
      html += '<section class="card chart-card r-section">'
        + '<h2>竞技场 Elo 历史趋势（Top 5）</h2>'
        + '<p class="sub">基于最近 ' + hist.snapshots.length + ' 期快照，观察头部模型分数走势</p>'
        + '<div id="rTrendChart" style="width:100%;height:320px;"></div></section>';
    }
    return html;
  }

  function renderTrendChart(hist) {
    var dom = document.getElementById('rTrendChart');
    if (!dom || typeof echarts === 'undefined') return;
    var dates = hist.snapshots.map(function (s) { return s.date; });
    var top5 = R.getModels().slice().sort(function (a, b) { return (b.elo || 0) - (a.elo || 0); }).slice(0, 5);
    var series = top5.map(function (m) {
      var data = hist.snapshots.map(function (s) {
        var sm = s.models.find(function (x) { return x.id === m.id; });
        return sm ? (sm.elo || null) : null;
      });
      data.push(m.elo || null);
      return { name: m.name, type: 'line', smooth: 0.3, symbolSize: 6, data: data };
    });
    var chart = echarts.init(dom);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: top5.map(function (m) { return m.name; }), bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '16%', top: '10%', containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: dates.concat([R.getMeta().updated]) },
      yAxis: { type: 'value', scale: true, name: 'Elo' },
      series: series,
      color: ['#7F77DD', '#1D9E75', '#D85A30', '#378ADD', '#D4537E']
    });
    window.addEventListener('resize', function () { chart.resize(); });
  }

  function priceCell(oldV, newV) {
    if (oldV == null && newV == null) return '—';
    var s = (oldV == null ? '—' : R.fmtCny(oldV)) + ' → ' + (newV == null ? '—' : R.fmtCny(newV));
    var dv = d(oldV, newV);
    if (dv != null && dv !== 0) s += ' ' + diffBadge((dv * R.USD_CNY).toFixed(2), '元');
    return s;
  }

  /* ---------- 动态 SEO ---------- */

  function setSeo(prevDate, curDate, nUp, nDown, nPrice, nAdded, summary) {
    var url = SITE + 'report.html';
    var title = '大模型榜单周报（' + prevDate + ' → ' + curDate + '）：'
      + nUp + ' 个模型 Elo 上升' + (nPrice ? '、' + nPrice + ' 个调整价格' : '') + ' | MaaS Rank 大模型排行榜';
    var desc = '本周大模型榜单变化汇总：' + nUp + ' 个模型 Elo 上升、' + nDown + ' 个下降'
      + (nPrice ? '、' + nPrice + ' 个模型调整 API 价格' : '')
      + (nAdded ? '、新增收录 ' + nAdded + ' 个模型' : '')
      + '。对比区间 ' + prevDate + ' → ' + curDate + '，数据每周自动更新。';

    document.title = title;
    document.querySelector('meta[name="description"]').setAttribute('content', desc);
    document.querySelector('link[rel="canonical"]').setAttribute('href', url);
    document.querySelector('meta[property="og:title"]').setAttribute('content', title);
    document.querySelector('meta[property="og:description"]').setAttribute('content', desc);
    document.querySelector('meta[property="og:url"]').setAttribute('content', url);
    document.querySelector('meta[name="twitter:title"]').setAttribute('content', title);
    document.querySelector('meta[name="twitter:description"]').setAttribute('content', desc);

    var ld = {
      '@context': 'https://schema.org',
      '@type': 'Report',
      'headline': '榜单变化周报（' + prevDate + ' → ' + curDate + '）',
      'datePublished': curDate,
      'description': summary,
      'url': url,
      'publisher': { '@type': 'Organization', 'name': 'MaaS Rank' },
      'inLanguage': 'zh-CN'
    };
    document.getElementById('ldReport').textContent = JSON.stringify(ld);
  }

  /* ---------- 初始化 ---------- */

  R.loadData().then(function () {
    document.getElementById('footDate').textContent = R.getMeta().updated;
    return fetch('data/history.json', { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .catch(function () { return null; });
  }).then(function (hist) {
    var snaps = hist && hist.snapshots && hist.snapshots.length ? hist.snapshots : [];
    if (snaps.length) renderReport(snaps[snaps.length - 1], hist);
    else renderBaseline();
    showContent();
    if (hist && hist.snapshots && hist.snapshots.length > 1) {
      renderTrendChart(hist);
    }
  }).catch(function (err) {
    document.getElementById('viewLoading').innerHTML =
      '<h1>数据加载失败</h1><p>' + R.esc(err.message) + '。请通过本地服务器访问（如 python3 -m http.server）。</p>';
  });
})();

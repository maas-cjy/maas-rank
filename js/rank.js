/* 排行榜页逻辑 */
(function () {
  'use strict';
  var R = window.MRank;

  var state = { key: 'elo', dir: -1 };
  var chart = null;

  var TAB = {
    elo: {
      label: '竞技场 Elo', unit: 'Elo', dir: -1, note: 'LMArena 人类盲测投票，分差 25 分内属于噪声区间',
      title: '竞技场 Elo 排名', desc: 'LMArena 全球人类盲测投票 · 分数越高代表真实用户偏好越强',
      fmt: function (m) { return R.fmtNum(m.elo) + R.estMark(m, 'elo'); }
    },
    superclue: {
      label: '中文能力', unit: '分', dir: -1, note: 'SuperCLUE 智能指数（满分 100），海外模型为参考值',
      title: '中文综合能力排名', desc: 'SuperCLUE 智能指数（数学/科学/代码/指令/幻觉/Agent）',
      fmt: function (m) { return R.fmtNum(m.superclue) + R.estMark(m, 'superclue'); }
    },
    priceIn: {
      label: '输入价格', unit: '¥/M', dir: 1, note: '每百万输入 tokens 价格（按 $1≈¥7.2 换算）',
      title: '输入价格排名（由低到高）', desc: '每百万输入 tokens 价格 · 越低越便宜',
      fmt: function (m) { return R.fmtCny(m.priceIn) + R.estMark(m, 'priceIn'); }
    },
    context: {
      label: '上下文', unit: 'tokens', dir: -1, note: '最大输入上下文窗口',
      title: '上下文窗口排名', desc: '最大输入上下文窗口 · 越长可处理的文档越多',
      fmt: function (m) { return R.fmtCtx(m.context); }
    },
    speed: {
      label: '输出速度', unit: 'tok/s', dir: -1, note: '输出速度为估算值（tok/s）',
      title: '输出速度排名', desc: '输出吞吐量（tokens/秒）· 部分为估算值',
      fmt: function (m) { return R.fmtSpeed(m.speed) + R.estMark(m, 'speed'); }
    }
  };

  function sortKey(m) {
    var v = m[state.key];
    return v == null ? (state.dir === 1 ? Infinity : -Infinity) : v;
  }

  function ranked() {
    var t = TAB[state.key];
    var list = R.getModels().slice().sort(function (a, b) {
      return (sortKey(a) - sortKey(b)) * t.dir;
    });
    return list;
  }

  function rankClass(i) {
    return i === 0 ? 'r1' : i === 1 ? 'r2' : i === 2 ? 'r3' : '';
  }

  function renderTable() {
    var t = TAB[state.key];
    var list = ranked();
    var html = '';
    list.forEach(function (m, i) {
      var rank = state.dir === 1 ? '' : '<span class="rank ' + rankClass(i) + '">' + (i + 1) + '</span>';
      var rowCls = i < 3 ? ' class="row-top3"' : '';
      html += '<tr' + rowCls + '>'
        + '<td>' + (rank || '<span class="muted num">' + (i + 1) + '</span>') + '</td>'
        + '<td><div class="mname"><a href="compare.html?m=' + encodeURIComponent(m.id) + '">' + R.esc(m.name) + '</a></div>'
        + '<div class="mprov">' + R.esc(m.provider) + ' · ' + R.regionName(m.region) + '</div></td>'
        + '<td class="num">' + t.fmt(m) + '</td>'
        + '<td class="num">' + R.fmtNum(m.superclue) + R.estMark(m, 'superclue') + '</td>'
        + '<td class="num">' + R.fmtCny(m.priceIn) + R.estMark(m, 'priceIn') + '</td>'
        + '<td class="num">' + R.fmtCny(m.priceOut) + R.estMark(m, 'priceOut') + '</td>'
        + '<td class="num">' + R.fmtCtx(m.context) + '</td>'
        + '<td class="num">' + R.fmtSpeed(m.speed) + R.estMark(m, 'speed') + '</td>'
        + '<td>' + R.badgeOpen(m) + ' ' + R.badgeRegion(m) + '</td>'
        + '</tr>';
    });
    document.getElementById('rankBody').innerHTML = html;
    document.getElementById('tableTitle').textContent = t.title;
    document.getElementById('tableSub').textContent = t.desc;
    document.getElementById('tableNote').textContent = '注：' + t.note;
    document.getElementById('chartTitle').textContent = 'Top 10 · ' + t.label;
  }

  function renderChart() {
    if (typeof echarts === 'undefined') return;
    if (!chart) chart = echarts.init(document.getElementById('chart'));
    var t = TAB[state.key];
    var list = ranked().slice(0, 10);
    var vals = list.map(function (m) { return m[state.key]; });
    var names = list.map(function (m) { return m.name; });
    var colors = list.map(function (_, i) {
      if (state.dir === -1 && i === 0) return '#f59e0b';
      if (state.dir === -1 && i === 1) return '#94a3b8';
      if (state.dir === -1 && i === 2) return '#b45309';
      return '#6366f1';
    });
    chart.setOption({
      grid: { left: 10, right: 50, top: 10, bottom: 10, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: function (p) {
        var idx = vals.length - 1 - p[0].dataIndex;
        var m = list[idx];
        return '<b>' + R.esc(m.name) + '</b><br/>' + R.esc(m.provider) + '<br/>' + t.label + '：<b>' + R.fmtNum(vals[idx]) + '</b>';
      } },
      xAxis: { type: 'value', axisLabel: { color: '#6a7180', fontSize: 11 } },
      yAxis: {
        type: 'category', data: names.slice().reverse(),
        axisLabel: { color: '#191c23', fontSize: 12 },
        axisLine: { show: false }, axisTick: { show: false }
      },
      series: [{
        type: 'bar', data: vals.slice().reverse(), barWidth: '58%',
        itemStyle: { borderRadius: [0, 6, 6, 0], color: function (p) { return colors[vals.length - 1 - p.dataIndex]; } },
        label: { show: true, position: 'right', fontSize: 11, color: '#6a7180' }
      }]
    }, true);
  }

  function setTab(key) {
    state.key = key;
    state.dir = TAB[key].dir;
    document.querySelectorAll('.tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.key === key);
    });
    renderTable();
    renderChart();
  }

  function init() {
    document.getElementById('tabs').addEventListener('click', function (e) {
      var btn = e.target.closest('.tab');
      if (btn) setTab(btn.dataset.key);
    });
    document.querySelectorAll('#rankTable thead th[data-key]').forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.dataset.key;
        if (state.key === k) { state.dir = -state.dir; }
        else { state.key = k; state.dir = TAB[k].dir; }
        document.querySelectorAll('.tab').forEach(function (b) { b.classList.toggle('active', b.dataset.key === k); });
        renderTable();
        renderChart();
      });
    });
    window.addEventListener('resize', function () { if (chart) chart.resize(); });
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
    renderTable();
    renderChart();
  }).catch(function (err) {
    document.getElementById('rankBody').innerHTML =
      '<tr><td colspan="9" class="empty">数据加载失败：' + R.esc(err.message) + '。请通过本地服务器访问（如 python3 -m http.server）。</td></tr>';
  });
})();

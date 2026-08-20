/* 排行榜页逻辑 */
  /* eslint-disable no-var */
(function () {
  'use strict';
  var R = window.MRank;

  // 全维度筛选状态：state.filters. providers / regions / opens 都是字符串数组（多选）
  var state = {
    key: 'elo', dir: -1, showAll: false, query: '',
    filters: { providers: [], regions: [], opens: [] }
  };
  var PAGE = 50;
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

  function applyFilters(list) {
    var f = state.filters;
    if (!f.providers.length && !f.regions.length && !f.opens.length) return list;
    return list.filter(function (m) {
      if (f.providers.length && f.providers.indexOf(m.provider) === -1) return false;
      if (f.regions.length && f.regions.indexOf(m.region) === -1) return false;
      if (f.opens.length) {
        var want = f.opens.indexOf('open') !== -1;
        if (want && !m.open) return false;
        if (!want && m.open) return false;
      }
      return true;
    });
  }

  function ranked() {
    var t = TAB[state.key];
    var list = R.getModels().slice().sort(function (a, b) {
      return (sortKey(a) - sortKey(b)) * t.dir;
    });
    return list;
  }

  /* 按筛选 chip 与搜索词过滤（chip 优先，再叠加搜索词） */
  function filtered() {
    var list = applyFilters(ranked());
    var q = state.query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(function (m) {
      return (m.name || '').toLowerCase().indexOf(q) !== -1
        || (m.provider || '').toLowerCase().indexOf(q) !== -1
        || (m.id || '').toLowerCase().indexOf(q) !== -1;
    });
  }

  /* 无搜索词时默认只显示前 PAGE 条，直到点击「显示全部」 */
  function visible() {
    var list = filtered();
    if (!state.query && !state.showAll && list.length > PAGE) {
      return list.slice(0, PAGE);
    }
    return list;
  }

  function rankClass(i) {
    return i === 0 ? 'r1' : i === 1 ? 'r2' : i === 2 ? 'r3' : '';
  }

  function renderTable() {
    var t = TAB[state.key];
    var all = filtered();
    var list = visible();
    var html = '';
    if (!list.length) {
      html = '<tr><td colspan="9" class="empty">没有匹配的模型，换个关键词试试。</td></tr>';
    }
    list.forEach(function (m, i) {
      var rank = state.dir === 1 ? '' : '<span class="rank ' + rankClass(i) + '">' + (i + 1) + '</span>';
      var rowCls = i < 3 ? ' class="row-top3"' : '';
      html += '<tr' + rowCls + '>'
        + '<td>' + (rank || '<span class="muted num">' + (i + 1) + '</span>') + '</td>'
        + '<td><div class="mname"><a href="model.html?id=' + encodeURIComponent(m.id) + '">' + R.esc(m.name) + '</a></div>'
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

    /* 底部引导：用户滚动到第 50 行后，提示还可展开全部 */
    if (!state.query && !state.showAll && all.length > PAGE) {
      html += '<tr><td colspan="9" class="more-row">'
        + '<button class="show-all" data-action="expand">显示全部 ' + all.length + ' 个模型</button>'
        + '</td></tr>';
    }

    document.getElementById('rankBody').innerHTML = html;
    document.getElementById('tableTitle').textContent = t.title;
    document.getElementById('tableSub').textContent = t.desc;
    document.getElementById('tableNote').textContent = '注：' + t.note;
    document.getElementById('chartTitle').textContent = 'Top 10 · ' + t.label;

    /* 工具栏状态：搜索词 / 显示全部按钮 */
    var hint = document.getElementById('matchHint');
    var btn = document.getElementById('showAllBtn');
    if (state.query) {
      hint.textContent = '找到 ' + all.length + ' 个匹配';
      btn.hidden = true;
    } else if (all.length > PAGE) {
      hint.textContent = (state.showAll ? '共 ' : 'Top ' + PAGE + ' · 共 ') + all.length + ' 个模型';
      btn.hidden = false;
      btn.textContent = state.showAll ? '收起至 Top ' + PAGE : '显示全部 ' + all.length + ' 个';
    } else {
      hint.textContent = '共 ' + all.length + ' 个模型';
      btn.hidden = true;
    }
  }

  function renderChart() {
    if (typeof echarts === 'undefined') return;
    if (!chart) chart = echarts.init(document.getElementById('chart'));
    var t = TAB[state.key];
    var list = visible().slice(0, 10);
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
    state.showAll = false;
    document.querySelectorAll('.tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.key === key);
    });
    renderTable();
    renderChart();
  }

  /* ============== 多维筛选（厂商 / 产地 / 授权 chip） ============== */
  var PROVIDER_ORDER = ['OpenAI', 'Anthropic', 'Google', 'xAI', 'DeepSeek', '阿里云', '字节跳动',
                        '月之暗面', 'MiniMax', '智谱', '腾讯', '百度', 'Meta', 'Mistral AI', 'NVIDIA',
                        'Amazon', '零一万物', '阶跃星辰', '小米', '美团'];
  var REGION_OPTIONS = [
    { v: 'china', label: '国产' }, { v: 'overseas', label: '海外' }
  ];
  var OPEN_OPTIONS = [
    { v: 'open', label: '开源' }, { v: 'closed', label: '闭源' }
  ];

  /* 多维筛选 chip：按厂商 / 产地 / 授权 过滤 */
  function renderFilters() {
    var models = R.getModels();
    /* 厂商：取全量数据中出现 ≥ 2 次的，并按 PROVIDER_ORDER 优先级排序 */
    var counts = {};
    models.forEach(function (m) {
      if (m.provider) counts[m.provider] = (counts[m.provider] || 0) + 1;
    });
    var providers = Object.keys(counts).filter(function (p) { return counts[p] >= 2; });
    providers.sort(function (a, b) {
      var ai = PROVIDER_ORDER.indexOf(a), bi = PROVIDER_ORDER.indexOf(b);
      if (ai === -1 && bi === -1) return b.length - a.length;
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
    document.getElementById('filterProviders').innerHTML =
      providers.map(function (p) {
        return '<button class="filter-chip" data-type="provider" data-val="' + R.esc(p) + '">'
          + R.esc(p) + ' <small style="opacity:.6">' + counts[p] + '</small></button>';
      }).join('');
    document.getElementById('filterRegions').innerHTML =
      REGION_OPTIONS.map(function (r) {
        return '<button class="filter-chip" data-type="region" data-val="' + r.v + '">'
          + r.label + '</button>';
      }).join('');
    document.getElementById('filterOpens').innerHTML =
      OPEN_OPTIONS.map(function (r) {
        return '<button class="filter-chip" data-type="open" data-val="' + r.v + '">'
          + r.label + '</button>';
      }).join('');

    /* 「N 个匹配 / 共 N 个」指示器 + 清除按钮 */
    var bar = document.getElementById('filterSection');
    if (!bar.querySelector('.filter-meta')) {
      var meta = document.createElement('span');
      meta.className = 'filter-meta';
      meta.innerHTML = '<span id="filterMetaText">已显示全部 332 个</span>'
        + '<button id="clearFilters" type="button" hidden>清除筛选</button>';
      bar.appendChild(meta);
    }
  }

  function applyFiltersUI() {
    var chips = document.querySelectorAll('.filter-chip');
    chips.forEach(function (c) {
      var t = c.dataset.type, v = c.dataset.val;
      var arr = state.filters[t === 'provider' ? 'providers' : t === 'region' ? 'regions' : 'opens'];
      c.classList.toggle('on', arr.indexOf(v) !== -1);
    });
    var matched = filtered().length;
    var total = R.getModels().length;
    var metaText = document.getElementById('filterMetaText');
    var clearBtn = document.getElementById('clearFilters');
    if (metaText) {
      metaText.textContent = matched === total
        ? '已显示全部 ' + total + ' 个'
        : '已筛选为 ' + matched + ' / ' + total + ' 个';
    }
    if (clearBtn) clearBtn.hidden = (state.filters.providers.length === 0
      && state.filters.regions.length === 0 && state.filters.opens.length === 0);
  }

  function toggleFilter(type, val) {
    var key = type === 'provider' ? 'providers' : type === 'region' ? 'regions' : 'opens';
    var arr = state.filters[key];
    var idx = arr.indexOf(val);
    if (idx === -1) arr.push(val); else arr.splice(idx, 1);
    applyFiltersUI();
    renderTable();
    renderChart();
  }

  function clearFilters() {
    state.filters = { providers: [], regions: [], opens: [] };
    applyFiltersUI();
    renderTable();
    renderChart();
  }

  function init() {
    document.getElementById('tabs').addEventListener('click', function (e) {
      var btn = e.target.closest('.tab');
      if (btn) setTab(btn.dataset.key);
    });
    document.getElementById('showAllBtn').addEventListener('click', function () {
      state.showAll = !state.showAll;
      renderTable();
      renderChart();
    });
    /* 表格底部的「显示全部」按钮是动态生成的，用事件委托 */
    document.getElementById('rankBody').addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action="expand"]');
      if (!btn) return;
      state.showAll = true;
      renderTable();
      renderChart();
    });
    document.getElementById('searchBox').addEventListener('input', function (e) {
      state.query = e.target.value;
      renderTable();
      renderChart();
      applyFiltersUI();
    });
    /* 筛选 chip 事件委托：点击切换 */
    document.getElementById('filterSection').addEventListener('click', function (e) {
      var chip = e.target.closest('.filter-chip');
      if (chip) toggleFilter(chip.dataset.type, chip.dataset.val);
      var clear = e.target.closest('#clearFilters');
      if (clear) clearFilters();
    });
    document.querySelectorAll('#rankTable thead th[data-key]').forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.dataset.key;
        if (state.key === k) { state.dir = -state.dir; }
        else { state.key = k; state.dir = TAB[k].dir; }
        state.showAll = false;
        document.querySelectorAll('.tab').forEach(function (b) { b.classList.toggle('active', b.dataset.key === k); });
        renderTable();
        renderChart();
      });
    });
    window.addEventListener('resize', function () { if (chart) chart.resize(); });

    /* 从 URL 读取初始排序 tab（首页 KPI 卡片跳转用），如 rank.html?key=priceIn */
    var k0 = R.qs('key');
    if (k0 && TAB[k0]) {
      state.key = k0;
      state.dir = TAB[k0].dir;
      document.querySelectorAll('.tab').forEach(function (b) {
        b.classList.toggle('active', b.dataset.key === k0);
      });
    }
    renderFilters();
    applyFiltersUI();
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

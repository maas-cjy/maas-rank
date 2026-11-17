/* 模型详情页逻辑：动态渲染 + 动态 SEO 标签 */
(function () {
  'use strict';
  var R = window.MRank;
  var radar = null;
  var posChart = null;
  var trendChart = null;
  var SITE = (window.MR_SITE && window.MR_SITE.base) || 'https://maasrank.com/';

  /* ---------- 排序 / 排名工具 ---------- */

  function sortedBy(key, dir) {
    var conv = key === 'priceIn' || key === 'priceOut';  // 混合币种，先折算成 ¥ 再排序
    return R.getModels().slice().sort(function (a, b) {
      var va = conv ? R.priceToCny(a, key) : a[key];
      var vb = conv ? R.priceToCny(b, key) : b[key];
      if (va == null) va = dir === 1 ? Infinity : -Infinity;
      if (vb == null) vb = dir === 1 ? Infinity : -Infinity;
      return (va - vb) * dir;
    });
  }

  /* 参数表价格行：官方币种优先展示，另一种货币括注折算值；
     缺失时写明「未收录」，并解释这不是免费；有价时紧邻核验月份。 */
  function fmtParamPrice(m, field) {
    if (m[field] == null) {
      return '<span class="price-missing" title="未收录官方定价：可能未公开报价、需按量询价，或本期尚未核验；不代表免费">未收录官方定价</span>';
    }
    var asof = R.priceAsOfShort(m)
      ? '<span class="price-asof" title="官方定价核验于 ' + R.esc(R.priceDateText(m)) + '">' + R.esc(R.priceAsOfShort(m)) + ' 核验</span>'
      : '';
    if (m[field] === 0) {
      return '<span class="price-free">限时免费</span>（官方标注限时免费，恢复收费请以官网现价为准）' + asof;
    }
    if (m.priceCurrency === 'CNY') {
      return '¥' + (+m[field]).toFixed(2) + '（官方人民币报价，约 ' + R.fmtUsd(+m[field] / R.USD_CNY) + '）' + asof;
    }
    return R.fmtUsd(m[field]) + '（约 ' + R.fmtCny(m[field]) + '）' + asof;
  }

  function rankOf(list, m) { return list.indexOf(m) + 1; }

  function median(vals) {
    var arr = vals.filter(function (v) { return v != null; }).sort(function (a, b) { return a - b; });
    if (!arr.length) return null;
    var n = arr.length;
    return n % 2 ? arr[(n - 1) / 2] : (arr[n / 2 - 1] + arr[n / 2]) / 2;
  }

  /* ---------- SEO：动态 title / description / canonical / JSON-LD ---------- */

  function setSeo(m) {
    var url = SITE + 'model.html?id=' + encodeURIComponent(m.id);
    var pIn = m.priceIn == null ? '未收录' : (m.priceIn === 0 ? '限时免费' : R.fmtPrice(m, 'priceIn'));
    var pOut = m.priceOut == null ? '未收录' : (m.priceOut === 0 ? '限时免费' : R.fmtPrice(m, 'priceOut'));
    var title = m.name + '（' + m.provider + '）价格、Elo 排名、上下文长度 | MaaS Rank 大模型排行榜';
    var desc = m.name + '（' + m.provider + '）——' + m.desc
      + '。竞技场 Elo ' + (m.elo == null ? '—' : m.elo) + ' 分，SuperCLUE 中文能力 ' + (m.superclue == null ? '—' : m.superclue) + ' 分，'
      + '综合能力 ' + R.fmtBench(m.bench) + ' 分，'
      + '输入 ' + pIn + ' / 百万 tokens，输出 ' + pOut + ' / 百万 tokens，上下文 ' + R.fmtCtx(m.context) + '，'
      + '输出速度 ' + (m.speed == null ? '—' : m.speed + ' tok/s') + '。数据每周自动更新。';

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
      '@type': 'SoftwareApplication',
      'name': m.name,
      'applicationCategory': 'AIApplication',
      'operatingSystem': 'API',
      'description': m.desc,
      'url': url,
      'provider': { '@type': 'Organization', 'name': m.provider },
      'datePublished': m.release || undefined,
      'offers': m.priceIn == null ? undefined : {
        '@type': 'Offer',
        'price': String(m.priceIn),
        'priceCurrency': m.priceCurrency === 'CNY' ? 'CNY' : 'USD',
        'description': '每百万输入 tokens 价格'
      }
    };
    var el = document.createElement('script');
    el.type = 'application/ld+json';
    el.textContent = JSON.stringify(ld);
    document.head.appendChild(el);
  }

  /* ---------- 视图切换 ---------- */

  function showDetail() {
    document.getElementById('viewLoading').hidden = true;
    document.getElementById('viewNotFound').hidden = true;
    document.getElementById('viewDetail').hidden = false;
  }

  function showNotFound() {
    document.getElementById('viewLoading').hidden = true;
    document.getElementById('viewDetail').hidden = true;
    document.getElementById('viewNotFound').hidden = false;
  }

  /* ---------- 渲染：头部信息 ---------- */

  function renderMeta(m) {
    document.getElementById('mName').textContent = m.name;
    document.getElementById('mDesc').textContent = m.desc;
    document.getElementById('mMeta').innerHTML =
      '<span class="chip">厂商 <b>' + R.esc(m.provider) + '</b></span>'
      + '<span class="chip">发布时间 <b>' + R.esc(m.release || '—') + '</b></span>'
      + (m.priceIn != null || m.priceOut != null
        ? '<span class="chip">价格核验 <b>' + R.esc(R.priceDateText(m)) + '</b></span>'
        : '<span class="chip">价格 <b>未收录</b></span>')
      + '<span class="chip">' + R.badgeOpen(m) + '</span>'
      + '<span class="chip">' + R.badgeRegion(m) + '</span>';
    document.getElementById('mCompare').setAttribute('href', 'compare.html?m=' + encodeURIComponent(m.id));
  }

  /* ---------- 渲染：KPI 卡片 ---------- */

  function estNote(m, key) {
    return R.isEst(m, key) ? '<span class="est-note"><span class="est-mark">*</span>估算值</span>' : '';
  }

  function kpiCard(label, num, unit, sub, extra) {
    return '<div class="card kpi-card">'
      + '<div class="kpi-label">' + label + '</div>'
      + '<div class="kpi-num">' + num + '<span class="kpi-unit"> ' + unit + '</span></div>'
      + '<div class="kpi-sub">' + sub + '</div>'
      + (extra ? '<div class="kpi-extra">' + extra + '</div>' : '')
      + '</div>';
  }

  function renderKpi(m) {
    var eloList = sortedBy('elo', -1);
    var cnList = sortedBy('superclue', -1);
    var priceList = sortedBy('priceOut', 1);
    var total = R.getModels().length;
    var html = '';

    html += kpiCard('竞技场 Elo',
      R.fmtNum(m.elo), '分',
      '全榜第 ' + rankOf(eloList, m) + ' 名 · 共 ' + total + ' 个',
      estNote(m, 'elo'));

    if (m.superclue == null) {
      html += kpiCard('SuperCLUE 智能指数',
        '<span class="kpi-missing">未收录</span>', '',
        '本期未参加中文测评，不参与该列排序',
        '未收录不等于能力为零');
    } else {
      html += kpiCard('SuperCLUE 智能指数',
        R.fmtNum(m.superclue), '分',
        '中文榜第 ' + rankOf(cnList, m) + ' 名 · 共 ' + cnList.filter(function (x) { return x.superclue != null; }).length + ' 个有效评分',
        estNote(m, 'superclue'));
    }

    if (m.priceIn == null && m.priceOut == null) {
      html += kpiCard('API 价格 · 每百万 tokens',
        '<span class="kpi-missing">未收录</span>', '',
        '未收录官方定价，不代表免费',
        '可能未公开报价或需按量询价');
    } else {
      html += kpiCard('API 价格 · 每百万 tokens',
        m.priceOut === 0 ? '限时免费' : R.fmtPrice(m, 'priceOut'), m.priceOut === 0 ? '' : '/M',
        '输出价第 ' + rankOf(priceList, m) + ' 低（' + R.priceCoverage().priced + ' 款有定价）· 输入 ' + (m.priceIn === 0 ? '限时免费' : R.fmtPrice(m, 'priceIn')),
        '价格核验 ' + R.priceDateText(m) + (m.priceIn === 0 ? ' · 官方限时免费，恢复收费请以官网现价为准' : ' · 输入价不含输出与缓存')
          + ((R.isEst(m, 'priceIn') || R.isEst(m, 'priceOut')) ? ' · <span class="est-mark">*</span>估算值' : ''));
    }

    html += kpiCard('上下文窗口',
      R.fmtCtx(m.context), 'tokens',
      '输出速度 ' + R.fmtSpeed(m.speed),
      estNote(m, 'speed'));

    document.getElementById('kpiGrid').innerHTML = html;
  }

  /* ---------- 渲染：能力雷达图（本模型 vs 榜单中位） ---------- */

  function fakeMedian() {
    var all = R.getModels();
    return {
      id: '__median__',
      name: '榜单中位',
      elo: median(all.map(function (m) { return m.elo; })),
      superclue: median(all.map(function (m) { return m.superclue; })),
      context: median(all.map(function (m) { return m.context; })),
      speed: median(all.map(function (m) { return m.speed; })),
      priceOut: median(all.map(function (m) { return m.priceOut; }))
    };
  }

  function renderRadar(m) {
    if (typeof echarts === 'undefined') return;
    if (!radar) radar = echarts.init(document.getElementById('chartRadar'));
    var all = R.getModels();
    var d = R.dims(m, all);
    var dm = R.dims(fakeMedian(), all);
    function med(key) {
      return median(all.map(function (x) { return x[key]; }));
    }
    function fmt(v) { return v == null ? null : +v.toFixed(1); }
    radar.setOption({
      tooltip: {},
      legend: { bottom: 0, textStyle: { fontSize: 12, color: '#191c23' } },
      radar: {
        indicator: [
          { name: '竞技场 Elo', max: 100 },
          { name: '中文能力', max: 100 },
          { name: '综合能力', max: 100 },
          { name: '上下文', max: 100 },
          { name: '输出速度', max: 100 },
          { name: '性价比', max: 100 }
        ],
        radius: '62%', splitNumber: 4,
        axisName: { color: '#6a7180', fontSize: 11 },
        splitArea: { areaStyle: { color: ['#ffffff', '#f7f8fc'] } },
        splitLine: { lineStyle: { color: '#e6e8ee' } },
        axisLine: { lineStyle: { color: '#e6e8ee' } }
      },
      series: [{
        type: 'radar',
        data: [
          {
            name: '本模型',
            value: [d.elo, d.cn, m.bench == null ? null : m.bench, d.ctx, d.spd, d.val].map(fmt),
            lineStyle: { color: '#4f46e5', width: 2 },
            itemStyle: { color: '#4f46e5' },
            areaStyle: { opacity: 0.1 },
            symbolSize: 4
          },
          {
            name: '榜单中位',
            value: [dm.elo, dm.cn, med('bench'), dm.ctx, dm.spd, dm.val].map(fmt),
            lineStyle: { color: '#94a3b8', width: 1.5, type: 'dashed' },
            itemStyle: { color: '#94a3b8' },
            symbolSize: 3
          }
        ]
      }]
    }, true);
  }

  /* ---------- 渲染：Elo 位次柱状图 ---------- */

  function renderPos(m) {
    if (typeof echarts === 'undefined') return;
    if (!posChart) posChart = echarts.init(document.getElementById('chartPos'));
    var list = sortedBy('elo', -1);
    var top = list.slice(0, 9);
    if (top.indexOf(m) === -1) top.push(m);
    top = top.slice().sort(function (a, b) { return (b.elo || -Infinity) - (a.elo || -Infinity); });
    var names = top.map(function (x) { return x.name; });
    var vals = top.map(function (x) { return x.elo; });
    posChart.setOption({
      grid: { left: 10, right: 40, top: 10, bottom: 10, containLabel: true },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (p) {
          var x = top[p[0].dataIndex];
          return '<b>' + R.esc(x.name) + '</b><br/>Elo：<b>' + R.fmtNum(x.elo) + '</b>'
            + (x.id === m.id ? '<br/>（本模型）' : '');
        }
      },
      xAxis: { type: 'value', axisLabel: { color: '#6a7180', fontSize: 11 } },
      yAxis: {
        type: 'category', data: names.slice().reverse(),
        axisLabel: { color: '#191c23', fontSize: 12 },
        axisLine: { show: false }, axisTick: { show: false }
      },
      series: [{
        type: 'bar', data: vals.slice().reverse(), barWidth: '58%',
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: function (p) { return top[vals.length - 1 - p.dataIndex].id === m.id ? '#f59e0b' : '#6366f1'; }
        },
        label: { show: true, position: 'right', fontSize: 11, color: '#6a7180' }
      }]
    }, true);
  }

  /* ---------- 渲染：SuperCLUE 能力六维（横向条） ---------- */

  function renderDims(m) {
    var list = R.dimList(m);
    var box = document.getElementById('chartDims');
    var note = document.getElementById('dimsNote');
    if (!list.length) {
      var basis = (R.getMeta().basisChange || {});
      box.innerHTML = '';
      note.textContent = '该模型暂无 SuperCLUE 六维评测数据（海外模型多为参考值）。'
        + (basis.field === 'superclue'
          ? ' 自 ' + basis.period + ' 起采用新评分口径，未参加该期测评的模型暂无分数。' : '');
      return;
    }
    var basis = (R.getMeta().basisChange || {});
    note.textContent = '综合能力分 ' + R.fmtBench(m.bench) + ' = 六维子分平均值，满分 100。'
      + (basis.field === 'superclue' ? ' ' + basis.note : '');
    box.innerHTML = list.map(function (x) {
      var w = Math.max(0, Math.min(100, x.value));
      return '<div class="dim-row">'
        + '<span class="dim-label">' + R.esc(x.label) + '</span>'
        + '<div class="dim-track"><div class="dim-fill" style="width:' + w + '%"></div></div>'
        + '<span class="dim-val">' + (+x.value).toFixed(1) + '</span>'
        + '</div>';
    }).join('');
  }

  /* ---------- 渲染：竞技场 Elo 历史趋势（每周快照） ---------- */

  function renderTrend(m, hist) {
    var note = document.getElementById('trendNote');
    if (typeof echarts === 'undefined') { note.textContent = '图表库未加载，无法渲染趋势。'; return; }
    var snaps = (hist && hist.snapshots) ? hist.snapshots : [];
    var dates = [], elos = [];
    snaps.forEach(function (s) {
      var sm = s.models ? s.models.filter(function (x) { return x.id === m.id; })[0] : null;
      if (sm && sm.elo != null) {
        dates.push(s.date);
        elos.push(sm.elo);
      }
    });
    var curDate = R.getMeta().updated;
    if (!dates.length || dates[dates.length - 1] !== curDate) {
      if (m.elo != null) {
        dates.push(curDate);
        elos.push(m.elo);
      }
    } else {
      elos[elos.length - 1] = m.elo;
    }
    if (dates.length < 2) {
      if (!trendChart) trendChart = echarts.init(document.getElementById('chartTrend'));
      trendChart.clear();
      note.textContent = '历史快照积累中（当前 ' + dates.length + ' 期）。数据每周自动更新，趋势将逐渐丰富。';
      return;
    }
    note.textContent = '折线展示该模型在各周数据快照中的竞技场 Elo，末端为最新一期。';
    if (!trendChart) trendChart = echarts.init(document.getElementById('chartTrend'));
    trendChart.setOption({
      grid: { left: 12, right: 30, top: 24, bottom: 10, containLabel: true },
      tooltip: {
        trigger: 'axis',
        formatter: function (p) {
          return '<b>' + R.esc(m.name) + '</b><br/>' + R.esc(dates[p[0].dataIndex])
            + ' · Elo：<b>' + R.fmtNum(elos[p[0].dataIndex]) + '</b>';
        }
      },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#6a7180', fontSize: 11 } },
      yAxis: {
        type: 'value', scale: true,
        axisLabel: { color: '#6a7180', fontSize: 11 },
        splitLine: { lineStyle: { color: '#eef0f5' } }
      },
      series: [{
        type: 'line', data: elos, smooth: true, symbolSize: 7,
        lineStyle: { color: '#4f46e5', width: 2 },
        itemStyle: { color: '#4f46e5' },
        areaStyle: { color: 'rgba(79, 70, 229, 0.08)' },
        label: { show: true, position: 'top', fontSize: 11, color: '#6a7180' }
      }]
    }, true);
  }

  /* ---------- 渲染：详细参数表 ---------- */

  function renderParams(m) {
    var rows = [
      ['厂商', R.esc(m.provider)],
      ['开源 / 闭源', R.badgeOpen(m)],
      ['属地', R.badgeRegion(m)],
      ['发布时间', R.esc(m.release || '—')],
      ['竞技场 Elo', R.fmtNum(m.elo) + R.estMark(m, 'elo')],
      ['SuperCLUE 智能指数', R.fmtNum(m.superclue) + R.estMark(m, 'superclue')],
      ['综合能力分', R.fmtBench(m.bench) + R.estMark(m, 'bench')],
      ['输入价格', fmtParamPrice(m, 'priceIn') + R.estMark(m, 'priceIn')],
      ['输出价格', fmtParamPrice(m, 'priceOut') + R.estMark(m, 'priceOut')],
      (m.priceSource === '官网'
        ? ['价格来源', '<span class="src-official">官网直采</span> '
          + R.esc(R.priceDateText(m)) + ' 核验 · ' + R.esc(m.priceNote || '高峰时段刊例价')]
        : ['价格来源', 'SuperCLUE 价格库 ' + R.esc(R.priceDateText(m)) + '（国产为官方人民币报价）']),
      ['上下文窗口', R.fmtCtx(m.context)],
      ['输出速度', R.fmtSpeed(m.speed) + R.estMark(m, 'speed')]
    ];
    document.getElementById('paramBody').innerHTML = rows.map(function (r) {
      return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>';
    }).join('');
  }

  /* ---------- 渲染：同厂商模型 ---------- */

  function renderProvider(m) {
    var others = R.getModels().filter(function (x) {
      return x.provider === m.provider && x.id !== m.id;
    });
    document.getElementById('providerSub').textContent = others.length
      ? m.provider + ' 旗下其他已收录模型'
      : '暂无 ' + m.provider + ' 的其他已收录模型';
    document.getElementById('providerLinks').innerHTML = others.map(function (x) {
      return '<a class="link-item" href="model.html?id=' + encodeURIComponent(x.id) + '">'
        + R.esc(x.name) + '<span>' + R.fmtNum(x.elo) + ' Elo</span></a>';
    }).join('') || '<p class="dim-note">可在 <a href="compare.html">模型对比</a> 页查看其他厂商模型。</p>';
  }

  /* ---------- 初始化 ---------- */

  R.loadData().then(function () {
    document.getElementById('footDate').textContent = R.getMeta().updated;

    var id = R.qs('id');
    var m = id ? R.getModel(id) : null;
    if (!m) { showNotFound(); return; }

    showDetail();
    setSeo(m);
    renderMeta(m);
    renderKpi(m);
    renderRadar(m);
    renderPos(m);
    renderDims(m);
    renderParams(m);
    renderProvider(m);

    var ul = document.getElementById('sources');
    ul.innerHTML = R.getMeta().sources.map(function (s) {
      return '<li><span class="src-name">' + R.esc(s.name) + '</span>'
        + '<span class="src-desc">' + R.esc(s.desc)
        + (s.url ? ' · <a href="' + R.esc(s.url) + '" target="_blank" rel="noopener">访问官网</a>' : '') + '</span></li>';
    }).join('');

    return fetch('data/history.json', { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .catch(function () { return null; });
  }).then(function (hist) {
    var m = R.getModel(R.qs('id'));
    if (m) renderTrend(m, hist);

    window.addEventListener('resize', function () {
      if (radar) radar.resize();
      if (posChart) posChart.resize();
      if (trendChart) trendChart.resize();
    });
  }).catch(function (err) {
    document.getElementById('viewLoading').innerHTML =
      '<h1>数据加载失败</h1><p>' + R.esc(err.message) + '。请通过本地服务器访问（如 python3 -m http.server）。</p>';
  });
})();

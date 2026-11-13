/* API 成本计算器逻辑 */
(function () {
  'use strict';
  var R = window.MRank;

  var MAX = 4;
  var selected = [];
  var chart = null;

  function num(id, fallback) {
    var v = parseFloat(document.getElementById(id).value);
    return isNaN(v) || v < 0 ? fallback : v;
  }

  /* 月成本（¥）：未命中输入×输入价 + 命中输入×输入价×(1−缓存折扣) + 输出×输出价 */
  function monthlyCost(m, inTok, outTok, hit, off) {
    if (m.priceIn == null && m.priceOut == null) return null;
    var pin = m.priceIn || 0, pout = m.priceOut || 0;
    var usd = (inTok * (1 - hit) * pin)
      + (inTok * hit * pin * (1 - off))
      + (outTok * pout);
    return usd * R.USD_CNY;
  }

  function fmtCnyBig(v) {
    if (v == null) return '—';
    if (v >= 10000) return '¥' + (v / 10000).toFixed(2) + ' 万';
    return '¥' + v.toFixed(2);
  }

  function renderPicker() {
    var kw = document.getElementById('search').value.trim().toLowerCase();
    var models = R.getModels().filter(function (m) {
      return m.priceIn != null || m.priceOut != null;
    }).sort(function (a, b) {
      if (a.region !== b.region) return a.region === 'china' ? -1 : 1;
      return ((a.priceIn || 0) + (a.priceOut || 0)) - ((b.priceIn || 0) + (b.priceOut || 0));
    });
    var html = '';
    models.forEach(function (m) {
      var hit = !kw || m.name.toLowerCase().indexOf(kw) > -1 || m.provider.toLowerCase().indexOf(kw) > -1;
      if (!hit) return;
      var on = selected.indexOf(m.id) > -1;
      var full = !on && selected.length >= MAX;
      html += '<label class="picker-item' + (full ? ' disabled' : '') + '">'
        + '<input type="checkbox" value="' + R.esc(m.id) + '"' + (on ? ' checked' : '') + (full ? ' disabled' : '') + '>'
        + '<span class="pi-name">' + R.esc(m.name) + '</span>'
        + '<span class="pi-prov">' + R.esc(m.provider) + ' · ¥' + (m.priceIn == null ? '—' : (m.priceIn * R.USD_CNY).toFixed(1)) + '/' + (m.priceOut == null ? '—' : (m.priceOut * R.USD_CNY).toFixed(1)) + '</span>'
        + '</label>';
    });
    document.getElementById('pickerList').innerHTML = html || '<p class="empty">没有匹配的模型</p>';
  }

  function render() {
    var inTok = num('inTok', 10), outTok = num('outTok', 2);
    var hit = Math.min(0.95, num('cacheHit', 30) / 100);
    var off = Math.min(0.95, num('cacheOff', 50) / 100);
    var reqs = num('reqs', 0); /* 万次 */

    var models = selected.map(R.getModel).filter(Boolean);
    var priced = models.filter(function (m) { return m.priceIn != null || m.priceOut != null; });
    var rows = priced.map(function (m) {
      var cost = monthlyCost(m, inTok, outTok, hit, off);
      return { m: m, cost: cost, per: (reqs > 0 && cost != null) ? cost / (reqs * 10000) : null };
    }).sort(function (a, b) { return (a.cost || Infinity) - (b.cost || Infinity); });

    /* 汇总 */
    var sumEl = document.getElementById('calcSummary');
    if (!selected.length) {
      sumEl.textContent = '在左侧勾选模型后自动计算。';
    } else if (!priced.length) {
      sumEl.textContent = '所选模型暂无价格数据。';
    } else {
      var missing = selected.length - priced.length;
      sumEl.textContent = '按每月输入 ' + inTok + 'M / 输出 ' + outTok + 'M tokens、缓存命中 '
        + Math.round(hit * 100) + '%、缓存读价折扣 ' + Math.round(off * 100) + '% 估算，汇率 $1≈¥'
        + R.USD_CNY + '。'
        + (missing > 0 ? '另有 ' + missing + ' 个所选模型缺少价格数据，未参与对比。' : '');
    }

    /* 表格 */
    var tbody = document.getElementById('costBody');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">请勾选至少 1 个有价格数据的模型</td></tr>';
    } else {
      tbody.innerHTML = rows.map(function (r, i) {
        var m = r.m;
        var pin = m.priceIn == null ? '—' : '¥' + (m.priceIn * R.USD_CNY).toFixed(2);
        var pout = m.priceOut == null ? '—' : '¥' + (m.priceOut * R.USD_CNY).toFixed(2);
        return '<tr' + (i === 0 && rows.length > 1 ? ' class="row-top3"' : '') + '>'
          + '<td><a href="model.html?id=' + encodeURIComponent(m.id) + '">' + R.esc(m.name) + '</a>'
          + '<div class="mprov">' + R.esc(m.provider) + '</div></td>'
          + '<td class="num">' + pin + R.estMark(m, 'priceIn') + '</td>'
          + '<td class="num">' + pout + R.estMark(m, 'priceOut') + '</td>'
          + '<td class="num"><b>' + fmtCnyBig(r.cost) + '</b></td>'
          + '<td class="num">' + (r.per == null ? '—' : '¥' + r.per.toFixed(4)) + '</td>'
          + '</tr>';
      }).join('');
    }

    /* 图表 */
    if (typeof echarts === 'undefined') return;
    if (!chart) chart = echarts.init(document.getElementById('costChart'));
    if (!rows.length) { chart.clear(); return; }
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: function (v) { return v == null ? '—' : '¥' + Number(v).toLocaleString('zh-CN'); } },
      grid: { left: 10, right: 70, top: 10, bottom: 10, containLabel: true },
      xAxis: { type: 'value', name: '¥ / 月', nameTextStyle: { color: '#6a7180' }, axisLabel: { color: '#6a7180', fontSize: 11 } },
      yAxis: {
        type: 'category', data: rows.map(function (r) { return r.m.name; }).reverse(),
        axisLabel: { color: '#191c23', fontSize: 12 },
        axisLine: { show: false }, axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        data: rows.map(function (r) { return r.cost == null ? null : +r.cost.toFixed(2); }).reverse(),
        barWidth: '55%',
        itemStyle: { borderRadius: [0, 6, 6, 0], color: '#6366f1' },
        label: { show: true, position: 'right', fontSize: 11, color: '#6a7180', formatter: function (p) { return p.value == null ? '' : '¥' + Number(p.value).toLocaleString('zh-CN'); } }
      }]
    }, true);
  }

  function init() {
    document.getElementById('pickerList').addEventListener('change', function (e) {
      if (e.target.type !== 'checkbox') return;
      var id = e.target.value;
      var i = selected.indexOf(id);
      if (i > -1) selected.splice(i, 1);
      else if (selected.length < MAX) selected.push(id);
      renderPicker();
      render();
    });
    document.getElementById('search').addEventListener('input', renderPicker);
    ['inTok', 'outTok', 'cacheHit', 'cacheOff', 'reqs'].forEach(function (id) {
      document.getElementById(id).addEventListener('input', render);
    });
    window.addEventListener('resize', function () { if (chart) chart.resize(); });
  }

  R.loadData().then(function () {
    var meta = R.getMeta();
    /* 价格日期单独取：页面快照日 ≠ 价格核验日（价格表可能已停更数月） */
    var priceDate = (meta.fieldInfo && meta.fieldInfo.price && meta.fieldInfo.price.date) || meta.updated;
    document.getElementById('dataDate').textContent = meta.updated;
    var pd = document.getElementById('priceDate');
    if (pd) pd.textContent = priceDate;
    document.getElementById('footDate').textContent = priceDate;
    document.getElementById('footDate2').textContent = meta.updated;
    init();
    /* 支持预选：cost.html?models=id1,id2 */
    (R.qs('models') || '').split(',').filter(Boolean).forEach(function (id) {
      if (R.getModel(id) && selected.length < MAX) selected.push(id);
    });
    renderPicker();
    render();
  }).catch(function (err) {
    document.getElementById('pickerList').innerHTML = '<p class="empty">数据加载失败：' + R.esc(err.message) + '</p>';
  });
})();

/* 模型对比页逻辑 */
(function () {
  'use strict';
  var R = window.MRank;

  var MAX = 4;
  var selected = [];
  var radar = null;
  var priceChart = null;

  var COLORS = ['#4f46e5', '#0e9f6e', '#d97706', '#dc2626'];

  function renderPicker() {
    var kw = document.getElementById('search').value.trim().toLowerCase();
    var models = R.getModels().slice().sort(function (a, b) {
      if (a.region !== b.region) return a.region === 'china' ? -1 : 1;
      return (b.elo || 0) - (a.elo || 0);
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
        + '<span class="pi-prov">' + R.esc(m.provider) + ' · ' + R.regionName(m.region) + '</span>'
        + '</label>';
    });
    document.getElementById('pickerList').innerHTML = html || '<p class="empty">没有匹配的模型</p>';
  }

  function toggle(id) {
    var i = selected.indexOf(id);
    if (i > -1) { selected.splice(i, 1); }
    else if (selected.length < MAX) { selected.push(id); }
    renderPicker();
    renderAll();
  }

  function renderAll() {
    var models = selected.map(R.getModel).filter(Boolean);
    document.querySelector('.cmp-main').style.opacity = models.length ? '1' : '.45';
    renderRadar(models);
    renderPrice(models);
    renderTable(models);
  }

  function renderRadar(models) {
    if (typeof echarts === 'undefined') return;
    if (!radar) radar = echarts.init(document.getElementById('chartRadar'));
    if (!models.length) { radar.clear(); return; }

    var IND = [
      { name: '竞技场 Elo', max: 100 },
      { name: '中文能力', max: 100 },
      { name: '上下文', max: 100 },
      { name: '输出速度', max: 100 },
      { name: '性价比', max: 100 }
    ];
    var series = models.map(function (m, i) {
      var d = R.dims(m, models);
      return {
        name: m.name,
        value: [d.elo, d.cn, d.ctx, d.spd, d.val].map(function (v) { return v == null ? null : +v.toFixed(1); }),
        lineStyle: { color: COLORS[i % COLORS.length], width: 2 },
        itemStyle: { color: COLORS[i % COLORS.length] },
        areaStyle: { opacity: 0.08 },
        symbolSize: 4
      };
    });
    radar.setOption({
      tooltip: {},
      legend: {
        bottom: 0, textStyle: { fontSize: 12, color: '#191c23' },
        data: models.map(function (m) { return m.name; })
      },
      radar: {
        indicator: IND,
        radius: '62%',
        splitNumber: 4,
        axisName: { color: '#6a7180', fontSize: 11 },
        splitArea: { areaStyle: { color: ['#ffffff', '#f7f8fc'] } },
        splitLine: { lineStyle: { color: '#e6e8ee' } },
        axisLine: { lineStyle: { color: '#e6e8ee' } }
      },
      series: [{ type: 'radar', data: series }]
    }, true);
  }

  function renderPrice(models) {
    if (typeof echarts === 'undefined') return;
    if (!priceChart) priceChart = echarts.init(document.getElementById('chartPrice'));
    if (!models.length) { priceChart.clear(); return; }
    priceChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: function (v) { return v == null ? '—' : '¥' + v.toFixed(2) + ' / 百万 tokens'; } },
      legend: { data: ['输入价', '输出价'], textStyle: { fontSize: 12, color: '#191c23' } },
      grid: { left: 50, right: 20, top: 40, bottom: 10, containLabel: true },
      xAxis: {
        type: 'category', data: models.map(function (m) { return m.name; }),
        axisLabel: { color: '#191c23', fontSize: 11, interval: 0, rotate: models.length > 2 ? 18 : 0 }
      },
      yAxis: { type: 'value', name: '¥ / 百万 tokens', axisLabel: { color: '#6a7180', fontSize: 11 }, splitLine: { lineStyle: { color: '#eef0f5' } } },
      series: [
        { name: '输入价', type: 'bar', data: models.map(function (m) { return m.priceIn == null ? null : +(m.priceIn * R.USD_CNY).toFixed(2); }), itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] }, barMaxWidth: 26 },
        { name: '输出价', type: 'bar', data: models.map(function (m) { return m.priceOut == null ? null : +(m.priceOut * R.USD_CNY).toFixed(2); }), itemStyle: { color: '#0e9f6e', borderRadius: [4, 4, 0, 0] }, barMaxWidth: 26 }
      ]
    }, true);
  }

  function renderTable(models) {
    var tbody = document.getElementById('cmpTable');
    if (!models.length) {
      tbody.innerHTML = '<tr><td colspan="' + (models.length + 1) + '" class="empty">请在左侧勾选至少 1 个模型</td></tr>';
      return;
    }
    var rows = [
      { label: '厂商', cell: function (m) { return R.esc(m.provider); } },
      { label: '开源', cell: function (m) { return R.badgeOpen(m); } },
      { label: '属地', cell: function (m) { return R.badgeRegion(m); } },
      { label: '发布时间', cell: function (m) { return R.esc(m.release); } },
      { label: '竞技场 Elo', key: 'elo', cell: function (m) { return R.fmtNum(m.elo) + R.estMark(m, 'elo'); }, best: 'max' },
      { label: 'SuperCLUE', key: 'superclue', cell: function (m) { return R.fmtNum(m.superclue) + R.estMark(m, 'superclue'); }, best: 'max' },
      { label: '输入价 ¥/M', key: 'priceIn', cell: function (m) { return R.fmtCny(m.priceIn) + R.estMark(m, 'priceIn'); }, best: 'min' },
      { label: '输出价 ¥/M', key: 'priceOut', cell: function (m) { return R.fmtCny(m.priceOut) + R.estMark(m, 'priceOut'); }, best: 'min' },
      { label: '上下文', key: 'context', cell: function (m) { return R.fmtCtx(m.context); }, best: 'max' },
      { label: '输出速度', key: 'speed', cell: function (m) { return R.fmtSpeed(m.speed) + R.estMark(m, 'speed'); }, best: 'max' }
    ];
    var head = '<tr><th></th>' + models.map(function (m) { return '<th>' + R.esc(m.name) + '</th>'; }).join('') + '</tr>';
    var body = rows.map(function (row) {
      var bestIdx = -1;
      if (row.key) {
        var vals = models.map(function (m) { return m[row.key]; });
        var present = vals.filter(function (v) { return v != null; });
        if (present.length) {
          var bestV = row.best === 'min' ? Math.min.apply(null, present) : Math.max.apply(null, present);
          bestIdx = vals.indexOf(bestV);
        }
      }
      var tds = models.map(function (m, i) {
        return '<td' + (i === bestIdx ? ' class="best"' : '') + '>' + row.cell(m) + '</td>';
      }).join('');
      return '<tr><td>' + row.label + '</td>' + tds + '</tr>';
    }).join('');
    tbody.innerHTML = head + body;
  }

  function init() {
    document.getElementById('pickerList').addEventListener('change', function (e) {
      if (e.target.type === 'checkbox') toggle(e.target.value);
    });
    document.getElementById('search').addEventListener('input', renderPicker);
    window.addEventListener('resize', function () {
      if (radar) radar.resize();
      if (priceChart) priceChart.resize();
    });
  }

  R.loadData().then(function () {
    document.getElementById('footDate').textContent = R.getMeta().updated;
    init();
    var pre = (R.qs('m') || '').split(',').filter(Boolean);
    pre.forEach(function (id) { if (R.getModel(id) && selected.length < MAX) selected.push(id); });
    renderPicker();
    renderAll();
  }).catch(function (err) {
    document.getElementById('pickerList').innerHTML = '<p class="empty">数据加载失败：' + R.esc(err.message) + '</p>';
  });
})();

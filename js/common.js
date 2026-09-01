/* 公共工具：数据加载、格式化、徽章 */
(function () {
  'use strict';

  const USD_CNY = 7.2;

  let MODELS = [];
  let META = null;

  async function loadData() {
    const res = await fetch('data/models.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('数据加载失败 HTTP ' + res.status);
    const d = await res.json();
    META = d.meta;
    MODELS = d.models;
    return d;
  }

  function getModels() { return MODELS; }
  function getMeta() { return META; }
  function getModel(id) { return MODELS.find(function (m) { return m.id === id; }); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtNum(v) { return v == null || isNaN(v) ? '—' : Number(v).toLocaleString('zh-CN'); }

  function fmtUsd(v) { return v == null ? '—' : '$' + (+v).toFixed(2); }

  function fmtCny(v) { return v == null ? '—' : '¥' + (+v * USD_CNY).toFixed(2); }

  function fmtCtx(v) {
    if (v == null) return '—';
    if (v >= 1000000) return (v / 1000000).toLocaleString('zh-CN') + 'M';
    if (v >= 1000) return (v / 1000).toLocaleString('zh-CN') + 'K';
    return fmtNum(v);
  }

  function fmtSpeed(v) { return v == null ? '—' : fmtNum(v) + ' tok/s'; }

  /* 综合能力分（SuperCLUE 六维子分平均，0–100） */
  function fmtBench(v) { return v == null ? '—' : (+v).toFixed(1); }

  /* SuperCLUE 六维子分：中文键名 -> 展示名 */
  const DIM_KEYS = {
    math: '数学推理', hallu: '幻觉控制', science: '科学推理',
    ifollow: '指令遵循', coding: '智能体编程', plan: '任务规划'
  };

  /* 返回模型的六维列表 [{key, label, value}]，缺维度自动跳过 */
  function dimList(m) {
    if (!m || !m.dims) return [];
    return Object.keys(DIM_KEYS).filter(function (k) {
      return m.dims[k] != null;
    }).map(function (k) {
      return { key: k, label: DIM_KEYS[k], value: m.dims[k] };
    });
  }

  function isEst(m, key) {
    if (!m.est) return false;
    if (key && !m.est[key]) return false;
    return true;
  }

  function estMark(m, key) {
    return isEst(m, key) ? '<span class="est-mark" title="估算值，以官方发布为准">*</span>' : '';
  }

  function badgeOpen(m) {
    return m.open
      ? '<span class="badge open">开源</span>'
      : '<span class="badge closed">闭源</span>';
  }

  function badgeRegion(m) {
    return m.region === 'china'
      ? '<span class="badge cn">国内</span>'
      : '<span class="badge" style="color:#6a7180;border-color:#e0e3ea;background:#f8f9fb;">海外</span>';
  }

  function regionName(r) { return r === 'china' ? '国内' : '海外'; }

  /* 雷达图维度归一化（固定标尺，保证跨模型可比） */
  function dims(m, selected) {
    var outPrices = selected.map(function (x) { return x.priceOut; }).filter(function (v) { return v != null; });
    var maxP = outPrices.length ? Math.max.apply(null, outPrices) : 1;
    var minP = outPrices.length ? Math.min.apply(null, outPrices) : 0;
    function val() {
      if (m.priceOut == null) return null;
      if (maxP === minP) return 100;
      return Math.max(0, Math.min(100, (maxP - m.priceOut) / (maxP - minP) * 100));
    }
    return {
      elo: m.elo == null ? null : Math.max(0, Math.min(100, (m.elo - 1300) / 250 * 100)),
      cn: m.superclue == null ? null : Math.max(0, Math.min(100, (m.superclue - 50) / 28 * 100)),
      ctx: m.context == null ? null : Math.max(0, Math.min(100, (Math.log10(m.context) - 5) * 100)),
      spd: m.speed == null ? null : Math.max(0, Math.min(100, m.speed / 250 * 100)),
      val: val()
    };
  }

  function qs(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  window.MRank = {
    USD_CNY: USD_CNY,
    loadData: loadData,
    getModels: getModels,
    getMeta: getMeta,
    getModel: getModel,
    esc: esc,
    fmtNum: fmtNum,
    fmtUsd: fmtUsd,
    fmtCny: fmtCny,
    fmtCtx: fmtCtx,
    fmtSpeed: fmtSpeed,
    fmtBench: fmtBench,
    DIM_KEYS: DIM_KEYS,
    dimList: dimList,
    isEst: isEst,
    estMark: estMark,
    badgeOpen: badgeOpen,
    badgeRegion: badgeRegion,
    regionName: regionName,
    dims: dims,
    qs: qs
  };

  /* 移动端导航展开/收起 */
  document.addEventListener('DOMContentLoaded', function () {
    const nav = document.querySelector('.nav');
    const toggle = document.querySelector('.nav-toggle');
    if (!toggle || !nav) return;
    toggle.addEventListener('click', function () {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? '✕' : '☰';
    });
  });
})();

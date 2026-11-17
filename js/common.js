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

  /* 宽松规范化 id：忽略大小写与分隔符（"Kimi K3" ≡ "kimi-k3"） */
  function canonId(s) {
    return String(s || '').toLowerCase().replace(/[^a-z0-9.\u4e00-\u9fff]/g, '');
  }

  /* 按 id 取模型：精确匹配 → aliases 匹配 → 规范形匹配（旧链接自动兼容） */
  function getModel(id) {
    if (!id) return undefined;
    let m = MODELS.find(function (x) { return x.id === id; });
    if (m) return m;
    m = MODELS.find(function (x) {
      return Array.isArray(x.aliases) && x.aliases.indexOf(id) !== -1;
    });
    if (m) return m;
    const q = canonId(id);
    return MODELS.find(function (x) { return canonId(x.id) === q; });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function fmtNum(v) { return v == null || isNaN(v) ? '—' : Number(v).toLocaleString('zh-CN'); }

  function fmtUsd(v) { return v == null ? '—' : '$' + (+v).toFixed(2); }

  function fmtCny(v) { return v == null ? '—' : '¥' + (+v * USD_CNY).toFixed(2); }

  /* 价格换算（统一折算为 ¥）：priceCurrency 为 CNY 的模型原样展示（官方人民币报价），
     其余（含缺省）按美元 ×7.2 换算。所有价格展示与排序必须经过这里，禁止直接 ×7.2。 */
  function priceToCny(m, field) {
    var v = m ? m[field] : null;
    if (v == null) return null;
    return m.priceCurrency === 'CNY' ? +v : +v * USD_CNY;
  }

  function fmtPrice(m, field) {
    var v = priceToCny(m, field);
    return v == null ? '—' : '¥' + v.toFixed(2);
  }

  /* ---------- 价格时效 / 覆盖率 ----------
     价格是本页最容易过期的字段：数据源 2026-07 后停更，页面快照日却是每天新的。
     所以价格必须在「用到它的地方」自带核验日期，而不是只在页脚写一句。 */

  function priceFieldInfo() {
    return (META && META.fieldInfo && META.fieldInfo.price) || {};
  }

  /* 单模型价格日期优先（便于将来逐模型核验），否则回落到全站价格数据期 */
  function priceDateRaw(m) {
    return (m && m.priceDate) || priceFieldInfo().date || '';
  }

  /* 统一成 YYYY-MM：兼容 "2026-07" / "2026年7月" */
  function priceDateISO(m) {
    var hit = /(\d{4})\D+(\d{1,2})/.exec(priceDateRaw(m));
    return hit ? hit[1] + '-' + ('0' + hit[2]).slice(-2) : '';
  }

  function priceDateText(m) {
    var raw = priceDateRaw(m);
    var iso = priceDateISO(m);
    /* 统一成中文数据期（2026年7月）：正文里比 2026-07 易读，
       紧凑角标另用 priceAsOfShort() 输出「07月」。 */
    if (raw && raw.indexOf('年') > -1) return raw;
    if (iso) {
      var p = iso.split('-');
      return p[0] + '年' + parseInt(p[1], 10) + '月';
    }
    return raw || '未知';
  }

  function priceAsOfShort(m) {
    var iso = priceDateISO(m);
    return iso ? iso.slice(5) + '月' : '';
  }

  /* 距今天数折算的月数，用来提示「已经四个月没核验」 */
  function priceAgeMonths(m) {
    var iso = priceDateISO(m);
    if (!iso) return null;
    var p = iso.split('-');
    var now = new Date();
    var months = (now.getFullYear() - +p[0]) * 12 + (now.getMonth() + 1 - +p[1]);
    return months > 0 ? months : 0;
  }

  /* 价格单元格：数字 + 紧邻的核验月份。缺失时写明「未收录」并解释，
     避免读者把 — 误读成 0 元 / 免费。 */
  function priceCell(m, field) {
    if (!m || m[field] == null) {
      return '<span class="price-missing" title="未收录官方定价：可能未公开报价、需按量询价，或本期尚未核验；不代表免费">未收录</span>';
    }
    var short = priceAsOfShort(m);
    var d = priceDateText(m);
    var srcMark = m.priceSource === '官网'
      ? '<span class="src-official" title="价格直采自厂商官网（' + esc(d) + '核验）">官网</span>'
      : '';
    return fmtPrice(m, field)
      + (short ? '<span class="price-asof" title="官方定价核验于 ' + esc(d) + '">' + esc(short) + '</span>' : '')
      + srcMark;
  }

  function priceCoverage() {
    var list = MODELS || [];
    var priced = 0;
    list.forEach(function (m) { if (m.priceIn != null || m.priceOut != null) priced++; });
    return { priced: priced, total: list.length };
  }

  /* 全站统一的价格口径说明（表格脚注 / 计算器 / 详情页复用） */
  function priceNote() {
    var cov = priceCoverage();
    var age = priceAgeMonths();
    return '价格核验于 ' + priceDateText()
      + (age != null ? '（约 ' + age + ' 个月前）' : '')
      + '，仅覆盖 ' + cov.priced + ' / ' + cov.total + ' 款模型；未收录不代表免费，调价请以厂商官网为准。';
  }

  function fmtCtx(v) {
    if (v == null) return '—';
    if (v >= 1000000) return (v / 1000000).toLocaleString('zh-CN') + 'M';
    if (v >= 1000) return (v / 1000).toLocaleString('zh-CN') + 'K';
    return fmtNum(v);
  }

  function fmtSpeed(v) { return v == null ? '—' : fmtNum(v) + ' tok/s'; }

  /* 综合能力分（SuperCLUE 六维子分平均，0–100） */
  function fmtBench(v) { return v == null ? '—' : (+v).toFixed(1); }

  /* SuperCLUE 维度子分：数据键名 -> 展示名。
     2026-11 新口径：数理推理替代数学推理，科学推理/任务规划停更，新增超长上下文。
     science/plan 保留映射是为了兼容切换前的历史快照数据。 */
  const DIM_KEYS = {
    math: '数理推理', hallu: '幻觉控制', science: '科学推理',
    ifollow: '精确指令遵循', coding: '智能体编程', plan: '任务规划',
    longctx: '超长上下文'
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
    priceToCny: priceToCny,
    fmtPrice: fmtPrice,
    priceCell: priceCell,
    priceDateText: priceDateText,
    priceDateISO: priceDateISO,
    priceAsOfShort: priceAsOfShort,
    priceAgeMonths: priceAgeMonths,
    priceCoverage: priceCoverage,
    priceNote: priceNote,
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

  /* 数据源异常提示条：
     由 scripts/check_health.py 生成 data/health.json。只有判定为 stale
     （连续 2 周抓取失败，或数据超过 14 天无变化）时才展示，避免误报噪音。 */
  function renderHealthBanner() {
    const main = document.querySelector('main');
    if (!main) return;

    fetch('data/health.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (h) {
        if (!h || !h.stale || !h.message) return;
        if (document.querySelector('.data-alert')) return;

        const bar = document.createElement('div');
        bar.className = 'data-alert';
        bar.setAttribute('role', 'status');
        bar.innerHTML = '<span class="data-alert-icon" aria-hidden="true">⚠</span>'
          + '<div class="data-alert-body">'
          +   '<b>数据更新延迟</b>'
          +   '<span>' + esc(h.message)
          +     ' 最近核对：' + esc(h.checked || '—') + '。'
          +     '<a href="about.html">查看数据说明</a>'
          +   '</span>'
          + '</div>';
        main.insertBefore(bar, main.firstChild);
      })
      .catch(function () { /* health.json 缺失或损坏时静默跳过，不影响页面 */ });
  }

  /* 移动端导航展开/收起 */
  document.addEventListener('DOMContentLoaded', function () {
    renderHealthBanner();

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

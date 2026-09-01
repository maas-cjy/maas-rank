/* 文章中心：读取 data/articles.json 渲染文章列表 */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function card(a) {
    var tags = (a.tags || []).map(function (t) {
      return '<span class="art-tag">' + esc(t) + '</span>';
    }).join('');
    return '<a class="art-card" href="articles/' + encodeURIComponent(a.file) + '">'
      + '<div class="art-date">' + esc(a.date) + (a.issue ? ' · 第 ' + a.issue + ' 期' : '') + '</div>'
      + '<h2 class="art-title">' + esc(a.title) + '</h2>'
      + '<p class="art-summary">' + esc(a.summary) + '</p>'
      + (tags ? '<div class="art-tags">' + tags + '</div>' : '')
      + '</a>';
  }

  function render(arts) {
    var list = (arts || []).filter(function (a) { return !a.draft; });
    var box = document.getElementById('artList');
    var countEl = document.getElementById('artCount');
    var latestEl = document.getElementById('artLatest');

    if (countEl) countEl.textContent = list.length + ' 篇文章';
    if (latestEl && list.length) latestEl.textContent = '最近更新 ' + list[0].date;

    if (!list.length) {
      box.innerHTML = '<section class="card"><p class="sub" style="padding:24px 0;text-align:center;">'
        + '暂无文章，每周数据更新后会自动生成榜单解读，敬请期待。</p></section>';
      return;
    }
    box.innerHTML = list.map(card).join('');
  }

  function init() {
    fetch('data/articles.json')
      .then(function (r) { return r.json(); })
      .then(function (arts) {
        render(arts);
        return fetch('data/models.json').then(function (r) { return r.json(); });
      })
      .then(function (d) {
        var fc = document.getElementById('footDate');
        if (fc && d && d.meta && d.meta.updated) fc.textContent = d.meta.updated;
      })
      .catch(function () {
        document.getElementById('artList').innerHTML =
          '<section class="card"><p class="sub" style="padding:24px 0;text-align:center;">文章加载失败，请刷新重试。</p></section>';
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

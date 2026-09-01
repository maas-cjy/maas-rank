/* =========================================================
 * MaaS Rank 站点配置（域名适配层）
 * ---------------------------------------------------------
 * 绑定自定义域名后，只需把 DOMAIN 改成你的域名，例如：
 *   var DOMAIN = 'https://www.yourdomain.com';
 * 所有页面的 canonical / Open Graph / JSON-LD 地址会自动切换，
 * 其余文件一行都不用改。留空时自动使用当前访问域名，
 * 因此 GitHub Pages 地址与自定义域名可同时正常工作。
 *
 * 注意：sitemap.xml / robots.txt 由 scripts/gen_sitemap.py 生成，
 *       切换域名时需同步修改该脚本顶部的 SITE_URL 并重新运行。
 * ========================================================= */
(function () {
  var DOMAIN = '';

  var OLD_BASE = 'https://maas-cjy.github.io/maas-rank/';

  function detectBase() {
    var loc = window.location;
    var dir = loc.pathname.replace(/[^/]*$/, '');
    return loc.origin + dir;
  }

  var BASE = (DOMAIN || detectBase()).replace(/\/?$/, '/');

  function rewriteUrl(el, attr) {
    var v = el.getAttribute(attr);
    if (!v) return;
    if (v.indexOf(OLD_BASE) === 0) el.setAttribute(attr, BASE + v.slice(OLD_BASE.length));
    else if (v.indexOf('/') === 0) el.setAttribute(attr, BASE + v.slice(1));
  }

  function rewrite() {
    /* canonical 与 og:url */
    Array.prototype.forEach.call(
      document.querySelectorAll('link[rel="canonical"], meta[property="og:url"]'),
      function (el) { rewriteUrl(el, el.tagName === 'LINK' ? 'href' : 'content'); }
    );
    /* 社交分享图 */
    Array.prototype.forEach.call(
      document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]'),
      function (el) {
        var v = el.getAttribute('content');
        if (v && v.indexOf(OLD_BASE) === 0) el.setAttribute('content', BASE + v.slice(OLD_BASE.length));
      }
    );
    /* JSON-LD 结构化数据中的地址 */
    Array.prototype.forEach.call(
      document.querySelectorAll('script[type="application/ld+json"]'),
      function (el) {
        try {
          JSON.parse(el.textContent); /* 先校验是合法 JSON */
          el.textContent = el.textContent.split(OLD_BASE).join(BASE);
        } catch (e) { /* 非法 JSON 忽略 */ }
      }
    );
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', rewrite);
  else rewrite();

  window.MR_SITE = { base: BASE, domain: DOMAIN };
})();

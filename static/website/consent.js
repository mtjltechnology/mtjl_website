/* Consentimento de cookies de medição/publicidade (Meta Pixel e Google Ads).
   Padrão é negado: _tracking.html sobe fbq e gtag já revogados. Aqui só se lê a
   escolha, se aplica e se mostra o banner enquanto não houver escolha. */
(function () {
  var K = 'mtjl_consent';
  var L = (document.documentElement.lang || 'pt').slice(0, 2);
  var T = {
    pt: { t: 'Usamos cookies de medição e publicidade (Meta e Google) só se você aceitar. O site funciona igual se você recusar.', y: 'Aceitar', n: 'Recusar', p: 'Política de Privacidade', h: '/politica-de-privacidade' },
    en: { t: 'We use measurement and advertising cookies (Meta and Google) only if you accept. The site works the same if you decline.', y: 'Accept', n: 'Decline', p: 'Privacy Policy', h: '/en/privacy-policy' },
    es: { t: 'Usamos cookies de medición y publicidad (Meta y Google) solo si aceptas. El sitio funciona igual si las rechazas.', y: 'Aceptar', n: 'Rechazar', p: 'Política de Privacidad', h: '/es/politica-de-privacidad' }
  }[L] || null;
  T = T || { t: '', y: 'OK', n: 'No', p: '', h: '/politica-de-privacidade' };
  // Domínio do LarClínica não serve as páginas de política: link absoluto.
  if (location.hostname.indexOf('larclinicahealth.com') !== -1) T.h = 'https://mtjltechnology.com' + T.h;

  function get() { try { return localStorage.getItem(K); } catch (e) { return null; } }
  function set(v) { try { localStorage.setItem(K, v); } catch (e) {} }
  function apply(yes) {
    var s = yes ? 'granted' : 'denied';
    if (window.fbq) fbq('consent', yes ? 'grant' : 'revoke');
    if (window.gtag) gtag('consent', 'update', { ad_storage: s, analytics_storage: s, ad_user_data: s, ad_personalization: s });
  }
  function close() { var b = document.getElementById('mtjl-consent'); if (b) b.remove(); }
  function choose(yes) { set(yes ? 'yes' : 'no'); apply(yes); close(); }

  function show() {
    if (document.getElementById('mtjl-consent')) return;
    var b = document.createElement('div');
    b.id = 'mtjl-consent';
    b.setAttribute('role', 'dialog');
    b.setAttribute('aria-label', 'Cookies');
    b.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:99999;max-width:640px;margin:0 auto;background:#fff;color:#0b1222;border:1px solid rgba(11,18,34,.18);border-radius:12px;box-shadow:0 8px 30px rgba(11,18,34,.18);padding:16px;font:14px/1.5 system-ui,sans-serif';
    var btn = 'flex:1;padding:10px 14px;border-radius:8px;border:1px solid #0b1222;background:#fff;color:#0b1222;font:600 14px system-ui,sans-serif;cursor:pointer';
    b.innerHTML = '<p style="margin:0 0 12px">' + T.t + ' <a href="' + T.h + '" style="color:inherit;text-decoration:underline">' + T.p + '</a></p>' +
      '<div style="display:flex;gap:10px"><button type="button" data-v="no" style="' + btn + '">' + T.n + '</button><button type="button" data-v="yes" style="' + btn + '">' + T.y + '</button></div>';
    b.addEventListener('click', function (e) { var v = e.target.getAttribute && e.target.getAttribute('data-v'); if (v) choose(v === 'yes'); });
    document.body.appendChild(b);
  }

  // Link "Cookies" no footer e na política reabre o banner pra mudar a escolha.
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('[data-cookie-prefs]');
    if (a) { e.preventDefault(); show(); }
  });
  function init() {
    var v = get();
    if (v === 'yes') apply(true); else if (v === null) show();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

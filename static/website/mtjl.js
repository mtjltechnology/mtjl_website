/* Comportamentos compartilhados das páginas institucionais.
   Carregado com `defer` — roda depois do parse, sem bloquear a renderização. */
(function () {
  'use strict';

  /* A navbar começa transparente sobre o hero escuro e ganha fundo claro ao
     rolar. Feito em JS porque a troca precisa alternar a cor do texto e da
     logo junto, o que uma transição puramente declarativa não cobre.
     O listener usa IntersectionObserver num sentinela no topo em vez de
     escutar scroll: evita recalcular layout a cada quadro de rolagem. */
  // As páginas institucionais usam .navbar; a do RelatifyAI Beauty usa .bb-navbar.
  var navbar = document.querySelector('.navbar, .bb-navbar');
  if (navbar) {
    var sentinel = document.createElement('div');
    sentinel.setAttribute('aria-hidden', 'true');
    sentinel.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:80px;pointer-events:none';
    document.body.prepend(sentinel);

    new IntersectionObserver(function (entries) {
      navbar.classList.toggle('is-scrolled', !entries[0].isIntersecting);
    }, { threshold: 0 }).observe(sentinel);
  }

  /* Marca o item de navegação da página atual, para quem chega por link direto
     não precisar deduzir onde está. */
  var path = window.location.pathname.replace(/\/+$/, '') || '/';
  document.querySelectorAll('.navbar-nav a, .navbar-mobile-panel a').forEach(function (a) {
    var href = a.getAttribute('href') || '';
    if (href.charAt(0) !== '/' ) return;
    if (href.replace(/\/+$/, '') === path) a.setAttribute('aria-current', 'page');
  });
})();

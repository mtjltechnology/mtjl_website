"""
Testes da migração do LarClínica para o domínio próprio
(https://www.larclinicahealth.com).

Duas regras convivem na mesma aplicação, decididas pelo cabeçalho Host:
mtjltechnology.com continua entregando o site institucional e aposenta
/larclinica com 301; larclinicahealth.com entrega a página do LarClínica na
raiz e devolve qualquer outro caminho para o institucional, também com 301,
para o mesmo HTML não responder 200 nos dois domínios.
"""
import pytest

LC_HEADERS = {"host": "www.larclinicahealth.com"}
MTJL_HEADERS = {"host": "mtjltechnology.com"}


# ── Caminho aposentado no institucional ───────────────────────────────────────

def test_larclinica_antigo_redireciona_301_para_dominio_novo(client):
    r = client.get("/larclinica", headers=MTJL_HEADERS, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == "https://www.larclinicahealth.com/"


def test_larclinica_antigo_preserva_query_string_no_redirect(client):
    r = client.get("/larclinica?sent=1", headers=MTJL_HEADERS, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == "https://www.larclinicahealth.com/?sent=1"


# ── Raiz de cada domínio ──────────────────────────────────────────────────────

def test_raiz_do_dominio_novo_entrega_a_pagina_do_larclinica(client):
    r = client.get("/", headers=LC_HEADERS, follow_redirects=False)

    assert r.status_code == 200
    assert '<link rel="canonical" href="https://www.larclinicahealth.com/" />' in r.text
    # Nome completo do produto, confirmado pelo PO em 2026-08-24. O título antigo
    # ("LarClínica | Telessaúde para Operadoras de Saúde") descrevia o segmento;
    # este descreve o produto, e é o mesmo texto usado no card da home.
    assert "LarClínica · Plataforma de Gestão do Cuidado" in r.text


@pytest.mark.parametrize("path", ["/", "/larclinica", "/sitemap.xml"])
def test_dominio_sem_www_cai_301_no_host_canonico(client, path):
    """O canonical da página declara www: o domínio nu não pode servir uma
    segunda cópia da mesma página."""
    r = client.get(path, headers={"host": "larclinicahealth.com"}, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == f"https://www.larclinicahealth.com{path}"


def test_raiz_do_institucional_continua_entregando_a_home_da_mtjl(client):
    r = client.get("/", headers=MTJL_HEADERS, follow_redirects=False)

    assert r.status_code == 200
    assert "MTJL Technology" in r.text
    assert "https://www.larclinicahealth.com/" in r.text  # card do produto aponta pra fora


def test_card_do_larclinica_na_home_usa_o_nome_completo_do_produto(client):
    """O card e o título da página do produto têm que contar a mesma história.

    O card dizia "Telessaúde para operadoras de saúde", que é segmento, não
    produto. O nome completo passou a ser LarClínica · Plataforma de Gestão do
    Cuidado, e o descritor curto que cabe no card é a segunda metade dele.
    """
    r = client.get("/", headers=MTJL_HEADERS)

    assert "Plataforma de Gestão do Cuidado" in r.text
    assert "Telessaúde para operadoras de saúde" not in r.text


def test_pagina_do_larclinica_nao_declara_mais_url_antiga(client):
    r = client.get("/", headers=LC_HEADERS)

    assert "mtjltechnology.com/larclinica" not in r.text


# ── Conteúdo duplicado: outros caminhos no domínio do LarClínica ──────────────

@pytest.mark.parametrize("path", ["/pilotqa-ai", "/desenvolvimento-de-software", "/pedemarket"])
def test_paginas_do_institucional_no_dominio_novo_voltam_301(client, path):
    r = client.get(path, headers=LC_HEADERS, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == f"https://mtjltechnology.com{path}"


def test_301_do_dominio_novo_preserva_query_string(client):
    r = client.get("/pilotqa-ai?pq_sent=1", headers=LC_HEADERS, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == "https://mtjltechnology.com/pilotqa-ai?pq_sent=1"


def test_larclinica_no_proprio_dominio_vai_direto_pra_raiz(client):
    """Sem passar por mtjltechnology.com: um salto só, não dois."""
    r = client.get("/larclinica", headers=LC_HEADERS, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == "https://www.larclinicahealth.com/"


def test_estatico_do_dominio_novo_nao_e_redirecionado(client):
    r = client.get("/static/website/mtjl.css", headers=LC_HEADERS, follow_redirects=False)

    assert r.status_code == 200


# ── Formulário de contato ─────────────────────────────────────────────────────

def test_contato_do_larclinica_volta_pra_raiz_do_proprio_dominio(client, monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mocker.patch("resend.Emails.send")

    r = client.post(
        "/larclinica_contact",
        headers=LC_HEADERS,
        data={"name": "Ana", "email": "ana@operadora.com.br", "organization": "Operadora X", "message": "quero demo"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == "/?sent=1"


def test_contato_postado_de_outro_host_volta_pro_dominio_do_larclinica(client, monkeypatch, mocker):
    """Página antiga em cache posta de mtjltechnology.com: a confirmação tem que
    aparecer no domínio novo, não numa URL aposentada."""
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mocker.patch("resend.Emails.send")

    r = client.post(
        "/larclinica_contact",
        headers=MTJL_HEADERS,
        data={"name": "Ana", "email": "ana@operadora.com.br", "message": "quero demo"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == "https://www.larclinicahealth.com/?sent=1"


# ── SEO: sitemap e robots por domínio ─────────────────────────────────────────

def test_sitemap_do_institucional_nao_lista_mais_larclinica(client):
    r = client.get("/sitemap.xml", headers=MTJL_HEADERS)

    assert r.status_code == 200
    assert "mtjltechnology.com/larclinica" not in r.text
    assert "<loc>https://mtjltechnology.com/pedemarket</loc>" in r.text


def test_sitemap_do_dominio_novo_lista_so_as_proprias_paginas(client):
    r = client.get("/sitemap.xml", headers=LC_HEADERS)

    assert r.status_code == 200
    assert "<loc>https://www.larclinicahealth.com/</loc>" in r.text
    assert "<loc>https://www.larclinicahealth.com/en</loc>" in r.text
    assert "<loc>https://www.larclinicahealth.com/es</loc>" in r.text
    assert "mtjltechnology.com" not in r.text
    assert r.text.count("<loc>") == 3


def test_traducoes_do_larclinica_ficam_no_proprio_dominio(client):
    """/en e /es no domínio do LarClínica são a página dele, não a do institucional."""
    for path, marker in (("/en", 'lang="en"'), ("/es", 'lang="es"')):
        r = client.get(path, headers=LC_HEADERS, follow_redirects=False)

        assert r.status_code == 200
        assert marker in r.text
        assert "LarClínica" in r.text


def test_robots_aponta_pro_sitemap_do_proprio_dominio(client):
    lc = client.get("/robots.txt", headers=LC_HEADERS)
    mtjl = client.get("/robots.txt", headers=MTJL_HEADERS)

    assert "Sitemap: https://www.larclinicahealth.com/sitemap.xml" in lc.text
    assert "Sitemap: https://mtjltechnology.com/sitemap.xml" in mtjl.text


# ── Destinatário do lead ──────────────────────────────────────────────────────

def test_lead_do_larclinica_vai_pra_caixa_do_proprio_dominio(client, monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(
        "/larclinica_contact",
        headers=LC_HEADERS,
        data={"name": "Ana", "email": "ana@operadora.com.br", "organization": "Operadora X", "message": "quero demo"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    payload = mock_send.call_args[0][0]
    assert payload["to"] == ["contato@larclinicahealth.com"]
    assert "[LarClínica]" in payload["text"]


def test_contato_geral_continua_indo_pro_faleconosco_da_mtjl(client, monkeypatch, mocker):
    """A troca de caixa é só do LarClínica: o resto do site não muda."""
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")

    client.post(
        "/contact",
        headers=MTJL_HEADERS,
        data={"name": "Ana", "email": "ana@empresa.com.br", "message": "oi"},
        follow_redirects=False,
    )

    assert mock_send.call_args[0][0]["to"] == ["faleconosco@mtjltechnology.com"]


# ── Rastreamento e verificação de propriedade ─────────────────────────────────

def test_pagina_do_larclinica_carrega_pixel_e_google_tag(client):
    r = client.get("/", headers=LC_HEADERS)

    assert "fbq('init','1132342796628104')" in r.text
    assert "googletagmanager.com/gtag/js?id=AW-18180637831" in r.text


def test_evento_de_lead_dispara_so_depois_do_envio(client):
    sem_envio = client.get("/", headers=LC_HEADERS)
    com_envio = client.get("/?sent=1", headers=LC_HEADERS)

    assert "fbq('track', 'Lead'" not in sem_envio.text
    assert "fbq('track', 'Lead'" in com_envio.text
    assert "generate_lead" in com_envio.text


def test_meta_de_verificacao_do_search_console_sai_do_env(client, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "larclinica_google_site_verification", "token-de-teste")

    r = client.get("/", headers=LC_HEADERS)

    assert '<meta name="google-site-verification" content="token-de-teste" />' in r.text


def test_sem_token_configurado_nao_renderiza_meta_de_verificacao(client):
    r = client.get("/", headers=LC_HEADERS)

    assert "google-site-verification" not in r.text


def test_aba_do_browser_usa_o_icone_do_larclinica(client):
    """A página é o site do LarClínica, então o favicon é o símbolo da marca dele,
    não o da MTJL."""
    r = client.get("/", headers=LC_HEADERS)

    assert '<link rel="icon" href="/static/brand/larclinica-favicon.ico" sizes="any" />' in r.text
    assert "mtjl-favicon.png" not in r.text


def test_favicon_ico_na_raiz_do_dominio_novo_devolve_o_arquivo(client):
    """O Google busca /favicon.ico direto. No institucional a rota segue 204."""
    lc = client.get("/favicon.ico", headers=LC_HEADERS)
    mtjl = client.get("/favicon.ico", headers=MTJL_HEADERS)

    assert lc.status_code == 200
    assert lc.headers["content-type"] == "image/x-icon"
    assert mtjl.status_code == 204

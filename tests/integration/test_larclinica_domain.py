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
    assert "LarClínica | Telessaúde para Operadoras de Saúde" in r.text


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


def test_pagina_do_larclinica_nao_declara_mais_url_antiga(client):
    r = client.get("/", headers=LC_HEADERS)

    assert "mtjltechnology.com/larclinica" not in r.text


# ── Conteúdo duplicado: outros caminhos no domínio do LarClínica ──────────────

@pytest.mark.parametrize("path", ["/pilotqa-ai", "/en", "/desenvolvimento-de-software", "/pedemarket"])
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


def test_sitemap_do_dominio_novo_lista_so_a_propria_raiz(client):
    r = client.get("/sitemap.xml", headers=LC_HEADERS)

    assert r.status_code == 200
    assert "<loc>https://www.larclinicahealth.com/</loc>" in r.text
    assert "mtjltechnology.com" not in r.text
    assert r.text.count("<loc>") == 1


def test_robots_aponta_pro_sitemap_do_proprio_dominio(client):
    lc = client.get("/robots.txt", headers=LC_HEADERS)
    mtjl = client.get("/robots.txt", headers=MTJL_HEADERS)

    assert "Sitemap: https://www.larclinicahealth.com/sitemap.xml" in lc.text
    assert "Sitemap: https://mtjltechnology.com/sitemap.xml" in mtjl.text

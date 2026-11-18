import pytest


@pytest.mark.parametrize("path", ["/politica-de-privacidade", "/en/privacy-policy", "/es/politica-de-privacidad"])
def test_privacidade_existe_e_tem_canonical(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert f'rel="canonical" href="https://mtjltechnology.com{path}"' in r.text


@pytest.mark.parametrize("path,marca", [("/nada", "Página não encontrada"), ("/en/nada", "Page not found"), ("/es/nada", "Página no encontrada")])
def test_404_html_para_navegador(client, path, marca):
    r = client.get(path, headers={"accept": "text/html"})
    assert r.status_code == 404 and marca in r.text and "noindex" in r.text


def test_404_json_sem_accept_html(client):
    assert client.get("/nada").json() == {"detail": "Not Found"}


def test_lead_dispara_em_sent_e_tracking_nas_paginas_de_produto(client):
    assert "generate_lead" in client.get("/?sent=1").text
    assert "generate_lead" not in client.get("/").text
    assert "fbq('init'" in client.get("/pilotqa-ai").text


def test_tracking_nasce_negado_e_carrega_banner(client):
    for path, h in (("/", {}), ("/", {"host": "www.larclinicahealth.com"})):
        t = client.get(path, headers=h).text
        assert "'consent','default'" in t and "ad_storage:'denied'" in t
        assert "fbq('consent'" in t and "/static/website/consent.js" in t
        assert "facebook.com/tr?id" not in t  # pixel noscript enviaria sem consentimento

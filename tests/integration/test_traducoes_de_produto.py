"""As páginas de produto precisam existir e responder no idioma certo.

Cada produto tem uma rota por idioma e um seletor de idioma apontando para as
outras duas. Um template esquecido ou um hreflang que aponta pra si mesmo passa
batido em revisão, então fica coberto aqui.
"""
import pytest

LC_HEADERS = {"host": "www.larclinicahealth.com"}


PRODUTOS = [
    ("/pedemarket", "pt-BR", None),
    ("/en/pedemarket", "en", None),
    ("/es/pedemarket", "es", None),
    ("/pilotqa-ai", "pt-BR", None),
    ("/en/pilotqa-ai", "en", None),
    ("/es/pilotqa-ai", "es", None),
    ("/relatify-beauty", "pt-BR", None),
    ("/en/relatify-beauty", "en", None),
    ("/es/relatify-beauty", "es", None),
    ("/", "pt-BR", LC_HEADERS),
    ("/en", "en", LC_HEADERS),
    ("/es", "es", LC_HEADERS),
]


@pytest.mark.parametrize("path,lang,headers", PRODUTOS)
def test_pagina_de_produto_responde_no_idioma_da_rota(client, path, lang, headers):
    r = client.get(path, headers=headers or {}, follow_redirects=False)

    assert r.status_code == 200
    assert f'<html lang="{lang}"' in r.text


@pytest.mark.parametrize("path,lang,headers", PRODUTOS)
def test_pagina_de_produto_oferece_os_tres_idiomas(client, path, lang, headers):
    r = client.get(path, headers=headers or {})

    assert r.text.count("lang-flag") >= 3
    assert r.text.count("lang-flag--active") == 1


PLANOS_PILOTQA = ["/pilotqa-ai", "/en/pilotqa-ai", "/es/pilotqa-ai"]


@pytest.mark.parametrize("path", PLANOS_PILOTQA)
def test_pilotqa_cobra_em_real_nos_tres_idiomas(client, path):
    """O Asaas cobra em real. Preço em dólar na página seria propaganda enganosa."""
    r = client.get(path)

    assert "R$" in r.text
    assert "197" in r.text and "697" in r.text
    assert "/pilotqa_ai/subscribe" in r.text
    assert "$197" not in r.text.replace("R$&nbsp;197", "").replace("R$ 197", "")


@pytest.mark.parametrize("lang,destino", [("pt", "/pedemarket"), ("en", "/en/pedemarket"), ("es", "/es/pedemarket")])
def test_contato_do_pedemarket_volta_pra_pagina_do_idioma(client, mocker, lang, destino):
    mocker.patch("router.send_contact_email")

    r = client.post(
        "/pedemarket_contact",
        data={"name": "Ana", "email": "ana@mercadoreal.com.br", "message": "oi", "lang": lang},
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == f"{destino}?sent=1"


@pytest.mark.parametrize("lang,destino", [("pt", "/"), ("en", "/en"), ("es", "/es")])
def test_contato_do_larclinica_volta_pra_pagina_do_idioma(client, mocker, lang, destino):
    mocker.patch("router.send_contact_email")

    r = client.post(
        "/larclinica_contact",
        data={"name": "Ana", "email": "ana@operadorareal.com.br", "message": "oi", "lang": lang},
        headers=LC_HEADERS,
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == f"{destino}?sent=1"

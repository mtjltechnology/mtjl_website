"""
Integration tests for the SEO URL rename (underscore → hyphen) done on
router.py. Old GET paths must keep working as 301 redirects to the new
path (preserving query string), and the new paths must render their
templates directly — including /en/pilotqa-ai and /es/pilotqa-ai, that
previously had no route of their own (they used to 302 dead-end into /en
and /es).
"""
import pytest

LEGACY_REDIRECTS = [
    ("/pilotqa_ai", "/pilotqa-ai"),
    ("/en/pilotqa_ai", "/en/pilotqa-ai"),
    ("/es/pilotqa_ai", "/es/pilotqa-ai"),
    ("/relatify_beauty", "/relatify-beauty"),
    ("/en/relatify_beauty", "/en/relatify-beauty"),
    ("/es/relatify_beauty", "/es/relatify-beauty"),
    ("/qualityassurance", "/testes-de-software"),
    ("/en/qualityassurance", "/en/software-testing"),
    ("/es/qualityassurance", "/es/pruebas-de-software"),
]

NEW_GET_ROUTES = [new for _old, new in LEGACY_REDIRECTS]


@pytest.mark.parametrize("old_path,new_path", LEGACY_REDIRECTS)
def test_url_antiga_redireciona_301_para_url_nova(client, old_path, new_path):
    r = client.get(old_path, follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == new_path


@pytest.mark.parametrize("old_path,new_path", LEGACY_REDIRECTS)
def test_url_antiga_preserva_query_string_no_redirect(client, old_path, new_path):
    r = client.get(f"{old_path}?pq_sent=1", follow_redirects=False)

    assert r.status_code == 301
    assert r.headers["location"] == f"{new_path}?pq_sent=1"


@pytest.mark.parametrize("new_path", NEW_GET_ROUTES)
def test_url_nova_responde_200(client, new_path):
    r = client.get(new_path, follow_redirects=False)

    assert r.status_code == 200


def test_en_pilotqa_ai_renderiza_template_proprio_em_ingles(client):
    """Antes da renomeação, /en/pilotqa_ai era um 302 morto pra /en — agora
    /en/pilotqa-ai tem rota própria e renderiza pilotqa_en.html de verdade."""
    r = client.get("/en/pilotqa-ai", follow_redirects=False)

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_es_pilotqa_ai_renderiza_template_proprio_em_espanhol(client):
    """Mesma situação de /en/pilotqa_ai, mas pra pilotqa_es.html."""
    r = client.get("/es/pilotqa-ai", follow_redirects=False)

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]

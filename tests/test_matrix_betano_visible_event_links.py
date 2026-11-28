"""Regression tests for the read-only Betano visible event link fallback."""
from tools.matrix_selfhosted_browser_quote_collector import betano_visible_event_links


class FakePage:
    def __init__(self, rows):
        self.rows = rows

    def evaluate(self, script):
        assert "querySelectorAll('a[href]')" in script
        return self.rows


def test_visible_event_link_is_read_only_and_identity_bounded():
    rows=[
      {"href":"/cuotas-de-partido/fenerbahce-sk-liverpool-fc/91590438/",
       "label":"Fenerbahçe SK vs Liverpool FC"},
      {"href":"/cuotas-de-partido/fenerbahce-sk-other-team/91590439/",
       "label":"Fenerbahçe SK vs Other Team"},
      {"href":"https://malicious.example/cuotas-de-partido/fenerbahce-sk-liverpool-fc/91590438/",
       "label":"Fenerbahçe SK vs Liverpool FC"},
      {"href":"javascript:alert(1)","label":"Fenerbahçe SK vs Liverpool FC"},
    ]
    assert betano_visible_event_links(FakePage(rows),"Fenerbahçe SK","Liverpool FC")==[
      "https://www.betano.co/cuotas-de-partido/fenerbahce-sk-liverpool-fc/91590438/"
    ]


def test_visible_link_fails_closed_without_both_teams():
    rows=[{"href":"/cuotas-de-partido/a-b/123456/","label":"Liverpool FC"}]
    assert betano_visible_event_links(FakePage(rows),"Fenerbahçe SK","Liverpool FC")==[]


def test_visible_event_link_rejects_guessed_and_foreign_paths():
    rows=[
      {"href":"https://betano.co/other/fenerbahce-liverpool/91590438/","label":"Fenerbahçe SK vs Liverpool FC"},
      {"href":"http://www.betano.co/cuotas-de-partido/x-y/91590438/","label":"Fenerbahçe SK vs Liverpool FC"},
      {"href":"//other.example/cuotas-de-partido/fenerbahce-liverpool/91590438/","label":"Fenerbahçe SK vs Liverpool FC"},
    ]
    assert betano_visible_event_links(FakePage(rows),"Fenerbahçe SK","Liverpool FC")==[]


def test_visible_event_link_deduplicates_and_caps():
    rows=[{"href":f"/cuotas-de-partido/fenerbahce-liverpool/{91590438+i}/",
           "label":"Fenerbahçe SK vs Liverpool FC"} for i in range(8)]
    result=betano_visible_event_links(FakePage(rows),"Fenerbahçe SK","Liverpool FC")
    assert len(result)==3
    assert len(set(result))==3

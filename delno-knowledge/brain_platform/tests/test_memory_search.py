from brain_platform.search.memory import memory_query_variants


def test_compliance_alfa_expands():
    vs = [v.lower() for v in memory_query_variants("какую компанию первым отправил на комплаенс в Альфу")]
    assert any("комплаенс" in v for v in vs)
    assert any("alfabank" in v or "mv_mmb" in v for v in vs)
    assert any("compliance" in v for v in vs)

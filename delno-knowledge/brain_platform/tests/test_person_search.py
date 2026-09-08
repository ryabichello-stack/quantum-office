from brain_platform.search.person import person_query_variants, transliterate_ru


def test_yulya_partsuf_variants_include_latin_and_full_name():
    vs = [v.lower() for v in person_query_variants("Юля Парцуф")]
    assert any("юлия" in v for v in vs)
    assert any("partsuf" in v for v in vs)
    assert any("yuliya" in v or "yulia" in v for v in vs)
    assert any(v == "парцуф" or "парцуф" in v for v in vs)
    # email-local style ypartsuf
    assert any("ypartsuf" in v or v.startswith("ypart") for v in vs)


def test_transliterate():
    assert "partsuf" in transliterate_ru("парцуф")

"""Onboarding slug helpers."""

from app.services.onboarding import slugify


def test_slugify_cyrillic_company():
    assert slugify("ООО Ромашка") == "company"


def test_slugify_latin():
    assert slugify("Acme Corp LLC") == "acme-corp-llc"

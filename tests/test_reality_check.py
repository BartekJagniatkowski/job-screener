from analyzer import SYSTEM_TEMPLATE


def test_system_template_has_reality_check_section():
    assert 'REALITY CHECK' in SYSTEM_TEMPLATE


def test_system_template_has_reality_check_json_field():
    assert '"reality_check"' in SYSTEM_TEMPLATE


def test_system_template_has_callouts_field():
    assert '"callouts"' in SYSTEM_TEMPLATE


def test_system_template_has_phrase_and_plain_fields():
    assert '"phrase"' in SYSTEM_TEMPLATE
    assert '"plain"' in SYSTEM_TEMPLATE

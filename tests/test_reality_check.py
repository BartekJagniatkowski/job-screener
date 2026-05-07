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


def test_reality_check_field_after_gut_feeling():
    pos_gut = SYSTEM_TEMPLATE.index('"gut_feeling"')
    pos_rc  = SYSTEM_TEMPLATE.index('"reality_check"')
    assert pos_gut < pos_rc


def test_reality_check_instruction_before_format():
    pos_rc_section = SYSTEM_TEMPLATE.index('REALITY CHECK')
    pos_format     = SYSTEM_TEMPLATE.index('FORMAT — ONLY this JSON')
    assert pos_rc_section < pos_format

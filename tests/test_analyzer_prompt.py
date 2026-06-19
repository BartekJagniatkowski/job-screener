import analyzer


def test_system_template_instructs_zero_list_short_circuit():
    assert "ON A ZERO LIST HIT" in analyzer.SYSTEM_TEMPLATE


def test_build_system_still_formats_with_new_section_present():
    user = {"cv": "Python developer", "zero_list": "Defense contractors", "yellow_list": "", "criteria": "Remote only"}
    result = analyzer.build_system(user)
    assert "ON A ZERO LIST HIT" in result
    assert "Python developer" in result
    assert "Defense contractors" in result

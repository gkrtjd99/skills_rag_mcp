from skill_rag.normalize import expand_for_retrieval, normalize_for_dense


def test_inserts_space_between_latin_and_hangul():
    assert normalize_for_dense("vercel에 배포") == "vercel 에 배포"


def test_inserts_space_between_hangul_and_latin():
    assert normalize_for_dense("배포vercel") == "배포 vercel"


def test_leaves_pure_english_untouched():
    assert normalize_for_dense("review code") == "review code"


def test_leaves_pure_hangul_untouched():
    assert normalize_for_dense("코드리뷰") == "코드리뷰"


def test_handles_digits_at_boundary():
    assert normalize_for_dense("3개") == "3 개"


def test_expands_high_value_korean_intent_terms():
    expanded = expand_for_retrieval("구현의 회귀 위험을 점검해줘")
    assert "implementation" in expanded
    assert "regression" in expanded
    assert "risk" in expanded
    assert "inspect" in expanded


def test_does_not_expand_english_query():
    assert expand_for_retrieval("review regressions") == "review regressions"

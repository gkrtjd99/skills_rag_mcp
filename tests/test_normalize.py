from skill_rag.normalize import normalize_for_dense


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

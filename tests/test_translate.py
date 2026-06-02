from skill_rag import translate


def test_detect_lang_korean():
    assert translate.detect_lang("벌집에 배포하는 스킬") == "ko"


def test_detect_lang_english():
    assert translate.detect_lang("Deploy to Vercel") == "en"


def test_detect_lang_mixed_dominant_korean():
    assert translate.detect_lang("배포 자동화 스킬 모음") == "ko"


def test_detect_lang_empty_is_english():
    assert translate.detect_lang("   ") == "en"


def test_translate_korean_uses_ko_en_model(monkeypatch):
    seen = {}

    def fake(text, name):
        seen["name"] = name
        return f"EN: {text}"

    monkeypatch.setattr(translate, "_run_model", fake)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    out = translate.translate("배포 스킬")
    assert seen["name"] == translate.MT_KO_EN
    assert out == "EN: 배포 스킬"


def test_translate_english_uses_en_ko_model(monkeypatch):
    seen = {}

    def fake(text, name):
        seen["name"] = name
        return f"KO: {text}"

    monkeypatch.setattr(translate, "_run_model", fake)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    out = translate.translate("Deploy app")
    assert seen["name"] == translate.MT_EN_KO
    assert out == "KO: Deploy app"


def test_translate_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", False)
    assert translate.translate("배포 스킬") == ""


def test_translate_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    assert translate.translate("   ") == ""


def test_translate_failure_returns_empty(monkeypatch):
    def boom(text, name):
        raise RuntimeError("model not cached")

    monkeypatch.setattr(translate, "_run_model", boom)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    assert translate.translate("Deploy app") == ""


def test_translate_symbols_only_returns_empty(monkeypatch):
    called = []

    def fake(text, name):
        called.append(name)
        return "should-not-be-used"

    monkeypatch.setattr(translate, "_run_model", fake)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    assert translate.translate("512 @#$") == ""
    assert called == []  # model never invoked

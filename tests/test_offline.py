import importlib
import os
import sys
import types

from skill_rag.offline import enforce_hf_offline


def test_enforce_hf_offline_sets_hub_and_transformers(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    enforce_hf_offline(True)

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_enforce_hf_offline_noop_when_downloads_allowed(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    enforce_hf_offline(False)

    assert "HF_HUB_OFFLINE" not in os.environ
    assert "TRANSFORMERS_OFFLINE" not in os.environ


def test_embed_load_enforces_offline_before_import(monkeypatch):
    monkeypatch.setenv("SKILL_RAG_LOCAL_FILES_ONLY", "1")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    from skill_rag import embed

    importlib.reload(embed)
    embed._load_model.cache_clear()
    seen = {}

    class FakeSentenceTransformer:
        max_seq_length = 999

        def __init__(self, name, local_files_only):
            seen["name"] = name
            seen["local_files_only"] = local_files_only
            seen["hf_offline"] = os.environ.get("HF_HUB_OFFLINE")
            seen["transformers_offline"] = os.environ.get("TRANSFORMERS_OFFLINE")

        def get_embedding_dimension(self):
            return 3

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    assert embed.model_dim("fake-model") == 3
    assert seen == {
        "name": "fake-model",
        "local_files_only": True,
        "hf_offline": "1",
        "transformers_offline": "1",
    }


def test_translate_load_enforces_offline_before_import(monkeypatch):
    monkeypatch.setenv("SKILL_RAG_LOCAL_FILES_ONLY", "1")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    from skill_rag import translate

    importlib.reload(translate)
    translate._load_model.cache_clear()
    seen = {}

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, name, local_files_only):
            seen["tok_name"] = name
            seen["tok_local_files_only"] = local_files_only
            seen["hf_offline"] = os.environ.get("HF_HUB_OFFLINE")
            seen["transformers_offline"] = os.environ.get("TRANSFORMERS_OFFLINE")
            return cls()

    class FakeModel:
        @classmethod
        def from_pretrained(cls, name, local_files_only):
            seen["model_name"] = name
            seen["model_local_files_only"] = local_files_only
            return cls()

    fake_module = types.SimpleNamespace(
        MarianMTModel=FakeModel,
        MarianTokenizer=FakeTokenizer,
    )
    monkeypatch.setitem(sys.modules, "transformers", fake_module)

    translate._load_model("fake-mt")
    assert seen == {
        "tok_name": "fake-mt",
        "tok_local_files_only": True,
        "hf_offline": "1",
        "transformers_offline": "1",
        "model_name": "fake-mt",
        "model_local_files_only": True,
    }

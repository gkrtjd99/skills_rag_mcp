import numpy as np

from skill_rag.embed import encode, encode_one, model_dim


def test_model_dim_is_positive():
    assert model_dim() > 0


def test_encode_one_returns_normalized_vector():
    v = encode_one("hello world")
    assert v.shape == (model_dim(),)
    assert abs(np.linalg.norm(v) - 1.0) < 1e-5


def test_encode_batch():
    v = encode(["a", "b", "c"])
    assert v.shape == (3, model_dim())


def test_encode_empty_input():
    v = encode([])
    assert v.shape == (0, model_dim())


def test_e5_uses_query_and_passage_prompts(monkeypatch):
    from skill_rag import embed

    seen = []

    class FakeModel:
        max_seq_length = 512

        def get_embedding_dimension(self):
            return 2

        def encode(self, texts, **kwargs):
            seen.append(texts)
            return np.ones((len(texts), 2), dtype=np.float32)

    monkeypatch.setattr(embed, "_load_model", lambda name: FakeModel())

    embed.encode(["document"], name="intfloat/multilingual-e5-base")
    embed.encode_one("question", name="intfloat/multilingual-e5-base")

    assert seen == [["passage: document"], ["query: question"]]


def test_non_e5_model_does_not_get_prompt_prefix(monkeypatch):
    from skill_rag import embed

    seen = []

    class FakeModel:
        max_seq_length = 512

        def get_embedding_dimension(self):
            return 2

        def encode(self, texts, **kwargs):
            seen.append(texts)
            return np.ones((len(texts), 2), dtype=np.float32)

    monkeypatch.setattr(embed, "_load_model", lambda name: FakeModel())
    embed.encode_one("question", name="BAAI/bge-m3")

    assert seen == [["question"]]

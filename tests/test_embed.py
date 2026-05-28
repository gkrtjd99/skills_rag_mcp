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

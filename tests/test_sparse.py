from skill_rag.sparse import BM25, tokenize


def test_tokenize_lowercases_and_splits():
    assert tokenize("Deploy to Vercel!") == ["deploy", "to", "vercel"]


def test_tokenize_two_char_hangul_word_is_itself():
    # A 2-char Hangul run's only bigram is the run itself.
    assert tokenize("배포 vercel") == ["배포", "vercel"]


def test_tokenize_hangul_run_becomes_char_bigrams():
    assert tokenize("코드리뷰") == ["코드", "드리", "리뷰"]


def test_tokenize_splits_hangul_glued_to_latin():
    # The latin token survives so it can match the corpus's `vercel`.
    assert tokenize("vercel에 배포") == ["vercel", "에", "배포"]


def test_bm25_korean_query_matches_korean_doc():
    docs = [
        tokenize("코드 리뷰: 버그와 누락된 테스트 검토"),
        tokenize("vercel deploy preview url"),
    ]
    bm25 = BM25(docs)
    # Glued query '코드리뷰' shares the '리뷰' bigram with doc 0.
    scores = bm25.scores(tokenize("코드리뷰 해줘"))
    assert scores[0] > 0.0
    assert scores[0] >= scores[1]


def test_bm25_ranks_matching_doc_first():
    docs = [
        tokenize("deploy a website to vercel preview url"),
        tokenize("review code for bugs and missing tests"),
        tokenize("write failing tests first then implement"),
    ]
    bm25 = BM25(docs)
    scores = bm25.scores(tokenize("vercel deploy"))
    assert len(scores) == 3
    assert scores[0] == max(scores)
    assert scores[0] > 0.0


def test_bm25_unknown_terms_score_zero():
    docs = [tokenize("alpha beta"), tokenize("gamma delta")]
    bm25 = BM25(docs)
    assert bm25.scores(tokenize("zzz nonexistent")) == [0.0, 0.0]


def test_bm25_empty_corpus():
    bm25 = BM25([])
    assert bm25.scores(tokenize("anything")) == []

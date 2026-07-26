from app.services.extractor import CandidateMemory, RuleBasedExtractor, format_candidate_text, parse_stored_text


def test_format_parse_round_trip_positive():
    candidate = CandidateMemory(predicate="preference", value="Python", raw_text="I like Python", polarity=1)
    predicate, value, polarity = parse_stored_text(format_candidate_text(candidate))
    assert (predicate, value, polarity) == ("preference", "Python", 1)


def test_format_parse_round_trip_negative():
    candidate = CandidateMemory(predicate="preference", value="Python", raw_text="I hate Python", polarity=-1)
    predicate, value, polarity = parse_stored_text(format_candidate_text(candidate))
    assert (predicate, value, polarity) == ("preference", "Python", -1)


def test_extractor_flags_negative_polarity_for_dislike_words():
    [candidate] = RuleBasedExtractor().extract("I hate Python")
    assert candidate.predicate == "preference"
    assert candidate.polarity == -1
    assert candidate.value == "Python"


def test_extractor_flags_positive_polarity_for_like_words():
    [candidate] = RuleBasedExtractor().extract("I like Python")
    assert candidate.predicate == "preference"
    assert candidate.polarity == 1
    assert candidate.value == "Python"

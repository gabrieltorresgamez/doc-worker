"""Tests for plus-address tag parsing."""

from doc_worker.alias import extract_person_key, parse_tag


def test_parse_tag_person_only():
	params = parse_tag("alice")
	assert params.person == "alice"
	assert params.mode is None
	assert params.language is None


def test_parse_tag_mode_and_language():
	params = parse_tag("alice.translate.de")
	assert params.person == "alice"
	assert params.mode == "translate"
	assert params.language == "de"


def test_parse_tag_aliased_mode_tokens():
	assert parse_tag("bob.s").mode == "summary"
	assert parse_tag("bob.t").mode == "translate"
	assert parse_tag("bob.summarize").mode == "summary"


def test_parse_tag_dash_separator():
	params = parse_tag("alice-summary-fr")
	assert params.person == "alice"
	assert params.mode == "summary"
	assert params.language == "fr"


def test_parse_tag_unknown_tokens_ignored():
	params = parse_tag("alice.bogus.xx.translate")
	assert params.person == "alice"
	assert params.mode == "translate"
	# 'xx' is a valid two-letter shape, so it is accepted as a language code
	assert params.language == "xx"


def test_parse_tag_empty_defaults_to_unknown():
	assert parse_tag("").person == "unknown"


def test_extract_person_key_with_display_name_and_plus():
	params = extract_person_key("Scanner <pipeline+alice.de@scan.example.com>")
	assert params.person == "alice"
	assert params.language == "de"


def test_extract_person_key_no_plus():
	params = extract_person_key("pipeline@scan.example.com")
	assert params.person == "pipeline"


def test_extract_person_key_is_case_insensitive():
	params = extract_person_key("PIPELINE+Alice.Translate@Example.COM")
	assert params.person == "alice"
	assert params.mode == "translate"

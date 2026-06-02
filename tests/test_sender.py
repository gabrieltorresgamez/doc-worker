"""Tests for the sender allowlist check."""

from doc_worker.senders import sender_allowed


def test_empty_allowlist_accepts_everyone():
	assert sender_allowed("anyone@anywhere.com", ())


def test_exact_address_match():
	allowed = ("scanner@corp.com",)
	assert sender_allowed("scanner@corp.com", allowed)
	assert not sender_allowed("intruder@corp.com", allowed)


def test_domain_match():
	allowed = ("corp.com",)
	assert sender_allowed("anyone@corp.com", allowed)
	assert not sender_allowed("anyone@evil.com", allowed)


def test_domain_match_with_at_prefix():
	assert sender_allowed("anyone@corp.com", ("@corp.com",))


def test_match_is_case_insensitive():
	assert sender_allowed("Scanner@Corp.COM", ("scanner@corp.com",))


def test_missing_sender_is_rejected_when_allowlist_set():
	assert not sender_allowed("", ("corp.com",))
	assert not sender_allowed(None, ("corp.com",))


def test_lookalike_domain_not_matched():
	assert not sender_allowed("attacker@notcorp.com", ("corp.com",))

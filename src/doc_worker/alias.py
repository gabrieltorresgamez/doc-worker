"""Extract the person key and optional job parameters from a scanner destination address."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MODE_TOKENS: dict[str, str] = {
	"translate": "translate",
	"t": "translate",
	"summary": "summary",
	"summarize": "summary",
	"s": "summary",
}

_ISO_639_1 = re.compile(r"^[a-z]{2}$")
_TOKEN_SPLIT = re.compile(r"[.\-]")


@dataclass(frozen=True)
class AliasParams:
	"""Parameters decoded from the '+tag' of a plus-addressed destination."""

	person: str
	mode: str | None
	language: str | None


def parse_tag(tag: str) -> AliasParams:
	"""Decode a plus-address tag into person, mode, and language.

	Tokens are split on '.' or '-'. The first token is the person key.
	Remaining tokens are classified: recognised mode keywords set the mode;
	two-letter ISO 639-1 codes set the language. Unknown tokens are ignored.
	All three fields are optional in the address — omitted values fall back to
	the recipient config and then global defaults at call time.

	Args:
		tag: The '+tag' portion of the destination address local-part.

	Returns:
		AliasParams with person key and optional mode and language overrides.
	"""
	tokens = _TOKEN_SPLIT.split(tag.lower())
	person = tokens[0] if tokens and tokens[0] else "unknown"
	mode: str | None = None
	language: str | None = None

	for token in tokens[1:]:
		if token in _MODE_TOKENS:
			mode = _MODE_TOKENS[token]
		elif _ISO_639_1.match(token):
			language = token

	return AliasParams(person=person, mode=mode, language=language)


def extract_person_key(address: str) -> AliasParams:
	"""Parse a raw destination address into job parameters.

	Extracts the '+tag' from a plus-addressed local-part and delegates to
	parse_tag. Falls back gracefully when no '+' is present.

	Args:
		address: Raw email address, possibly including a display name.

	Returns:
		AliasParams decoded from the tag, or a bare person key if no tag tokens.
	"""
	angle = re.search(r"<([^>]+)>", address)
	if angle:
		address = angle.group(1)
	address = address.strip()
	local = address.split("@", 1)[0].lower() if "@" in address else address.lower()
	tag = local.split("+", 1)[1] if "+" in local else local
	return parse_tag(tag)

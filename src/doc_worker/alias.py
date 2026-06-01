"""Extract the person key from a scanner destination address."""

from __future__ import annotations

import re


def extract_local_part(address: str) -> str:
	"""Extract the local part from a raw email address string.

	Handles addresses with or without display names and angle brackets,
	e.g. "Maria <maria@scan.example.com>" → "maria".

	Args:
		address: Raw email address, possibly including a display name.

	Returns:
		Lowercase local part (before '@'). Returns the full lowercased input
		if no '@' is found.
	"""
	angle = re.search(r"<([^>]+)>", address)
	if angle:
		address = angle.group(1)
	address = address.strip()
	if "@" in address:
		return address.split("@", 1)[0].lower()
	return address.lower()

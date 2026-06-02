"""Sender authorization for incoming pipeline messages."""

from __future__ import annotations


def sender_allowed(from_addr: str | None, allowed_senders: tuple[str, ...]) -> bool:
	"""Check whether a sender is permitted to trigger the pipeline.

	The pipeline mailbox accepts mail from anyone, so without an allowlist any
	sender can spend backend credits and have documents relayed to configured
	recipients. When ``allowed_senders`` is non-empty, only matching senders are
	allowed. An entry may be a full address (``boss@example.com``) or a bare
	domain (``example.com`` / ``@example.com``) matching any address there.

	Args:
		from_addr: The message's From address (email only, display name stripped).
		allowed_senders: Configured allowlist entries, lower-cased.

	Returns:
		True if the sender is allowed, or if no allowlist is configured.
	"""
	if not allowed_senders:
		return True

	sender = (from_addr or "").strip().lower()
	if not sender:
		return False

	domain = sender.rsplit("@", 1)[-1]
	return any(entry.lstrip("@") in {sender, domain} for entry in allowed_senders)

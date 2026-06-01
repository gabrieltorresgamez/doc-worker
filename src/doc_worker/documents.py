"""Attachment extraction from email messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from imap_tools import MailMessage

logger = logging.getLogger(__name__)

_ACCEPTED_PREFIXES = ("application/pdf", "image/")


@dataclass(frozen=True)
class Attachment:
	"""A decoded email attachment."""

	filename: str
	content_type: str
	payload: bytes


def extract_attachments(msg: MailMessage, max_mb: int) -> list[Attachment]:
	"""Extract PDF and image attachments from a parsed email message.

	Attachments with unsupported MIME types or exceeding max_mb are skipped
	and a warning is logged.

	Args:
		msg: Parsed IMAP message from imap-tools.
		max_mb: Maximum accepted attachment size in megabytes.

	Returns:
		List of accepted Attachment objects (may be empty).
	"""
	max_bytes = max_mb * 1024 * 1024
	result: list[Attachment] = []

	for att in msg.attachments:
		ct = (att.content_type or "").lower()
		if not any(ct.startswith(p) for p in _ACCEPTED_PREFIXES):
			logger.debug("Skipping %r: unsupported type %r", att.filename, ct)
			continue
		size = len(att.payload)
		if size > max_bytes:
			logger.warning(
				"Skipping %r: %.1f MB exceeds limit of %d MB",
				att.filename,
				size / 1024 / 1024,
				max_mb,
			)
			continue
		result.append(
			Attachment(
				filename=att.filename or "attachment",
				content_type=ct,
				payload=att.payload,
			)
		)

	return result

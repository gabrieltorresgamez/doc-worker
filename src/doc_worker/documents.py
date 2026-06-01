"""Attachment extraction and PDF-to-image conversion."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pypdfium2 as pdfium

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


def pdf_to_images(pdf_bytes: bytes, scale: float = 2.0) -> list[bytes]:
	"""Render each page of a PDF to a PNG image.

	Args:
		pdf_bytes: Raw PDF file bytes.
		scale: Render scale factor. Higher values improve quality at the cost
			of larger output (2.0 ≈ 144 dpi from a 72 dpi base).

	Returns:
		List of PNG image bytes, one entry per page in document order.
	"""
	doc = pdfium.PdfDocument(pdf_bytes)
	pages: list[bytes] = []

	for i, page in enumerate(doc):
		bitmap = page.render(scale=scale, rotation=0)
		pil_image = bitmap.to_pil()
		buf = io.BytesIO()
		pil_image.save(buf, format="PNG")
		png = buf.getvalue()
		pages.append(png)
		logger.debug("Rendered page %d: %d bytes", i + 1, len(png))

	return pages

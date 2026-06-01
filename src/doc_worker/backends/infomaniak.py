"""Infomaniak AI backend: vision LLM for single-call OCR + translate/summarize."""

from __future__ import annotations

import base64
import logging
import time
from typing import TYPE_CHECKING

from openai import OpenAI

from doc_worker.documents import pdf_to_images

from .base import build_system_prompt

if TYPE_CHECKING:
	from doc_worker.config import AppConfig

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.infomaniak.com/2/ai/{product_id}/openai/v1/"
_MAX_RETRIES = 2
_RETRY_BACKOFF = 2.0


class InfomaniakBackend:
	"""Vision-LLM backend via Infomaniak's OpenAI-compatible API.

	A single call OCRs the document and translates or summarizes it.
	PDFs are rendered to per-page PNG images before submission.
	"""

	def __init__(self, config: AppConfig) -> None:
		"""Initialise the Infomaniak backend.

		Args:
			config: Application configuration containing Infomaniak credentials.
		"""
		self._model = config.infomaniak_backend.model
		self._client = OpenAI(
			api_key=config.infomaniak_token,
			base_url=_BASE_URL.format(product_id=config.infomaniak_product_id),
		)

	def process(
		self,
		doc_bytes: bytes,
		mime_type: str,
		filename: str,
		mode: str,
		target_language: str,
	) -> str:
		"""OCR and transform a document using Infomaniak's vision model.

		Args:
			doc_bytes: Raw document bytes.
			mime_type: MIME type of the document.
			filename: Original filename, used for logging.
			mode: 'translate' or 'summary'.
			target_language: Target language name in English.

		Returns:
			OCR'd and transformed UTF-8 text.

		Raises:
			RuntimeError: If all retry attempts fail.
		"""
		image_parts = self._to_image_parts(doc_bytes, mime_type)
		system_prompt = build_system_prompt(mode, target_language)

		logger.info(
			"Infomaniak: %r mode=%s lang=%s pages=%d",
			filename, mode, target_language, len(image_parts),
		)

		last_error: Exception | None = None
		for attempt in range(_MAX_RETRIES):
			try:
				response = self._client.chat.completions.create(
					model=self._model,
					messages=[
						{"role": "system", "content": system_prompt},
						{"role": "user", "content": image_parts},  # type: ignore[arg-type]
					],
				)
				return response.choices[0].message.content or ""
			except Exception as exc:  # noqa: BLE001
				last_error = exc
				logger.warning(
					"Infomaniak attempt %d/%d failed: %s",
					attempt + 1, _MAX_RETRIES, exc,
				)
				if attempt < _MAX_RETRIES - 1:
					time.sleep(_RETRY_BACKOFF**attempt)

		raise RuntimeError(
			f"Infomaniak backend failed after {_MAX_RETRIES} attempts"
		) from last_error

	@staticmethod
	def _to_image_parts(doc_bytes: bytes, mime_type: str) -> list[dict]:
		"""Convert document bytes into OpenAI image content parts.

		Args:
			doc_bytes: Raw document bytes.
			mime_type: MIME type of the document.

		Returns:
			List of OpenAI content-part dicts with base64-encoded images.
		"""
		if mime_type == "application/pdf":
			return [
				{
					"type": "image_url",
					"image_url": {
						"url": f"data:image/png;base64,{base64.b64encode(img).decode()}"
					},
				}
				for img in pdf_to_images(doc_bytes)
			]
		b64 = base64.b64encode(doc_bytes).decode()
		return [{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}]

"""Mistral backend: dedicated OCR model followed by chat for translate/summarize."""

from __future__ import annotations

import base64
import logging
import time
from typing import TYPE_CHECKING

from mistralai.client import Mistral

from .base import build_system_prompt

if TYPE_CHECKING:
	from doc_worker.config import AppConfig

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_BACKOFF = 2.0


class MistralBackend:
	"""Two-step backend: mistral-ocr for extraction, chat model for transformation."""

	def __init__(self, config: AppConfig) -> None:
		"""Initialise the Mistral backend.

		Args:
			config: Application configuration containing the Mistral API key.
		"""
		self._ocr_model = config.mistral_backend.ocr_model
		self._chat_model = config.mistral_backend.chat_model
		self._client = Mistral(api_key=config.mistral_api_key)

	def process(
		self,
		doc_bytes: bytes,
		mime_type: str,
		filename: str,
		mode: str,
		target_language: str,
	) -> str:
		"""OCR then translate or summarize using Mistral's dedicated models.

		Args:
			doc_bytes: Raw document bytes. PDFs are accepted natively by mistral-ocr.
			mime_type: MIME type of the document.
			filename: Original filename, used for logging.
			mode: 'translate' or 'summary'.
			target_language: Target language name in English.

		Returns:
			OCR'd and transformed UTF-8 text.
		"""
		logger.info("Mistral OCR: %r", filename)
		ocr_text = self._ocr(doc_bytes, mime_type)

		logger.info(
			"Mistral chat: mode=%s lang=%s ocr_chars=%d",
			mode, target_language, len(ocr_text),
		)
		return self._chat(ocr_text, mode, target_language)

	def _ocr(self, doc_bytes: bytes, mime_type: str) -> str:
		"""Run mistral-ocr with retry on transient errors.

		Args:
			doc_bytes: Raw document bytes.
			mime_type: MIME type of the document.

		Returns:
			Concatenated markdown text from all OCR pages.

		Raises:
			RuntimeError: If all retry attempts fail.
		"""
		b64 = base64.b64encode(doc_bytes).decode()
		data_url = f"data:{mime_type};base64,{b64}"

		last_error: Exception | None = None
		for attempt in range(_MAX_RETRIES):
			try:
				response = self._client.ocr.process(
					model=self._ocr_model,
					document={"type": "document_url", "document_url": data_url},
				)
				return "\n\n".join(page.markdown for page in response.pages)
			except Exception as exc:  # noqa: BLE001
				last_error = exc
				logger.warning(
					"Mistral OCR attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES, exc
				)
				if attempt < _MAX_RETRIES - 1:
					time.sleep(_RETRY_BACKOFF**attempt)

		raise RuntimeError(
			f"Mistral OCR failed after {_MAX_RETRIES} attempts"
		) from last_error

	def _chat(self, ocr_text: str, mode: str, target_language: str) -> str:
		"""Transform OCR text via chat completion with retry.

		Args:
			ocr_text: Raw OCR output to transform.
			mode: 'translate' or 'summary'.
			target_language: Target language name in English.

		Returns:
			Translated or summarized UTF-8 text.

		Raises:
			RuntimeError: If all retry attempts fail.
		"""
		system_prompt = build_system_prompt(mode, target_language)

		last_error: Exception | None = None
		for attempt in range(_MAX_RETRIES):
			try:
				response = self._client.chat.complete(
					model=self._chat_model,
					messages=[
						{"role": "system", "content": system_prompt},
						{"role": "user", "content": ocr_text},
					],
				)
				return response.choices[0].message.content or ""
			except Exception as exc:  # noqa: BLE001
				last_error = exc
				logger.warning(
					"Mistral chat attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES, exc
				)
				if attempt < _MAX_RETRIES - 1:
					time.sleep(_RETRY_BACKOFF**attempt)

		raise RuntimeError(
			f"Mistral chat failed after {_MAX_RETRIES} attempts"
		) from last_error

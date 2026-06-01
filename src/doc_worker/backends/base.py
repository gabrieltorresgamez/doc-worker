"""DocBackend protocol and shared prompt builders."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

_TRANSLATE_SYSTEM = (
	"You are a document OCR and translation tool. Transcribe ALL text from the provided "
	"document, then translate it into clear, natural {language}. Output ONLY the {language} "
	"text in a readable layout (preserve paragraph breaks, lists, and headings). Do not add "
	"commentary, notes, or the original-language text."
)

_SUMMARY_SYSTEM = (
	"You are a document OCR and summarization tool. Transcribe the text from the provided "
	"document, then write a concise, faithful summary in {language}, capturing the key "
	"points, names, dates, amounts, and any required actions or deadlines. Output ONLY the "
	"{language} summary. No commentary."
)


@runtime_checkable
class DocBackend(Protocol):
	"""Protocol for document OCR + translate/summarize backends."""

	def process(
		self,
		doc_bytes: bytes,
		mime_type: str,
		filename: str,
		mode: str,
		target_language: str,
	) -> str:
		"""OCR and transform a document into the target language.

		Args:
			doc_bytes: Raw document bytes (PDF or image).
			mime_type: MIME type, e.g. 'application/pdf' or 'image/jpeg'.
			filename: Original filename, used for logging context.
			mode: Either 'translate' or 'summary'.
			target_language: Language name in English, e.g. 'Spanish'.

		Returns:
			Extracted and transformed UTF-8 text.

		Raises:
			RuntimeError: If the backend call fails after all retries.
		"""
		...


def build_system_prompt(mode: str, language: str) -> str:
	"""Build the system prompt for the given mode and target language.

	Args:
		mode: Either 'translate' or 'summary'.
		language: Target language name in English, e.g. 'Spanish'.

	Returns:
		Formatted system prompt string.
	"""
	template = _TRANSLATE_SYSTEM if mode == "translate" else _SUMMARY_SYSTEM
	return template.format(language=language)

"""Document worker: poll loop and per-message orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .alias import extract_person_key
from .backends import get_backend
from .config import load_config
from .documents import extract_attachments
from .mailbox import apply_post_action, ensure_folders, fetch_unseen, send_reply
from .senders import sender_allowed

if TYPE_CHECKING:
	from imap_tools import MailMessage

	from .backends.base import DocBackend
	from .config import AppConfig
	from .documents import Attachment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Job:
	"""Fully resolved job parameters for one message."""

	person: str
	mode: str
	lang_code: str
	language_name: str
	reply_to: str


def _resolve_job(msg: MailMessage, config: AppConfig) -> _Job:
	"""Derive job parameters from message headers and configuration.

	Args:
		msg: Incoming IMAP message.
		config: Application configuration.

	Returns:
		Fully resolved _Job with defaults applied.
	"""
	# Prefer the To: address; fall back to Delivered-To: header.
	to_addresses = msg.to
	if to_addresses:
		raw_to = to_addresses[0]
	else:
		delivered = msg.headers.get("delivered-to")
		raw_to = str(delivered[0]) if delivered else ""

	params = extract_person_key(raw_to)
	recipient = config.recipients.get(params.person)

	# Priority: alias tag → recipient config → global defaults
	mode = params.mode or (recipient.mode if recipient else None) or config.defaults.mode
	lang_code = params.language or (recipient.language if recipient else None) or config.defaults.language
	language_name = config.languages.get(lang_code, lang_code.capitalize())
	reply_to = recipient.address if recipient else config.fallback_reply_to

	return _Job(
		person=params.person,
		mode=mode,
		lang_code=lang_code,
		language_name=language_name,
		reply_to=reply_to,
	)


def _subject(mode: str, lang_code: str, filename: str) -> str:
	"""Build the reply subject line.

	Args:
		mode: 'translate' or 'summary'.
		lang_code: ISO 639-1 language code.
		filename: Original attachment filename.

	Returns:
		Formatted subject string.
	"""
	tag = lang_code.upper()
	if mode == "translate":
		return f"Traducción ({tag}): {filename}"
	return f"Resumen ({tag}): {filename}"


def _collect_attachments(
	attachments: list[Attachment],
	backend: DocBackend,
	job: _Job,
) -> tuple[str, list[tuple[bytes, str, str]]]:
	"""Process all attachments and collect results.

	Args:
		attachments: List of decoded attachments.
		backend: Document processing backend.
		job: Resolved job parameters.

	Returns:
		Tuple of (body_text, reply_attachments) where body_text combines all
		results and reply_attachments contains the originals for re-attaching.
	"""
	bodies: list[str] = []
	originals: list[tuple[bytes, str, str]] = []

	for att in attachments:
		text = backend.process(
			doc_bytes=att.payload,
			mime_type=att.content_type,
			filename=att.filename,
			mode=job.mode,
			target_language=job.language_name,
		)
		separator = f"--- {att.filename} ---" if len(attachments) > 1 else ""
		bodies.append(f"{separator}\n\n{text}".strip() if separator else text)
		originals.append((att.payload, att.content_type, att.filename))

	return "\n\n".join(bodies), originals


def _send_error(
	uid: str,
	filename: str,
	msg: MailMessage,
	reply_to: str,
	config: AppConfig,
) -> None:
	"""Send a generic error notification with the original attachment and apply on_failure.

	The underlying exception is intentionally not included in the user-facing
	message to avoid leaking internal details; it is recorded in the logs by the
	caller instead.

	Args:
		uid: IMAP UID of the source message.
		filename: Filename hint for the subject line.
		msg: Original IMAP message (used to re-attach the file).
		reply_to: Recipient address for the error notification.
		config: Application configuration.
	"""
	try:
		originals: list[tuple[bytes, str, str]] = [
			(att.payload, att.content_type, att.filename) for att in extract_attachments(msg, config.max_attachment_mb)
		]
		send_reply(
			reply_to=reply_to,
			subject=f"[Error] Could not process: {filename}",
			body=(
				"Your document could not be processed automatically.\n\n"
				"The original file is attached so you can try again or handle it manually."
			),
			attachments=originals,
			config=config,
		)
	except Exception:
		logger.exception("Failed to send error notification for uid=%s", uid)

	apply_post_action(uid, config.on_failure, config.imap.folder_failed, config)


def process_message(msg: MailMessage, config: AppConfig, backend: DocBackend) -> None:
	"""Process one incoming scan email end-to-end.

	Resolves the alias, extracts attachments, calls the backend, sends the
	reply with results, and applies the configured success post-action.
	On any error the original scan is emailed back with an error note and
	the failure post-action is applied instead.

	Args:
		msg: Incoming IMAP message.
		config: Application configuration.
		backend: Document processing backend.
	"""
	start = datetime.now(UTC)
	uid = msg.uid
	reply_to = config.fallback_reply_to
	filename = "(no attachment)"

	try:
		if not sender_allowed(msg.from_, config.allowed_senders):
			logger.warning("uid=%s: sender %r not in allowlist — skipping", uid, msg.from_)
			apply_post_action(uid, config.on_failure, config.imap.folder_failed, config)
			return

		job = _resolve_job(msg, config)
		reply_to = job.reply_to

		logger.info(
			"uid=%s person=%s mode=%s lang=%s -> %s",
			uid,
			job.person,
			job.mode,
			job.lang_code,
			job.reply_to,
		)

		attachments = extract_attachments(msg, config.max_attachment_mb)

		if not attachments:
			logger.warning("uid=%s: no accepted attachments", uid)
			send_reply(
				reply_to=job.reply_to,
				subject="[Error] No supported attachment found",
				body=(
					"Your scan could not be processed because no supported "
					"attachment (PDF or image) was found in the email."
				),
				attachments=[],
				config=config,
			)
			apply_post_action(uid, config.on_failure, config.imap.folder_failed, config)
			return

		if len(attachments) > config.max_attachments:
			logger.warning(
				"uid=%s: %d attachments exceeds limit of %d — processing first %d only",
				uid,
				len(attachments),
				config.max_attachments,
				config.max_attachments,
			)
			attachments = attachments[: config.max_attachments]

		filename = attachments[0].filename
		body, originals = _collect_attachments(attachments, backend, job)

		send_reply(
			reply_to=job.reply_to,
			subject=_subject(job.mode, job.lang_code, filename),
			body=body,
			attachments=originals,
			config=config,
		)
		apply_post_action(uid, config.on_success, config.imap.folder_processed, config)

		elapsed = (datetime.now(UTC) - start).total_seconds()
		logger.info(
			"OK uid=%s person=%s mode=%s lang=%s files=%d elapsed=%.1fs",
			uid,
			job.person,
			job.mode,
			job.lang_code,
			len(attachments),
			elapsed,
		)

	except Exception:
		elapsed = (datetime.now(UTC) - start).total_seconds()
		logger.exception("FAIL uid=%s file=%r elapsed=%.1fs", uid, filename, elapsed)
		_send_error(uid, filename, msg, reply_to, config)


def run() -> None:
	"""Run the document worker poll loop indefinitely."""
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s %(message)s",
	)
	logger.info("doc-worker starting")

	config = load_config()
	backend = get_backend(config)
	logger.info("Backend: %s | Poll interval: %ds", config.backend, config.poll_interval_seconds)

	if not config.allowed_senders:
		logger.warning(
			"No 'allowed_senders' configured — every sender can trigger processing. "
			"Set an allowlist in config.yml to restrict access.",
		)

	ensure_folders(config)

	while True:
		try:
			for msg in fetch_unseen(config):
				process_message(msg, config, backend)
		except Exception:
			logger.exception("Unhandled error in poll loop — will retry after sleep")

		time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
	run()

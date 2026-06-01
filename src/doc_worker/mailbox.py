"""IMAP message fetch / move / delete and SMTP reply sending."""

from __future__ import annotations

import email.encoders
import logging
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from imap_tools import AND, MailBox

if TYPE_CHECKING:
	from imap_tools import MailMessage

	from doc_worker.config import AppConfig

logger = logging.getLogger(__name__)


def ensure_folders(config: AppConfig) -> None:
	"""Create the processed and failed IMAP folders if they do not exist.

	Args:
		config: Application configuration.
	"""
	with MailBox(config.imap.host, config.imap.port).login(
		config.imap_user, config.imap_password
	) as mb:
		existing = {f.name for f in mb.folder.list()}
		for folder in (config.imap.folder_processed, config.imap.folder_failed):
			if folder not in existing:
				mb.folder.create(folder)
				logger.info("Created IMAP folder %r", folder)


def fetch_unseen(config: AppConfig) -> list[MailMessage]:
	"""Fetch all UNSEEN messages from the inbox without marking them seen.

	Messages remain UNSEEN so that a crash before post-action leaves them
	available for reprocessing on the next poll.

	Args:
		config: Application configuration.

	Returns:
		List of unread MailMessage objects (may be empty).
	"""
	with MailBox(config.imap.host, config.imap.port).login(
		config.imap_user, config.imap_password
	) as mb:
		mb.folder.set(config.imap.folder_inbox)
		messages = list(mb.fetch(AND(seen=False), mark_seen=False))
	logger.info("Fetched %d unseen message(s)", len(messages))
	return messages


def apply_post_action(uid: str, action: str, folder: str, config: AppConfig) -> None:
	"""Move or permanently delete a message by UID.

	Args:
		uid: IMAP UID of the source message.
		action: Either 'move' or 'delete'.
		folder: Destination folder name (only used when action is 'move').
		config: Application configuration.
	"""
	with MailBox(config.imap.host, config.imap.port).login(
		config.imap_user, config.imap_password
	) as mb:
		mb.folder.set(config.imap.folder_inbox)
		if action == "delete":
			mb.delete([uid])
			mb.expunge()
			logger.info("Deleted message uid=%s", uid)
		else:
			mb.move([uid], folder)
			logger.info("Moved message uid=%s → %r", uid, folder)


def send_reply(
	reply_to: str,
	subject: str,
	body: str,
	attachments: list[tuple[bytes, str, str]],
	config: AppConfig,
) -> None:
	"""Compose and send a reply email via SMTP with STARTTLS.

	Args:
		reply_to: Recipient email address.
		subject: Email subject line.
		body: Plain-text body (UTF-8).
		attachments: List of (payload_bytes, content_type, filename) tuples
			to attach to the message.
		config: Application configuration.
	"""
	msg = MIMEMultipart()
	msg["From"] = f"{config.smtp.from_name} <{config.smtp.from_address}>"
	msg["To"] = reply_to
	msg["Subject"] = subject
	msg.attach(MIMEText(body, "plain", "utf-8"))

	for payload, content_type, filename in attachments:
		main, sub = content_type.split("/", 1) if "/" in content_type else ("application", "octet-stream")
		part = MIMEBase(main, sub)
		part.set_payload(payload)
		email.encoders.encode_base64(part)
		part.add_header("Content-Disposition", "attachment", filename=filename)
		msg.attach(part)

	with smtplib.SMTP(config.smtp.host, config.smtp.port) as smtp:
		smtp.ehlo()
		smtp.starttls()
		smtp.login(config.smtp_user, config.smtp_password)
		smtp.sendmail(config.smtp.from_address, reply_to, msg.as_string())

	logger.info("Sent reply to %r subject=%r", reply_to, subject)

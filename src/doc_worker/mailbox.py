"""IMAP message fetch / move / delete and SMTP reply sending."""

from __future__ import annotations

import email.encoders
import logging
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import markdown as md
from imap_tools import AND, MailBox

if TYPE_CHECKING:
	from imap_tools import MailMessage

	from doc_worker.config import AppConfig

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; font-size: 15px; line-height: 1.6; color: #222; max-width: 800px; margin: 2em auto; padding: 0 1em; }}
  h1, h2, h3 {{ color: #111; margin-top: 1.4em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #f5f5f5; }}
  code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }}
  pre {{ background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 0; padding-left: 1em; color: #555; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 1.5em 0; }}
</style>
</head>
<body>
{content}
</body>
</html>"""


def _to_html(markdown_text: str) -> str:
	"""Convert markdown text to a complete, styled HTML document.

	Args:
		markdown_text: Markdown-formatted string (e.g. from Mistral).

	Returns:
		Full HTML document string.
	"""
	content = md.markdown(
		markdown_text,
		extensions=["tables", "fenced_code", "nl2br"],
	)
	return _HTML_TEMPLATE.format(content=content)


def ensure_folders(config: AppConfig) -> None:
	"""Create the processed and failed IMAP folders if they do not exist.

	Args:
		config: Application configuration.
	"""
	with MailBox(config.imap.host, config.imap.port).login(config.imap_user, config.imap_password) as mb:
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
	with MailBox(config.imap.host, config.imap.port).login(config.imap_user, config.imap_password) as mb:
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
	with MailBox(config.imap.host, config.imap.port).login(config.imap_user, config.imap_password) as mb:
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

	The body is sent as multipart/alternative with a plain-text fallback and
	an HTML part converted from the markdown body.

	Args:
		reply_to: Recipient email address.
		subject: Email subject line.
		body: Markdown-formatted body text (UTF-8).
		attachments: List of (payload_bytes, content_type, filename) tuples
			to attach to the message.
		config: Application configuration.
	"""
	outer = MIMEMultipart("mixed")
	outer["From"] = f"{config.smtp.from_name} <{config.smtp.from_address}>"
	outer["To"] = reply_to
	outer["Subject"] = subject

	alternative = MIMEMultipart("alternative")
	alternative.attach(MIMEText(body, "plain", "utf-8"))
	alternative.attach(MIMEText(_to_html(body), "html", "utf-8"))
	outer.attach(alternative)

	for payload, content_type, filename in attachments:
		main, sub = content_type.split("/", 1) if "/" in content_type else ("application", "octet-stream")
		part = MIMEBase(main, sub)
		part.set_payload(payload)
		email.encoders.encode_base64(part)
		part.add_header("Content-Disposition", "attachment", filename=filename)
		outer.attach(part)

	with smtplib.SMTP(config.smtp.host, config.smtp.port) as smtp:
		smtp.ehlo()
		smtp.starttls()
		smtp.login(config.smtp_user, config.smtp_password)
		smtp.sendmail(config.smtp.from_address, reply_to, outer.as_string())

	logger.info("Sent reply to %r subject=%r", reply_to, subject)

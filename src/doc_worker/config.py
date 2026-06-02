"""Configuration loading for doc-worker."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ImapConfig:
	"""IMAP connection settings."""

	host: str
	port: int
	folder_inbox: str
	folder_processed: str
	folder_failed: str


@dataclass(frozen=True)
class SmtpConfig:
	"""SMTP connection settings."""

	host: str
	port: int
	from_address: str
	from_name: str


@dataclass(frozen=True)
class Defaults:
	"""Default processing parameters applied when a recipient omits mode or language."""

	mode: str
	language: str


@dataclass(frozen=True)
class MistralBackendConfig:
	"""Model settings for the Mistral backend."""

	ocr_model: str = "mistral-ocr-2512"
	chat_model: str = "mistral-small-latest"


@dataclass(frozen=True)
class RecipientConfig:
	"""Per-recipient settings looked up by the '+tag' person key."""

	address: str
	mode: str | None = None
	language: str | None = None


@dataclass(frozen=True)
class AppConfig:
	"""Full application configuration assembled from config.yml and environment."""

	poll_interval_seconds: int
	imap: ImapConfig
	smtp: SmtpConfig
	backend: str
	mistral_backend: MistralBackendConfig
	defaults: Defaults
	languages: dict[str, str]
	recipients: dict[str, RecipientConfig]
	fallback_reply_to: str
	on_success: str
	on_failure: str
	max_attachment_mb: int
	max_attachments: int
	allowed_senders: tuple[str, ...]
	# Secrets — never in config.yml
	imap_user: str
	imap_password: str
	smtp_user: str
	smtp_password: str
	mistral_api_key: str


def _require_env(name: str) -> str:
	"""Return an environment variable or raise if absent.

	Args:
		name: Environment variable name.

	Returns:
		The non-empty variable value.

	Raises:
		RuntimeError: If the variable is unset or empty.
	"""
	value = os.environ.get(name)
	if not value:
		raise RuntimeError(f"Required environment variable {name!r} is not set")
	return value


def load_config(path: Path | None = None) -> AppConfig:
	"""Load configuration from a YAML file and the process environment.

	Args:
		path: Path to config.yml. Defaults to /app/config.yml.

	Returns:
		Populated AppConfig instance.

	Raises:
		FileNotFoundError: If the config file does not exist.
		RuntimeError: If a required environment variable is missing.
	"""
	config_path = path or Path("/app/config.yml")
	with config_path.open() as fh:
		raw: dict = yaml.safe_load(fh)

	backend = os.environ.get("BACKEND") or raw.get("backend", "mistral")

	return AppConfig(
		poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
		imap=ImapConfig(**raw["imap"]),
		smtp=SmtpConfig(**raw["smtp"]),
		backend=str(backend),
		mistral_backend=MistralBackendConfig(**raw.get("backends", {}).get("mistral", {})),
		defaults=Defaults(**raw["defaults"]),
		languages=dict(raw.get("languages", {})),
		recipients={key: RecipientConfig(**val) for key, val in raw.get("recipients", {}).items()},
		fallback_reply_to=str(raw["fallback_reply_to"]),
		on_success=str(raw.get("on_success", "move")),
		on_failure=str(raw.get("on_failure", "move")),
		max_attachment_mb=int(raw.get("max_attachment_mb", 25)),
		max_attachments=int(raw.get("max_attachments", 10)),
		allowed_senders=tuple(str(s).strip().lower() for s in raw.get("allowed_senders", []) if str(s).strip()),
		imap_user=_require_env("IMAP_USER"),
		imap_password=_require_env("IMAP_PASSWORD"),
		smtp_user=_require_env("SMTP_USER"),
		smtp_password=_require_env("SMTP_PASSWORD"),
		mistral_api_key=_require_env("MISTRAL_API_KEY"),
	)

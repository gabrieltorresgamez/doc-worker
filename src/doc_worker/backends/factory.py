"""Backend factory: select and instantiate the configured implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .mistral import MistralBackend

if TYPE_CHECKING:
	from doc_worker.backends.base import DocBackend
	from doc_worker.config import AppConfig


def get_backend(config: AppConfig) -> DocBackend:
	"""Instantiate the configured document processing backend.

	Args:
		config: Application configuration.

	Returns:
		A DocBackend instance ready to process documents.

	Raises:
		ValueError: If the configured backend name is not recognised.
	"""
	if config.backend.lower() == "mistral":
		return MistralBackend(config)
	raise ValueError(f"Unknown backend {config.backend!r}. Valid value: 'mistral'.")

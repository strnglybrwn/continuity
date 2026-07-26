from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.persistence.models import Heartbeat, HeartbeatAttachment

MAX_ATTACHMENTS_PER_HEARTBEAT: Final[int] = 5
MAX_ATTACHMENT_SIZE_BYTES: Final[int] = 250 * 1024 * 1024
_READ_CHUNK_BYTES: Final[int] = 1024 * 1024

_ALLOWED_CONTENT_TYPES: Final[set[str]] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/tiff",
    "image/bmp",
    "image/svg+xml",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
}

_ALLOWED_EXTENSIONS: Final[set[str]] = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".svg",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
}


class AttachmentValidationError(ValueError):
    """Raised when an attachment violates configured constraints."""


@dataclass(frozen=True, slots=True)
class AttachmentUploadPayload:
    filename: str
    content_type: str
    size_bytes: int
    sha256_hex: str
    content_bytes: bytes


@dataclass(frozen=True, slots=True)
class HeartbeatAttachmentSummary:
    id: UUID
    filename: str
    content_type: str
    size_bytes: int


def sanitize_uploads(uploads: list[UploadFile]) -> list[UploadFile]:
    """Drop empty form parts from multi-file inputs."""
    return [upload for upload in uploads if upload.filename and upload.filename.strip()]


def parse_uploads(uploads: list[UploadFile]) -> list[AttachmentUploadPayload]:
    """Parse uploaded files, validating size and type constraints."""
    payloads: list[AttachmentUploadPayload] = []

    for upload in uploads:
        filename = upload.filename.strip() if upload.filename else ""
        if not filename:
            continue

        content_type = (upload.content_type or "application/octet-stream").lower().strip()

        if not _is_allowed_type(filename, content_type):
            raise AttachmentValidationError(
                f"Unsupported attachment type for '{filename}'. "
                "Allowed types are PDF, Office documents, and images."
            )

        content_bytes = bytearray()
        content_hash = sha256()
        total_size = 0

        upload.file.seek(0)
        while True:
            chunk = upload.file.read(_READ_CHUNK_BYTES)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > MAX_ATTACHMENT_SIZE_BYTES:
                raise AttachmentValidationError(
                    f"Attachment '{filename}' exceeds the 250 MB size limit"
                )

            content_hash.update(chunk)
            content_bytes.extend(chunk)

        if total_size == 0:
            raise AttachmentValidationError(f"Attachment '{filename}' is empty")

        payloads.append(
            AttachmentUploadPayload(
                filename=filename,
                content_type=content_type,
                size_bytes=total_size,
                sha256_hex=content_hash.hexdigest(),
                content_bytes=bytes(content_bytes),
            )
        )

    return payloads


def validate_attachment_addition(
    existing_count: int,
    incoming_count: int,
) -> None:
    if existing_count + incoming_count > MAX_ATTACHMENTS_PER_HEARTBEAT:
        raise AttachmentValidationError(
            "Attachment limit exceeded. A heartbeat can have at most 5 attachments"
        )


def add_heartbeat_attachments(
    session: Session,
    heartbeat_id: UUID,
    payloads: list[AttachmentUploadPayload],
) -> list[HeartbeatAttachment]:
    if not payloads:
        return []

    heartbeat = session.get(Heartbeat, heartbeat_id)
    if heartbeat is None:
        raise AttachmentValidationError("Heartbeat not found")

    existing_count = len(heartbeat.attachments)
    validate_attachment_addition(existing_count, len(payloads))

    attachments: list[HeartbeatAttachment] = []

    for payload in payloads:
        attachment = HeartbeatAttachment(
            heartbeat_id=heartbeat.id,
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            content_sha256=payload.sha256_hex,
            content_bytes=payload.content_bytes,
        )
        session.add(attachment)
        attachments.append(attachment)

    session.commit()

    for attachment in attachments:
        session.refresh(attachment)

    return attachments


def delete_heartbeat_attachment(
    session: Session,
    heartbeat_id: UUID,
    attachment_id: UUID,
) -> bool:
    attachment = session.get(HeartbeatAttachment, attachment_id)

    if attachment is None:
        return False

    if attachment.heartbeat_id != heartbeat_id:
        return False

    session.delete(attachment)
    session.commit()
    return True


def list_heartbeat_attachment_summaries(
    heartbeat: Heartbeat,
) -> list[HeartbeatAttachmentSummary]:
    return [
        HeartbeatAttachmentSummary(
            id=attachment.id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
        )
        for attachment in heartbeat.attachments
    ]


def get_attachment_content(
    session: Session,
    attachment_id: UUID,
) -> HeartbeatAttachment | None:
    return session.get(HeartbeatAttachment, attachment_id)


def _is_allowed_type(filename: str, content_type: str) -> bool:
    if content_type in _ALLOWED_CONTENT_TYPES:
        return True

    extension = Path(filename).suffix.lower()
    return extension in _ALLOWED_EXTENSIONS

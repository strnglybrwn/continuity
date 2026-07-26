from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from starlette.datastructures import UploadFile

from app.services import heartbeat_attachment_service as attachment_service
from app.services.heartbeat_attachment_service import (
    AttachmentValidationError,
    add_heartbeat_attachments,
    delete_heartbeat_attachment,
    parse_uploads,
    sanitize_uploads,
    validate_attachment_addition,
)


def _upload(filename: str, content_type: str, content: bytes) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers={"content-type": content_type},
    )


def test_sanitize_uploads_drops_empty_parts() -> None:
    uploads = [
        _upload("", "application/pdf", b""),
        _upload("plan.pdf", "application/pdf", b"pdf"),
    ]

    result = sanitize_uploads(uploads)

    assert len(result) == 1
    assert result[0].filename == "plan.pdf"


def test_parse_uploads_accepts_pdf_and_extracts_metadata() -> None:
    uploads = [_upload("plan.pdf", "application/pdf", b"pdf-bytes")]

    parsed = parse_uploads(uploads)

    assert len(parsed) == 1
    assert parsed[0].filename == "plan.pdf"
    assert parsed[0].content_type == "application/pdf"
    assert parsed[0].size_bytes == 9
    assert parsed[0].content_bytes == b"pdf-bytes"
    assert len(parsed[0].sha256_hex) == 64


def test_parse_uploads_rejects_invalid_type() -> None:
    uploads = [_upload("script.sh", "text/x-shellscript", b"echo hi")]

    with pytest.raises(AttachmentValidationError, match="Unsupported attachment type"):
        parse_uploads(uploads)


def test_parse_uploads_rejects_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attachment_service, "MAX_ATTACHMENT_SIZE_BYTES", 10)
    uploads = [_upload("big.pdf", "application/pdf", b"12345678901")]

    with pytest.raises(AttachmentValidationError, match="exceeds the 250 MB size limit"):
        parse_uploads(uploads)


def test_validate_attachment_addition_rejects_more_than_five() -> None:
    with pytest.raises(AttachmentValidationError, match="at most 5 attachments"):
        validate_attachment_addition(3, 3)


def test_add_heartbeat_attachments_persists_rows() -> None:
    heartbeat_id = uuid4()
    heartbeat = MagicMock()
    heartbeat.id = heartbeat_id
    heartbeat.attachments = []

    session = MagicMock()
    session.get.return_value = heartbeat

    payloads = parse_uploads([_upload("plan.pdf", "application/pdf", b"pdf")])

    attachments = add_heartbeat_attachments(session, heartbeat_id, payloads)

    assert len(attachments) == 1
    session.add.assert_called_once()
    session.commit.assert_called_once()
    session.refresh.assert_called_once()


def test_delete_heartbeat_attachment_hard_deletes() -> None:
    heartbeat_id = uuid4()
    attachment_id = uuid4()

    attachment = MagicMock()
    attachment.heartbeat_id = heartbeat_id

    session = MagicMock()
    session.get.return_value = attachment

    deleted = delete_heartbeat_attachment(session, heartbeat_id, attachment_id)

    assert deleted is True
    session.delete.assert_called_once_with(attachment)
    session.commit.assert_called_once()

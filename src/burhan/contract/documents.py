"""DOCX -> text ingestion for the live run's Node A inputs (TC-16; AT-M16-7).

Node A consumes *text*, never files: this converts a study or instrument DOCX
into the plain text that crosses the adapter boundary (``screen_boundary_input``
admits only text). A missing, unreadable, or content-empty document halts typed
(``IntegrityHalt``) — never a silent empty string that would hand Node A an empty
prompt. The raw survey CSV is not a document and is never passed here; it stays
ordinary pipeline data (NFR-401), read only by the ingest/prep stages.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import docx
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from burhan.core.errors import IntegrityHalt, halt

if TYPE_CHECKING:
    from pathlib import Path


def _iter_block_text(document: DocxDocument) -> Iterator[str]:
    """Yield paragraph and table-cell text in true document order."""
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            yield block.text
        elif isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    yield cell.text


def document_to_text(path: Path) -> str:
    """Extract a DOCX's paragraph and table text in document order.

    Halts typed on a missing, unreadable, or content-empty document (AT-M16-7):
    the live extraction must never send Node A an empty prompt.
    """
    if not path.is_file():
        halt(IntegrityHalt("study document not found (FR-201)", report={"path": str(path)}))
    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001 — boundary translation to a typed halt
        halt(
            IntegrityHalt(
                "study document is not a readable DOCX (FR-201)",
                report={"path": str(path), "error": type(exc).__name__},
            )
        )
    text = "\n".join(part for part in _iter_block_text(document) if part.strip())
    if not text.strip():
        halt(
            IntegrityHalt(
                "study document yielded no text; never a silent empty prompt (FR-201)",
                report={"path": str(path)},
            )
        )
    return text

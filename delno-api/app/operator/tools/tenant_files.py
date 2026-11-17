"""Hermes file operations; tenant scope comes only from authenticated context."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import tenant_attachments as files
from app.services.audit import write_audit


class FileFoldersTool:
    name = "files.folders"
    description = "List the company's folders."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {}}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        return ToolResult(ok=True, data={"folders": files.list_folders(db, ctx)})


class FileFolderCreateTool:
    name = "files.folder_create"
    description = "Create a folder for this company."
    critical_write = True
    parameters_schema = {"type": "object", "properties": {"name": {"type": "string"}, "parent_id": {"type": "string"}}, "required": ["name"]}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        try:
            folder = files.create_folder(db, ctx, str(params.get("name") or ""), params.get("parent_id"))
        except ValueError as exc:
            return ToolResult(ok=False, data={"error": str(exc)})
        write_audit(db, ctx, action="tool.files.folder_create", resource=f"folder:{folder['id']}")
        return ToolResult(ok=True, data={"folder": folder})


class FileCreateTextTool:
    name = "files.create_text"
    description = "Save generated text, Markdown, CSV or HTML as a company file. For DOCX/PDF/XLSX use a dedicated generator when available."
    critical_write = True
    parameters_schema = {"type": "object", "properties": {"name": {"type": "string"}, "content": {"type": "string"}, "folder_id": {"type": "string"}}, "required": ["name", "content"]}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        try:
            item = files.create_text_file(db, ctx, str(params.get("name") or ""), str(params.get("content") or ""), params.get("folder_id"))
        except ValueError as exc:
            return ToolResult(ok=False, data={"error": str(exc)})
        write_audit(db, ctx, action="tool.files.create_text", resource=f"file:{item['id']}")
        return ToolResult(ok=True, data={"file": item})


class FileReadTextTool:
    name = "files.read_text"
    description = "Read a small text, Markdown, CSV, HTML or JSON company file by file_id."
    critical_write = False
    parameters_schema = {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        try:
            return ToolResult(ok=True, data=files.read_text_file(db, ctx, str(params.get("file_id") or "")))
        except (ValueError, UnicodeError) as exc:
            return ToolResult(ok=False, data={"error": str(exc)})


class FileMoveTool:
    name = "files.move"
    description = "Move a company file to a folder."
    critical_write = True
    parameters_schema = {"type": "object", "properties": {"file_id": {"type": "string"}, "folder_id": {"type": "string"}}, "required": ["file_id"]}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        try:
            item = files.move_file(db, ctx, str(params.get("file_id") or ""), params.get("folder_id"))
        except ValueError as exc:
            return ToolResult(ok=False, data={"error": str(exc)})
        write_audit(db, ctx, action="tool.files.move", resource=f"file:{item['id']}")
        return ToolResult(ok=True, data={"file": item})


class FileDeleteTool:
    name = "files.delete"
    description = "Permanently delete a company file after owner confirmation."
    critical_write = True
    parameters_schema = {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        file_id = str(params.get("file_id") or "")
        try:
            files.delete_file(db, ctx, file_id)
        except ValueError as exc:
            return ToolResult(ok=False, data={"error": str(exc)})
        write_audit(db, ctx, action="tool.files.delete", resource=f"file:{file_id}")
        return ToolResult(ok=True, data={"deleted": file_id})


class FileFolderDeleteTool:
    name = "files.folder_delete"
    description = "Delete an empty company folder after owner confirmation."
    critical_write = True
    parameters_schema = {"type": "object", "properties": {"folder_id": {"type": "string"}}, "required": ["folder_id"]}

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        folder_id = str(params.get("folder_id") or "")
        try:
            files.delete_folder(db, ctx, folder_id)
        except ValueError as exc:
            return ToolResult(ok=False, data={"error": str(exc)})
        write_audit(db, ctx, action="tool.files.folder_delete", resource=f"folder:{folder_id}")
        return ToolResult(ok=True, data={"deleted": folder_id})

"""Domain enums — standalone, no SQLAlchemy dependency.

These are the only parts of the model layer that the REST-based
application actually uses.  The SQLAlchemy ORM classes in sibling
modules are dead weight (the app talks to Supabase via PostgREST).
"""

from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    user = "user"


class UploadStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ReportStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SourceType(StrEnum):
    upload = "upload"
    reference = "reference"

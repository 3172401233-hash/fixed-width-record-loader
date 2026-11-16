"""定长记录接入库：多版布局、字节级切片、派生字段与坏记录隔离。"""

from .layout import FieldSpec, LayoutVersion, RecordLayout
from .errors import BadRecord, ParseError
from .loader import FileLoader, LoadResult, UploadRegistry

__all__ = [
    "FieldSpec",
    "LayoutVersion",
    "RecordLayout",
    "BadRecord",
    "ParseError",
    "FileLoader",
    "LoadResult",
    "UploadRegistry",
]

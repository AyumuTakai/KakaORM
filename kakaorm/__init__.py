__version__ = "0.4.9"

from kakaorm.archive import ArchiveModel
from kakaorm.columns.base import (
    AggFunc,
    Avg,
    Case,
    Count,
    DenseRank,
    Lag,
    Lead,
    Max,
    Min,
    Rank,
    RowNumber,
    Sum,
    When,
    WindowedAgg,
    WindowFunc,
)
from kakaorm.columns.types import (
    BoolColumn,
    DateColumn,
    DateTimeColumn,
    DecimalColumn,
    FloatColumn,
    ForeignKey,
    IntColumn,
    StrColumn,
    TimeColumn,
)
from kakaorm.engine import (
    AioMySQLEngine,
    AioSQLiteEngine,
    AsyncpgEngine,
    Engine,
    Psycopg3Engine,
    connect,
)
from kakaorm.i18n import SUPPORTED_LOCALES, translate_detail
from kakaorm.migration import Migrator, VersionedMigrator
from kakaorm.model import Model
from kakaorm.query import Subquery
from kakaorm.relationship import belongs_to, has_many, has_one
from kakaorm.soft_delete import SoftDeleteModel
from kakaorm.validators import (
    ValidationError,
    max_length,
    max_value,
    min_length,
    min_value,
    one_of,
    regex,
)

# CLI（オプション依存なので try/except）
try:
    from kakaorm.cli.cli import main as cli_main
except ImportError:
    cli_main = None  # type: ignore

# 用途ごとにグループ分けしているため、アルファベット順には並べない
__all__ = [  # noqa: RUF022
    # Engine
    "Engine",
    "AsyncpgEngine",
    "AioSQLiteEngine",
    "AioMySQLEngine",
    "Psycopg3Engine",
    "connect",
    # Model
    "Model",
    "SoftDeleteModel",
    "ArchiveModel",
    # Column types
    "IntColumn",
    "StrColumn",
    "FloatColumn",
    "BoolColumn",
    "DateTimeColumn",
    "ForeignKey",
    "DecimalColumn",
    "DateColumn",
    "TimeColumn",
    # Relationships
    "has_many",
    "has_one",
    "belongs_to",
    # Subquery
    "Subquery",
    # Aggregate functions
    "AggFunc",
    "Count",
    "Sum",
    "Avg",
    "Max",
    "Min",
    # CASE WHEN
    "Case",
    "When",
    # Window Functions
    "WindowFunc",
    "RowNumber",
    "Rank",
    "DenseRank",
    "Lag",
    "Lead",
    "WindowedAgg",
    # Migration
    "Migrator",
    "VersionedMigrator",
    # Validation
    "ValidationError",
    "min_length",
    "max_length",
    "min_value",
    "max_value",
    "regex",
    "one_of",
    # i18n
    "translate_detail",
    "SUPPORTED_LOCALES",
    # CLI (optional)
    "cli_main",
]

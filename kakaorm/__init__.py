__version__ = "0.4.1"

from kakaorm.engine import (
    Engine,
    AsyncpgEngine,
    AioSQLiteEngine,
    AioMySQLEngine,
    Psycopg3Engine,
    connect,
)
from kakaorm.model import Model
from kakaorm.soft_delete import SoftDeleteModel
from kakaorm.archive import ArchiveModel
from kakaorm.columns.types import (
    IntColumn,
    StrColumn,
    FloatColumn,
    BoolColumn,
    DateTimeColumn,
    ForeignKey,
    DecimalColumn,
    DateColumn,
    TimeColumn,
)
from kakaorm.columns.base import (
    AggFunc,
    Case,
    Count,
    Sum,
    Avg,
    Max,
    Min,
    When,
    WindowFunc,
    RowNumber,
    Rank,
    DenseRank,
    Lag,
    Lead,
    WindowedAgg,
)
from kakaorm.relationship import has_many, has_one, belongs_to
from kakaorm.query import Subquery
from kakaorm.migration import Migrator, VersionedMigrator
from kakaorm.validators import (
    ValidationError,
    min_length,
    max_length,
    min_value,
    max_value,
    regex,
    one_of,
)

# CLI（オプション依存なので try/except）
try:
    from kakaorm.cli.cli import main as cli_main
except ImportError:
    cli_main = None  # type: ignore

__all__ = [
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
    # CLI (optional)
    "cli_main",
]

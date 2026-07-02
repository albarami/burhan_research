"""Schema-bound artifact models, canonical serialization, seeds (TC-01).

Public surface per 08_BUILD_SPEC.md M01: ``load_yaml``/``load_json``,
``dump_canonical``, ``canonical.dumps``, ``seeds.derive``, and the six
governed model families.
"""

from burhan.core.artifacts.loader import (
    MODEL_FOR_SCHEMA,
    SCHEMA_FOR_MODEL,
    dump_canonical,
    load_json,
    load_yaml,
    validate_and_build,
)
from burhan.core.artifacts.models import (
    ArtifactModel,
    DecisionEntry,
    ProvenanceEntry,
    ReferenceComparisonReport,
    ResultsStoreEntry,
    RunManifest,
    StudyConfig,
)
from burhan.core.artifacts.schemas import (
    GOVERNED_SCHEMA_FILES,
    check_instance,
    load_schema,
    schemas_dir,
)

__all__ = [
    "GOVERNED_SCHEMA_FILES",
    "MODEL_FOR_SCHEMA",
    "SCHEMA_FOR_MODEL",
    "ArtifactModel",
    "DecisionEntry",
    "ProvenanceEntry",
    "ReferenceComparisonReport",
    "ResultsStoreEntry",
    "RunManifest",
    "StudyConfig",
    "check_instance",
    "dump_canonical",
    "load_json",
    "load_schema",
    "load_yaml",
    "schemas_dir",
    "validate_and_build",
]

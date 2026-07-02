"""Schema-bound artifact models (standards §1; schemas/00_README.md).

One pydantic v2 model family per governed machine contract, mirroring the
schemas field-for-field: ``extra="forbid"`` for ``additionalProperties:
false``, per-schema enums (the stage enums differ per contract and are
modeled separately on purpose), verbatim patterns, and schema defaults.

The governed JSON Schema remains authoritative at runtime — these models are
the typed interface, and every load/dump runs both validators (see
``loader``). Timestamps are timezone-aware UTC at whole-second precision and
serialize to ``YYYY-MM-DDTHH:MM:SSZ`` (matches the worked example and the
``run_id`` grammar).
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    model_validator,
)

# --------------------------------------------------------------------------
# Shared building blocks
# --------------------------------------------------------------------------

SHA256_PATTERN = r"^[a-f0-9]{64}$"
RESULTS_ID_PATTERN = (
    r"^(power|prep|assumptions|measurement|structural|effects|robustness)"
    r"\.[a-z_]+(\.([A-Za-z0-9_]+(->[A-Za-z0-9_]+)?))*(\.[a-z_0-9]+)?$"
)

Sha256 = Annotated[str, Field(pattern=SHA256_PATTERN)]


def _validate_utc_seconds(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.microsecond != 0:
        raise ValueError("timestamp must be whole-second precision")
    return value


def _serialize_utc_seconds(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


UtcSeconds = Annotated[
    dt.datetime,
    AfterValidator(_validate_utc_seconds),
    PlainSerializer(_serialize_utc_seconds, return_type=str, when_used="json"),
]


class ArtifactModel(BaseModel):
    """Base for every artifact crossing a stage boundary (standards §1)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PipelineStage(StrEnum):
    """The 13 pipeline stages (shared enum, schemas/00_README.md)."""

    INGEST = "ingest"
    CONTRACT = "contract"
    GATE1 = "gate1"
    POWER = "power"
    PREP = "prep"
    ASSUMPTIONS = "assumptions"
    MEASUREMENT = "measurement"
    STRUCTURAL = "structural"
    EFFECTS = "effects"
    ROBUSTNESS = "robustness"
    NARRATE = "narrate"
    GATE2 = "gate2"
    PACKAGE = "package"


class RunState(StrEnum):
    """Run states (shared enum, schemas/00_README.md; architecture §4)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_TO_BOUNDARY = "COMPLETED_TO_BOUNDARY"
    HALTED_INTEGRITY = "HALTED_INTEGRITY"
    HALTED_VERIFICATION = "HALTED_VERIFICATION"
    HALTED_GATE = "HALTED_GATE"


# --------------------------------------------------------------------------
# results_store.schema.json
# --------------------------------------------------------------------------


class ResultsStage(StrEnum):
    """Statistical stages allowed to write statistics (AD-05)."""

    POWER = "power"
    PREP = "prep"
    ASSUMPTIONS = "assumptions"
    MEASUREMENT = "measurement"
    STRUCTURAL = "structural"
    EFFECTS = "effects"
    ROBUSTNESS = "robustness"


class ResultsEngine(StrEnum):
    """Engines permitted as statistic producers."""

    R_LAVAAN = "r_lavaan"
    PY_SEMOPY = "py_semopy"
    PY_PANDAS = "py_pandas"


class ResultsStoreEntry(ArtifactModel):
    """One statistic in the append-only results store (FR-1001)."""

    schema_version: Literal[1]
    id: str = Field(pattern=RESULTS_ID_PATTERN)
    value: bool | int | float | str
    se: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    ci_level: float | None = Field(default=None, gt=0, lt=1)
    p: float | None = Field(default=None, ge=0, le=1)
    df: float | None = Field(default=None, ge=0)
    n: int | None = Field(default=None, ge=1)
    unit: str | None = None
    stage: ResultsStage
    engine: ResultsEngine
    playbook_step: str
    params: dict[str, Any] | None = None
    created: UtcSeconds
    hash: Sha256


# --------------------------------------------------------------------------
# provenance_log.schema.json
# --------------------------------------------------------------------------


class ProvenanceActor(StrEnum):
    """Who acted (NFR-301)."""

    POLICY = "policy"
    INVARIANT = "invariant"
    RECONCILER = "reconciler"
    GATE = "gate"
    WORKER = "worker"
    ORCHESTRATOR = "orchestrator"
    OPERATOR = "operator"


class ProvenanceEventType(StrEnum):
    """What happened (NFR-301)."""

    RULE_FIRED = "rule_fired"
    ROW_DROP = "row_drop"
    CASE_RECOVERED = "case_recovered"
    ITEM_FLAG = "item_flag"
    ITEM_DELETION = "item_deletion"
    MODIFICATION_APPLIED = "modification_applied"
    ESTIMATOR_DETERMINED = "estimator_determined"
    INVARIANT_PASS = "invariant_pass"
    INVARIANT_FAIL = "invariant_fail"
    VERIFICATION_PASS = "verification_pass"
    VERIFICATION_FLAG = "verification_flag"
    VERIFICATION_HALT = "verification_halt"
    GATE_VERDICT = "gate_verdict"
    ADVISORY_ISSUED = "advisory_issued"
    HALT = "halt"
    ARTIFACT_WRITTEN = "artifact_written"
    STAGE_COMPLETE = "stage_complete"


class ArtifactRef(ArtifactModel):
    """Path + content hash of an artifact touched by an event."""

    path: str
    sha256: Sha256


class ProvenanceEntry(ArtifactModel):
    """One entry in the append-only sanad log (NFR-301)."""

    schema_version: Literal[1]
    seq: int = Field(ge=1)
    ts: UtcSeconds
    stage: PipelineStage
    actor: ProvenanceActor
    event_type: ProvenanceEventType
    rule_ref: str | None = None
    trigger: str
    effect: str
    artifact_refs: list[ArtifactRef] | None = None
    details: dict[str, Any] | None = None


# --------------------------------------------------------------------------
# decision_log.schema.json
# --------------------------------------------------------------------------


class DecisionStage(StrEnum):
    """Stages at which policy decisions occur (no gates; FR-1201)."""

    INGEST = "ingest"
    CONTRACT = "contract"
    POWER = "power"
    PREP = "prep"
    ASSUMPTIONS = "assumptions"
    MEASUREMENT = "measurement"
    STRUCTURAL = "structural"
    EFFECTS = "effects"
    ROBUSTNESS = "robustness"
    NARRATE = "narrate"
    PACKAGE = "package"


class DecisionPoint(StrEnum):
    """Registered operational decision points (FR-1201)."""

    INCLUSION_THRESHOLD = "inclusion_threshold"
    DUPLICATE_RULE = "duplicate_rule"
    ATTENTION_CHECK_RULE = "attention_check_rule"
    STRAIGHTLINER_RULE = "straightliner_rule"
    MISSING_MECHANISM = "missing_mechanism"
    MISSING_TREATMENT = "missing_treatment"
    OUTLIER_TREATMENT = "outlier_treatment"
    ESTIMATOR_DETERMINATION = "estimator_determination"
    BOOTSTRAP_PARAMETERS = "bootstrap_parameters"
    RESPECIFICATION = "respecification"
    ITEM_DELETION_RECOMMENDATION = "item_deletion_recommendation"
    ITEM_DELETION_EXECUTED = "item_deletion_executed"
    HIGHER_ORDER_CARRY = "higher_order_carry"
    FIT_BAND_EVALUATION = "fit_band_evaluation"
    REPORTING_FORMAT = "reporting_format"
    OTHER = "other"


class DecisionEntry(ArtifactModel):
    """One operational decision resolved by policy (FR-1201)."""

    schema_version: Literal[1]
    seq: int = Field(ge=1)
    ts: UtcSeconds
    stage: DecisionStage
    decision_point: DecisionPoint
    rule_id: str
    rule_version: str
    inputs: dict[str, Any]
    decision: str
    rationale: str
    alternatives_considered: list[str] | None = None
    flags: list[str] | None = None
    protected: bool = False


# --------------------------------------------------------------------------
# run_manifest.schema.json
# --------------------------------------------------------------------------


class StageState(StrEnum):
    """Terminal state of one stage record."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED_BOUNDARY = "SKIPPED_BOUNDARY"


class EngineInfo(ArtifactModel):
    """Engine build identity."""

    version: str
    git_commit: str = Field(pattern=r"^[a-f0-9]{7,40}$")
    git_dirty: bool | None = None


class VersionedSha(ArtifactModel):
    """Version string + content hash (prompt templates, AD-04)."""

    version: str
    sha256: Sha256


class PromptHashes(ArtifactModel):
    """Prompt template hashes per LLM node."""

    node_a: VersionedSha
    node_b: VersionedSha
    node_c: VersionedSha


class ManifestHashes(ArtifactModel):
    """Hashes of everything that governs a run (NFR-102)."""

    study_config: Sha256
    decision_policy: Sha256
    protected_registry: Sha256
    playbook: Sha256
    prompts: PromptHashes
    uv_lock: Sha256
    renv_lock: Sha256


class EnvironmentInfo(ArtifactModel):
    """Frozen environment facts (04_ENVIRONMENT §7)."""

    python: str
    r: str
    os: str
    blas_threads: Literal[1] | None = None
    max_workers: int | None = Field(default=None, ge=1)
    doctor_passed: Literal[True]
    doctor_report_sha256: Sha256 | None = None


class LlmNodeInfo(ArtifactModel):
    """Provider/model/lineage per LLM node (AD-04, FR-304)."""

    provider: str
    model: str
    lineage: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")
    temperature: float = Field(ge=0)
    prompt_version: str | None = None


class LlmNodes(ArtifactModel):
    """All three node configurations."""

    node_a: LlmNodeInfo
    node_b: LlmNodeInfo
    node_c: LlmNodeInfo


class StageRecord(ArtifactModel):
    """One stage transition record (NFR-502)."""

    stage: PipelineStage
    state: StageState
    started: UtcSeconds
    finished: UtcSeconds | None = None
    artifact_tree_sha256: Sha256 | None = None
    notes: str | None = None


class Seal(ArtifactModel):
    """Hash-tree root recorded at terminal state (NFR-102)."""

    hash_tree_root: Sha256
    sealed_at: UtcSeconds


class RunManifest(ArtifactModel):
    """Everything required to re-execute a run bit-identically (NFR-101)."""

    schema_version: Literal[1]
    run_id: str = Field(pattern=r"^[0-9]{8}T[0-9]{6}Z$")
    study_id: str
    started: UtcSeconds
    finished: UtcSeconds | None = None
    state: RunState
    master_seed: int = Field(ge=0)
    engine: EngineInfo
    hashes: ManifestHashes
    environment: EnvironmentInfo
    llm_nodes: LlmNodes
    stages: list[StageRecord]
    advisory: bool = False
    seal: Seal | None = None


# --------------------------------------------------------------------------
# study_config.schema.yaml
# --------------------------------------------------------------------------


class SourceDocument(ArtifactModel):
    """A source document behind the contract (FR-201)."""

    role: Literal["study_document", "data_dictionary", "instrument_export"]
    path: str
    sha256: Sha256


class StudyMeta(ArtifactModel):
    """Study identity block."""

    study_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    title: str
    created: UtcSeconds | None = None
    source_documents: list[SourceDocument] = Field(min_length=1)


class Methodology(ArtifactModel):
    """Declared methodology; estimator is deliberately absent (FR-602)."""

    declared: Literal["CB_SEM"]
    playbook_id: str
    playbook_version: str
    design: Literal["cross_sectional"]
    notes: str | None = None


class ScaleSpec(ArtifactModel):
    """Valid response range of one item."""

    type: Literal["likert", "numeric"]
    min: int
    max: int
    labels: list[str] | None = None


class InstrumentItem(ArtifactModel):
    """One designed instrument item (FR-201/202: as designed, never a subset)."""

    code: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    text: str
    construct_ref: str
    reverse_coded: bool
    source: str | None = None
    column_hint: str | None = None
    scale: ScaleSpec


class Instrument(ArtifactModel):
    """The designed item pool."""

    items: list[InstrumentItem] = Field(min_length=2)


class Construct(ArtifactModel):
    """A latent construct; first- or second-order (FR-201, §9.5)."""

    code: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    name: str
    level: Literal["first_order", "second_order"]
    measurement: Literal["reflective"]
    indicators: list[str] | None = Field(default=None, min_length=2)
    components: list[str] | None = Field(default=None, min_length=2)
    source: str | None = None

    @model_validator(mode="after")
    def _level_requirements(self) -> Construct:
        # Mirrors the schema's allOf/if/then exactly (presence only; the
        # V1-V7 cross-field resolution checks belong to M06's validators).
        if self.level == "first_order" and self.indicators is None:
            raise ValueError("first_order construct requires indicators")
        if self.level == "second_order" and self.components is None:
            raise ValueError("second_order construct requires components")
        return self


class HigherOrder(ArtifactModel):
    """Adopted higher-order approach and structural carry (FR-701/803)."""

    approach: Literal["repeated_indicator", "two_stage"]
    structural_carry: Literal["full_hierarchy", "latent_scores"]
    citation: str | None = None


class Moderator(ArtifactModel):
    """A moderation declaration on a structural path."""

    variable: str
    on_path: str = Field(pattern=r"^[A-Za-z0-9_]+->[A-Za-z0-9_]+$")


class Control(ArtifactModel):
    """A control variable and its targets."""

    variable: str
    on: list[str] = Field(min_length=1)


class StructuralModel(ArtifactModel):
    """Exogenous/endogenous structure with mediators/moderators/controls."""

    exogenous: list[str] = Field(min_length=1)
    endogenous: list[str] = Field(min_length=1)
    mediators: list[str] | None = None
    moderators: list[Moderator] | None = None
    controls: list[Control] | None = None


class Hypothesis(ArtifactModel):
    """One hypothesis (id grammar H<number><optional letter>)."""

    id: str = Field(pattern=r"^H[0-9]+[a-z]?$")
    effect: Literal["direct", "indirect", "total"]
    from_: str = Field(alias="from")
    to: str
    sign: Literal["positive", "negative"]
    via: list[str] | None = None
    statement: str | None = None


class CompletionColumns(ArtifactModel):
    """Progress/finished columns of the export."""

    progress_column: str | None = None
    finished_column: str | None = None


class AttentionCheck(ArtifactModel):
    """One attention-check column and its expected answer."""

    column: str
    expected: str


class Demographic(ArtifactModel):
    """One demographic field mapping."""

    code: str
    column_hint: str
    type: Literal["categorical", "ordinal", "numeric", "text"]


class DataBlock(ArtifactModel):
    """The raw export contract (zero-orphan accounting inputs, FR-507)."""

    file: str
    format: Literal["csv", "xlsx"]
    export_dialect: Literal["qualtrics", "generic"] | None = None
    header_rows: int | None = Field(default=None, ge=1, le=3)
    id_column: str | None = None
    consent_column: str | None = None
    completion: CompletionColumns | None = None
    attention_checks: list[AttentionCheck] | None = None
    demographics: list[Demographic] | None = None
    metadata_columns: list[str] | None = None
    ignored_item_columns: list[str] | None = None


class Crosswalk(ArtifactModel):
    """Column-to-item crosswalk mode (FR-103)."""

    mode: Literal["auto", "provided"] | None = None
    provided_map: dict[str, str] | None = None


class ProtectedOverrides(ArtifactModel):
    """Per-study protected-decision delegation (FR-705)."""

    item_deletion_preauthorized: bool = False


class StudyConfig(ArtifactModel):
    """The validated study contract (FR-201; instrument AS DESIGNED)."""

    schema_version: Literal[1]
    meta: StudyMeta
    methodology: Methodology
    instrument: Instrument
    constructs: list[Construct] = Field(min_length=1)
    higher_order: HigherOrder | None = None
    model: StructuralModel
    hypotheses: list[Hypothesis] = Field(min_length=1)
    data: DataBlock
    crosswalk: Crosswalk | None = None
    protected_overrides: ProtectedOverrides | None = None


# --------------------------------------------------------------------------
# reference_comparison.schema.json
# --------------------------------------------------------------------------


class ComparisonDomain(StrEnum):
    """What kind of quantity is being compared (FR-1503)."""

    N_CHAIN = "n_chain"
    CLEANING_DECISION = "cleaning_decision"
    MISSING_TREATMENT = "missing_treatment"
    ITEM_RETENTION = "item_retention"
    RELIABILITY = "reliability"
    CONVERGENT_VALIDITY = "convergent_validity"
    DISCRIMINANT_VALIDITY = "discriminant_validity"
    CMB = "cmb"
    FIT = "fit"
    RESPECIFICATION = "respecification"
    PATH = "path"
    EFFECT = "effect"
    HYPOTHESIS_VERDICT = "hypothesis_verdict"
    REPORTING_CONSISTENCY = "reporting_consistency"


class ComparisonStatus(StrEnum):
    """Per-comparison outcome."""

    MATCH = "match"
    DIVERGENT = "divergent"
    REFERENCE_MISSING = "reference_missing"
    BURHAN_ONLY = "burhan_only"


class DivergenceClassification(StrEnum):
    """Set only after investigation; unresolved until then (Concept §15)."""

    UNRESOLVED = "unresolved"
    MANUAL_WEAKNESS = "manual_weakness"
    ENGINE_OR_POLICY_CORRECTION = "engine_or_policy_correction"
    EQUIVALENT_DEFENSIBLE_CHOICE = "equivalent_defensible_choice"


class ReferenceDocument(ArtifactModel):
    """A reference-source document with its hash."""

    path: str
    sha256: Sha256


class ReferenceSource(ArtifactModel):
    """Where the manual reference values come from."""

    description: str
    documents: list[ReferenceDocument] = Field(min_length=1)
    caveats: str | None = None


class Comparison(ArtifactModel):
    """One reference-vs-Burhan comparison (no side presumed correct)."""

    comparison_id: str
    domain: ComparisonDomain
    metric: str
    reference_value: bool | int | float | str | None = None
    burhan_value: bool | int | float | str | None = None
    burhan_stat_id: str | None = None
    delta: float | None = None
    tolerance: float | None = None
    status: ComparisonStatus
    classification: DivergenceClassification = DivergenceClassification.UNRESOLVED
    investigation: str | None = None
    resolution: str | None = None


class ComparisonSummary(ArtifactModel):
    """Counts; unresolved must reach 0 before production use (Concept §15)."""

    total: int = Field(ge=1)
    matches: int = Field(ge=0)
    divergent: int = Field(ge=0)
    reference_missing: int | None = Field(default=None, ge=0)
    burhan_only: int | None = Field(default=None, ge=0)
    unresolved: int = Field(ge=0)


class Signoff(ArtifactModel):
    """Researcher sign-off on the comparison report."""

    researcher: str
    date: dt.date
    notes: str | None = None


class ReferenceComparisonReport(ArtifactModel):
    """The DBA validation-run comparison report (FR-1503)."""

    schema_version: Literal[1]
    study_id: str
    run_id: str
    reference_source: ReferenceSource
    comparisons: list[Comparison] = Field(min_length=1)
    summary: ComparisonSummary
    signoff: Signoff | None = None

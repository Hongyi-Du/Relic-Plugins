"""Conservative scope recommendations from matched, training-only evidence.

Recommendations carry no deployment authority. Statistical bounds describe the
declared diagnostic sampling model, not generalization from a live pilot.
"""
from dataclasses import asdict, dataclass
import json
import math


CELL_FIELDS = ("team", "task_family", "model", "environment_version")


def context_cell(context):
    if not isinstance(context, dict):
        return None
    team = context.get("team")
    if "team_ids" in context:
        teams = context["team_ids"]
        if not isinstance(teams, list) or len(teams) != 1 or not isinstance(teams[0], str):
            return None
        if team is not None and team != teams[0]:
            return None
        team = teams[0]
    values = (team,) + tuple(context.get(key) for key in CELL_FIELDS[1:])
    if not all(isinstance(value, str) and value for value in values):
        return None
    return values


@dataclass(frozen=True)
class Outcome:
    trial_id: str
    task_id: str
    initial_state_id: str
    seed: int
    split: str
    context: dict
    score: float
    cost: float = 0.0
    status: str = "completed"
    evaluator_version: str = "diagnostic-v1"
    patch_ref: dict | None = None


@dataclass(frozen=True)
class PairedEvidence:
    pair_id: str
    control: Outcome
    treatment: Outcome
    provenance: str = "paired_execution"

    def validate(self, *, split=None):
        if self.provenance != "paired_execution":
            raise ValueError("Observational evidence cannot be fitted as a paired trial.")
        left, right = self.control, self.treatment
        for key in ("task_id", "initial_state_id", "seed", "split", "context", "evaluator_version"):
            if getattr(left, key) != getattr(right, key):
                raise ValueError("Unmatched paired field: " + key)
        if not self.pair_id or left.trial_id == right.trial_id:
            raise ValueError("Distinct trial IDs and a pair ID are required.")
        if left.patch_ref is not None or not right.patch_ref:
            raise ValueError("A pair requires an unpatched control and an exact treatment reference.")
        ref = right.patch_ref
        if set(ref) != {"patch_id", "revision"} or not isinstance(ref["patch_id"], str) or type(ref["revision"]) is not int or ref["revision"] < 1:
            raise ValueError("An exact patch_id/revision reference is required.")
        for outcome in (left, right):
            if outcome.status != "completed":
                raise ValueError("Infrastructure failures are not business outcomes.")
            if split is not None and outcome.split != split:
                raise ValueError("Only the requested split may be fitted.")
            for value in (outcome.score, outcome.cost):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError("Scores and normalized costs must be finite in [0, 1].")
        if context_cell(left.context) is None:
            raise ValueError("Training context is incomplete.")
        return self

    @property
    def gain(self):
        return self.treatment.score - self.control.score

    @property
    def utility_gain(self):
        return self.gain - (self.treatment.cost - self.control.cost)

    def to_dict(self):
        return asdict(self)


class EvidenceLedger:
    """An isolated experiment ledger; never touches the production org store."""

    def __init__(self):
        self._pairs = {}
        self._tasks = set()

    @staticmethod
    def _detached(pair):
        data = json.loads(json.dumps(pair.to_dict(), allow_nan=False))
        return PairedEvidence(data["pair_id"], Outcome(**data["control"]), Outcome(**data["treatment"]), data["provenance"])

    def record_pair(self, pair):
        pair.validate()
        existing = self._pairs.get(pair.pair_id)
        if existing is not None:
            if existing != pair:
                raise ValueError("An evidence ID cannot be rebound.")
            return self._detached(existing)
        key = (pair.control.task_id, tuple(sorted(pair.treatment.patch_ref.items())))
        if key in self._tasks:
            raise ValueError("A repeated task cannot become an independent sample.")
        # JSON roundtrip freezes caller-owned dictionaries without pickle/code.
        stored = self._detached(pair)
        self._pairs[pair.pair_id] = stored
        self._tasks.add(key)
        return self._detached(stored)

    def snapshot(self):
        return [json.loads(json.dumps(pair.to_dict())) for pair in self._pairs.values()]


@dataclass(frozen=True)
class LearnerConfig:
    alpha: float = 0.05
    minimum_pairs: int = 3
    minimum_gain: float = 0.0
    maximum_decisions: int = 1

    def validate(self):
        if not 0 < self.alpha < 1 or self.minimum_pairs < 2 or self.maximum_decisions < 1 or not math.isfinite(self.minimum_gain) or self.minimum_gain < 0:
            raise ValueError("Invalid learner configuration.")


@dataclass(frozen=True)
class ScopeRecommendation:
    patch_ref: dict
    accepted_cells: tuple
    rejected_cells: tuple
    uncertain_cells: tuple
    statistics: tuple
    evidence_ids: tuple
    authority: str = "recommendation_only"

    def applies(self, context):
        return context_cell(context) in self.accepted_cells

    def scope_spec(self):
        def predicate(cell):
            return {"all": [{"field": "team_ids", "op": "eq", "value": [value]} if key == "team"
                             else {"field": key, "op": "eq", "value": value}
                             for key, value in zip(CELL_FIELDS, cell)]}
        return {"include": {"any": [predicate(cell) for cell in self.accepted_cells]} if self.accepted_cells else {"const": False},
                "exclude": {"any": [predicate(cell) for cell in self.rejected_cells]} if self.rejected_cells else {"const": False}}

    def to_dict(self):
        return asdict(self)


class ScopeLearner:
    def __init__(self, config=None):
        self.config = config or LearnerConfig()
        self.config.validate()

    def propose(self, patch_ref, evidence):
        grouped = {}
        ids = set()
        tasks = set()
        for pair in evidence:
            pair.validate(split="train")
            if pair.treatment.patch_ref != patch_ref:
                raise ValueError("Evidence belongs to another Patch revision.")
            if pair.pair_id in ids or pair.control.task_id in tasks:
                raise ValueError("Duplicate evidence or task instance.")
            ids.add(pair.pair_id)
            tasks.add(pair.control.task_id)
            grouped.setdefault(context_cell(pair.control.context), []).append(pair)
        accepted, rejected, uncertain, statistics = [], [], [], []
        cells = max(1, len(grouped))
        for cell, pairs in sorted(grouped.items()):
            n = len(pairs)
            mean = sum(pair.utility_gain for pair in pairs) / n
            # Paired utilities are in [-2, 2]; use the full range of four.
            radius = math.sqrt(8 * math.log(2 * cells * self.config.maximum_decisions / self.config.alpha) / n)
            lower, upper = max(-2.0, mean - radius), min(2.0, mean + radius)
            harm = any(pair.gain < 0 for pair in pairs)
            if harm:
                decision = "narrow"
                rejected.append(cell)
            elif n >= self.config.minimum_pairs and lower > self.config.minimum_gain:
                decision = "recommend"
                accepted.append(cell)
            else:
                decision = "uncertain"
                uncertain.append(cell)
            statistics.append({"cell": cell, "pairs": n, "mean_utility_gain": mean,
                               "lower_bound": lower, "upper_bound": upper,
                               "observed_harm": harm, "decision": decision})
        return ScopeRecommendation(dict(patch_ref), tuple(accepted), tuple(rejected),
                                   tuple(uncertain), tuple(statistics), tuple(sorted(ids)))

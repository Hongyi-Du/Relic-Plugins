"""Independent normal/emergency line-break quantities; no reference-driven aliases.

The legacy ``wrap`` combined two different provider properties. It remains raw
diagnostic evidence, but cannot prove either of these versioned quantities.
"""

BREAK_FIELDS = ("normal_break_strategy", "emergency_break_strategy")
NORMAL_BREAKS = {"none", "word", "break-all", "character", "keep-all"}
EMERGENCY_BREAKS = {"none", "break-unbreakable"}


def break_strategy_issues(element):
    """Validate proof/applicability without changing the existing text predicate."""
    issues = []
    layout = element.get("layout")
    layout = layout if isinstance(layout, dict) else {}
    version = layout.get("break_strategy_version")
    if type(version) is not int or version != 1:
        issues.append("Missing or unsupported layout.break_strategy_version")
    applicable = bool(element.get("text")) or element.get("kind") == "text"
    evidence = element.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    configuration = evidence.get("line_break_configuration")
    if not isinstance(configuration, dict):
        issues.append("Missing actual line-break configuration evidence")
        configuration = {}
    if configuration.get("applicable") is not applicable:
        issues.append("Line-break applicability does not match the existing text predicate")
    for key in ("source", "owner"):
        value = configuration.get(key)
        if not (isinstance(value, str) and value.strip() or key == "owner" and isinstance(value, dict) and value):
            issues.append("Line-break configuration has no actual " + key)
    raw = configuration.get("raw")
    if not isinstance(raw, dict) or applicable and not raw:
        issues.append("Line-break configuration has no raw provider measurements")
    for key, allowed in ((BREAK_FIELDS[0], NORMAL_BREAKS), (BREAK_FIELDS[1], EMERGENCY_BREAKS)):
        if key not in layout:
            issues.append("Missing measurement: layout." + key)
        elif applicable and (not isinstance(layout[key], str) or layout[key] not in allowed):
            issues.append("Visible text has no valid measured layout." + key)
        elif not applicable and layout[key] is not None:
            issues.append("Non-text line-break strategy must be explicitly inapplicable: " + key)
    if not applicable and not (isinstance(configuration.get("reason"), str) and configuration["reason"].strip()):
        issues.append("Non-text line-break inapplicability has no reason")
    if configuration.get("errors"):
        issues.append("Line-break configuration retains unresolved provider evidence: " + str(configuration["errors"]))
    return issues

"""Conservative source-derived platform reachability for reference vocabulary.

This is a bounded lexical proof, not a JavaScript evaluator. Only a unique,
unshadowed canonical isMac binding and braced if/else statements constrain a
use. Unsupported syntax/uses remain required on both platforms. No key names
are special-cased, and the caller's complete original vocabulary is retained.
"""
import re
from typing import NamedTuple


PLATFORMS = frozenset(("windows", "macos"))


class Token(NamedTuple):
    kind: str
    value: str
    start: int
    end: int


def tokens(text):
    result = []
    index = 0
    regex_prefix = {"(", "[", "{", ",", ";", ":", "=", "=>", "!", "?", "&&", "||", "??",
                    "===", "!==", "==", "!=", "+", "-", "*", "%", "&", "|", "^", "~", "<", ">",
                    "<=", ">=", "return", "throw", "case", "typeof", "void", "delete", "yield", "await",
                    "instanceof", "in", "of"}
    while index < len(text):
        start = index
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            index = end + 2
            continue
        if char in "'\"`":
            quote = char
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                    continue
                if quote == "`" and text.startswith("${", index):
                    raise ValueError("template interpolation is outside the bounded proof")
                if text[index] == quote:
                    index += 1
                    result.append(Token("string" if quote != "`" else "template", text[start + 1:index - 1], start, index))
                    break
                if quote != "`" and text[index] in "\r\n":
                    raise ValueError("unterminated string")
                index += 1
            else:
                raise ValueError("unterminated string")
            continue
        if char == "/":
            previous = result[-1] if result else None
            if previous is None or previous.value in regex_prefix:
                index += 1
                in_class = False
                while index < len(text):
                    current = text[index]
                    if current == "\\":
                        index += 2
                        continue
                    if current in "\r\n":
                        raise ValueError("unterminated regular expression")
                    if current == "[":
                        in_class = True
                    elif current == "]":
                        in_class = False
                    elif current == "/" and not in_class:
                        index += 1
                        while index < len(text) and text[index].isalpha():
                            index += 1
                        result.append(Token("regex", text[start:index], start, index))
                        break
                    index += 1
                else:
                    raise ValueError("unterminated regular expression")
                continue
            if previous.value == "}":
                raise ValueError("ambiguous slash after a block is outside the bounded proof")
            if (previous.kind == "identifier" and previous.value in ("else", "do", "break", "continue", "debugger", "new")
                or previous.kind not in ("identifier", "number", "string", "template", "regex")
                and previous.value not in (")", "]", "++", "--")):
                raise ValueError("unproven slash context is outside the bounded proof")
            # A slash after an expression can be division. A possible regex
            # after a control-condition close is rejected during pairing below.
        identifier = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", text[index:])
        if identifier:
            index += len(identifier.group())
            result.append(Token("identifier", identifier.group(), start, index))
            continue
        number = re.match(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text[index:])
        if number:
            index += len(number.group())
            result.append(Token("number", number.group(), start, index))
            continue
        if char == "\\":
            raise ValueError("escaped identifiers are outside the bounded proof")
        operator = next((value for value in ("===", "!==", ">>>", "=>", "==", "!=", "<=", ">=", "&&", "||", "??", "?.", "++", "--", "+=", "-=", "*=", "/=", "**", "<<", ">>")
                         if text.startswith(value, index)), char)
        index += len(operator)
        result.append(Token("punctuation", operator, start, index))
    return result


def guarded_ranges(text):
    """Return only independently proven branches and an auditable proof receipt."""
    proof = {"proved": False, "reason": None, "definition": None, "guards": []}
    branches = []
    try:
        stream = tokens(text)
        pairs, stack, scopes = {}, [], {}
        for index, token in enumerate(stream):
            scopes[index] = tuple(item for item in stack if stream[item].value == "{")
            if token.kind != "punctuation":
                continue
            if token.value in ("(", "[", "{"):
                stack.append(index)
            elif token.value in (")", "]", "}"):
                if not stack or stream[stack[-1]].value != {")": "(", "]": "[", "}": "{"}[token.value]:
                    raise ValueError("unbalanced JavaScript delimiters")
                opening = stack.pop()
                pairs[opening] = index
                pairs[index] = opening
            elif token.value in ("/", "/=") and index and stream[index - 1].value == ")":
                opening = pairs.get(index - 1)
                if opening and stream[opening - 1].value in ("if", "while", "for", "with", "switch", "catch"):
                    raise ValueError("ambiguous slash after a control statement")
        if stack:
            raise ValueError("unbalanced JavaScript delimiters")
        identities = [index for index, token in enumerate(stream) if token.kind == "identifier" and token.value == "isMac"]
        guard_by_index = {}
        for index in identities:
            if [token.value for token in stream[index + 1:index + 3]] == ["(", ")"]:
                call = stream[index]
                guard = {"id": "isMac@" + str(call.start), "line": text.count("\n", 0, call.start) + 1,
                         "condition": "isMac()", "start": call.start, "end": stream[index + 2].end,
                         "proof": "unconstrained-expression", "branches": []}
                guard_by_index[index] = guard
                proof["guards"].append(guard)
        expected = ["const", "isMac", "=", "(", ")", "=>", "PLATFORM", ".", "platform", "===", "darwin", ";"]
        expected_kinds = ["identifier", "identifier", "punctuation", "punctuation", "punctuation", "punctuation",
                          "identifier", "punctuation", "identifier", "punctuation", "string", "punctuation"]
        definitions = [index for index in identities if index > 0
                       and [token.value for token in stream[index - 1:index + 11]] == expected
                       and [token.kind for token in stream[index - 1:index + 11]] == expected_kinds]
        if len(definitions) != 1:
            raise ValueError("no unique canonical const isMac platform predicate")
        definition = definitions[0]
        scope = scopes[definition]
        definition_token = stream[definition]
        proof["definition"] = {"line": text.count("\n", 0, definition_token.start) + 1,
                               "start": stream[definition - 1].start, "end": stream[definition + 10].end,
                               "source": text[stream[definition - 1].start:stream[definition + 10].end]}
        # Do not prove a guard through possible lexical rebinding, a function
        # parameter/alias, another scope, or dynamic eval/with scope changes.
        if any(token.kind == "identifier" and token.value in ("eval", "with") for token in stream):
            raise ValueError("dynamic scope is outside the bounded proof")
        for index in identities:
            if index == definition:
                continue
            if (index < definition or [token.value for token in stream[index + 1:index + 3]] != ["(", ")"]
                or stream[index - 1].value in (".", "?.", "function", "class", "new")
                or index + 3 < len(stream) and stream[index + 3].value in ("{", "=>")
                or scopes[index][:len(scope)] != scope):
                raise ValueError("isMac has an unproven use or lexical shadow")
        for index in identities:
            if index == definition:
                continue
            guard = guard_by_index[index]
            # Ternaries, negation, boolean combinations and unbraced statements
            # remain required on both platforms; no guessed expression extent.
            if index < 2 or stream[index - 2].kind != "identifier" or [token.value for token in stream[index - 2:index]] != ["if", "("]:
                continue
            if index >= 3 and stream[index - 3].value in (".", "?."):
                continue
            if (index + 4 >= len(stream) or [token.value for token in stream[index + 3:index + 5]] != [")", "{"]
                or any(token.kind != "punctuation" for token in stream[index + 3:index + 5])):
                continue
            opening = index + 4
            closing = pairs[opening]
            branch_ranges = [("then", opening, closing, ("macos",))]
            if closing + 1 < len(stream) and stream[closing + 1].value == "else":
                if closing + 2 >= len(stream) or stream[closing + 2].value != "{" or stream[closing + 2].kind != "punctuation":
                    continue
                other = closing + 2
                branch_ranges.append(("else", other, pairs[other], ("windows",)))
            guard["proof"] = "canonical-predicate-and-braced-branches"
            for name, first, last, platforms in branch_ranges:
                branch = {"guard": guard["id"], "branch": name, "platforms": list(platforms),
                          "start": stream[first].end, "end": stream[last].start,
                          "line": text.count("\n", 0, stream[first].start) + 1,
                          "end_line": text.count("\n", 0, stream[last].start) + 1}
                guard["branches"].append(dict(branch))
                branches.append(branch)
        proof["proved"] = True
        proof["reason"] = "Only the recorded braced branches constrain occurrences; other expressions remain dual-platform"
        return branches, proof, stream
    except ValueError as error:
        proof["reason"] = str(error)
        # Never keep partial exclusions after a later lexical/identity failure.
        for guard in proof["guards"]:
            guard["proof"] = "unproven-after-analysis-failure"
            guard["branches"] = []
        return [], proof, []


def reference_key_platforms(text, keys, html=""):
    branches, proof, stream = guarded_ranges(text)
    string_spans = {(token.start, token.end) for token in stream if token.kind == "string"}
    occurrences = []

    def add(key, start, end, source, kind, lexical=False):
        guards = [branch for branch in branches if lexical and branch["start"] <= start < branch["end"]]
        platforms = set(PLATFORMS)
        for branch in guards:
            platforms.intersection_update(branch["platforms"])
        reason = "proven-enclosing-platform-guards" if guards else "no-proven-platform-restriction"
        if not platforms:
            # PLATFORM is mutable, so contradictory nested predicate reads do
            # not prove dead code. Retain the use on both platforms.
            platforms = set(PLATFORMS)
            reason = "conflicting-nested-guards-retained-on-both-platforms"
        body = html if source == "index.html" else text
        occurrences.append({"key": key, "source": source, "line": body.count("\n", 0, start) + 1,
                            "start": start, "end": end, "kind": kind, "platforms": sorted(platforms),
                            "guards": [{"id": branch["guard"], "branch": branch["branch"]} for branch in guards],
                            "reason": reason})

    for match in re.finditer(r"['\"]([a-z][a-z0-9_.-]+)['\"]", text):
        if match[1] in keys:
            add(match[1], match.start(), match.end(), "app.js", "literal", (match.start(), match.end()) in string_spans)
    for match in re.finditer(r"\bt(?:n)?\(\s*['\"]([a-z][a-z0-9_.-]*\.)['\"]\s*\+", text):
        start, end = match.start(1) - 1, match.end(1) + 1
        for key in sorted(keys):
            if key.startswith(match[1]):
                add(key, start, end, "app.js", "dynamic-prefix", (start, end) in string_spans)
    for match in re.finditer(r'data-i18n(?:-[\w-]+)?="([^"]+)"', html):
        if match[1] in keys:
            add(match[1], match.start(), match.end(), "index.html", "html")
    found = {item["key"] for item in occurrences}
    for key in sorted(keys - found):
        add(key, 0, 0, "app.js", "unlocated-original-contract-key")
    required = {key: sorted({platform for item in occurrences if item["key"] == key for platform in item["platforms"]})
                for key in sorted(keys)}
    return {"version": 1, "reference_union": sorted(keys), "predicate_proof": proof,
            "occurrences": occurrences, "key_platforms": required}

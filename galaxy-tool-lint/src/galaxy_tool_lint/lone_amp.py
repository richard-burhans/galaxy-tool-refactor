"""Classify lone ``&`` occurrences in a shell command body (GTR032's engine).

Moved from ``scripts/measure.py`` (the ``command-lone-amp`` sizing measure, which
now imports it back) when GTR032 graduated from a reserved no-op to a real
detector — check ``docs/decisions.md`` D3 (the data-backed deferral) and D34
(the revival: its stated revisit condition was met). The classes and their
semantics are unchanged, so the measure's historical numbers stay comparable.
"""

from __future__ import annotations

from collections import Counter

LONE_AMP_CLASSES = (
    "redirect",  # adjacent < or > : 2>&1, &>file, <&3 — a redirection, not joining
    "pipe",  # |& : bash pipe-with-stderr, not joining
    "quoted",  # inside '...' or "..." : a literal & in an argument (sed/awk)
    "background",  # lone & at end of a command (eol / ; / )) — intentional, not a bug
    "joining",  # lone & with a following command — the genuine GTR032 anti-pattern
)


def classify_lone_amps(text: str, /) -> Counter[str]:
    r"""Tally each lone ``&`` in *text* into a ``LONE_AMP_CLASSES`` bucket.

    Pure (string in, counts out), so it is unit-tested with synthetic bodies.
    Quote state is a simple single/double scan with bash backslash-escaping:
    outside single quotes a ``\`` escapes the next character, so an escaped
    ``\"`` / ``\'`` does not toggle quote state and an escaped ``\&`` is a literal,
    not a shell operator. Inside single quotes ``\`` is literal (bash escapes
    nothing there), so it is not treated as an escape. A ``&`` that is part of
    ``&&`` is not a lone ``&`` and is never counted.
    """
    counts: Counter[str] = Counter()
    in_single = in_double = False
    skip_next = False
    for i, ch in enumerate(text):
        if skip_next:
            skip_next = False
            continue
        if ch == "\\" and not in_single:
            skip_next = True  # bash: \ escapes the next char outside single quotes
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            continue
        if ch != "&":
            continue
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if prev == "&" or nxt == "&":
            continue  # part of && — not a lone &
        if in_single or in_double:
            counts["quoted"] += 1
        elif prev in "<>" or nxt == ">":
            counts["redirect"] += 1
        elif prev == "|":
            counts["pipe"] += 1
        else:
            j = i + 1
            while j < len(text) and text[j] in " \t":
                j += 1
            after = text[j] if j < len(text) else ""
            counts["background" if after in "\n;)" or after == "" else "joining"] += 1
    return counts

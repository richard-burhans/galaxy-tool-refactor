# When it can't fix it: actionable stops, not silent guesses

The point of a behaviour-preserving toolchain is as much about what it *refuses* to do
as what it does. When a change cannot be proven safe, `galaxy-tool-refactor` stops and
tells you three things: **what** it could not do, **why**, and **the next step** to
take by hand. It never quietly guesses and never silently leaves the job half-done.

Every command block below is the **actual output** of the shipped CLI (0.3.5).

## 1. Upgrade stops below a behaviour boundary it cannot clear

A tool with a `<conditional>` whose branches both define a `threshold` parameter, and a
`<test>` that sets `threshold` without saying which branch it means. Galaxy 24.2
tightened test-case validation to require an unambiguous path, and the toolchain cannot
qualify an ambiguous name for you:

```console
$ galaxy-tool-refactor upgrade --modernize varcall.xml
upgraded varcall.xml
  profile upgrade stopped at 24.1 (latest is 26.1): 24_2_fix_test_case_validation (must_fix at 24.2) applies to this tool and cannot be fixed automatically yet; see docs/profile_boundaries.md for what changes there and how to update the tool, or rerun with --allow-behavior-change to upgrade anyway.
  profile 21.09→24.1: upgrade crosses no behaviour change that applies to this tool — behavior-preserving.
1 file(s) upgraded.
```

It still does everything it safely can (the profile advances all the way to 24.1), then
stops one step below the boundary, names the exact Galaxy change (`24_2_fix_test_case_validation`),
points to the per-boundary reference, and offers the deliberate escape hatch
(`--allow-behavior-change`).

**What to do:** qualify the test parameter (`<param name="mode|threshold" .../>`) so it
is unambiguous, then re-run `upgrade`.

## 2. Upgrade declines a `must_fix` that has no safe automatic fix

An output declared `format="input"` while the tool has **two** data inputs, so there is
no single input to inherit the format from. Galaxy disabled `format="input"` at profile
16.04, and the toolchain will not pick an input for you:

```console
$ galaxy-tool-refactor upgrade --modernize merge.xml
unchanged merge.xml
  profile upgrade left profile= unchanged: 16_04_fix_output_format (must_fix at 16.04) applies to this tool and no vendored profile predates the first change; see docs/profile_boundaries.md for what changes there and how to update the tool, or rerun with --allow-behavior-change to upgrade anyway.
1 file(s) left unchanged.
```

**What to do:** replace `format="input"` with `format_source="a"` (or `"b"`), naming the
input whose datatype the output should inherit, then re-run `upgrade`. (When a tool has
exactly one data input the fix *is* provable, and the toolchain applies it for you. This
stop is specifically the ambiguous, multi-input case.)

## 3. `convert-help` skips when the conversion is not provable yet

Converting an RST `<help>` body to Markdown is only XSD-valid from profile 24.2 onward,
so on an older tool the command declines and tells you the prerequisite:

```console
$ galaxy-tool-refactor convert-help seqfilter.xml
skipped seqfilter.xml: profile 18.01 is below 24.2 — <help format=…> is not XSD-valid there; run `upgrade` first
0 converted, 1 skipped
```

**What to do:** run `upgrade` (or `upgrade --modernize`) to reach profile 24.2 or newer,
then re-run `convert-help`. It also skips, with a reason, when the Markdown rendering
would not be semantically identical to the original RST.

## 4. `tokenize-version` skips with the precise reason

Factoring a literal `version` into `@TOOL_VERSION@`/`@VERSION_SUFFIX@` tokens only makes
sense for the IUC `<base>+galaxy<suffix>` convention. On anything else it declines and
explains:

```console
$ galaxy-tool-refactor tokenize-version seqfilter.xml
skipped seqfilter.xml: version is not a literal "<base>+galaxy<suffix>" (already tokenized, or not using the IUC suffix convention)
0 tokenized, 1 skipped
```

**What to do:** nothing is required. This is the command correctly recognising that the
tool is out of its scope, rather than rewriting a version string it does not understand.

## The pattern

Every one of these is the same contract: a clear statement of what was not done, the
specific Galaxy change or precondition behind it, and the concrete edit (or command) that
unblocks it. The boundary reference each stop names is
[`docs/profile_boundaries.md`](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/profile_boundaries.md),
the per-boundary "what changed and what to do" guide. A warning you can act on is worth
far more than a fix you cannot trust.

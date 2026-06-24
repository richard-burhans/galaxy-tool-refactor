# A complete pass: check, format, upgrade

This walks one tool through the three everyday commands. Every command block below
is the **actual output** of the shipped `galaxy-tool-refactor` CLI (0.3.5) run on the
tool shown, not a mock-up.

## The tool

A small, plausible `samtools` wrapper. It declares an old `profile="18.01"`, leaves a
`<command>` file variable unquoted, and writes its `<help>` as bare text:

```xml
<tool id="seqfilter" name="Sequence filter" version="1.2.0" profile="18.01">
    <requirements>
        <requirement type="package" version="1.20">samtools</requirement>
    </requirements>
    <command><![CDATA[
        samtools view -b -q $min_qual $input_bam > '$output_bam'
    ]]></command>
    <inputs>
        <param name="input_bam" type="data" format="bam" label="BAM file"/>
        <param name="min_qual" type="integer" value="20" label="Minimum mapping quality"/>
    </inputs>
    <outputs>
        <data name="output_bam" format="bam" label="Filtered BAM"/>
    </outputs>
    <help>This is the help.</help>
</tool>
```

## 1. `check`: what deviates (read-only)

```console
$ galaxy-tool-refactor check seqfilter.xml
seqfilter.xml:5   GTR020  single-quoted 1 behaviour-preserving Cheetah variable(s) in <command>
seqfilter.xml:16  GTR019  <help> body is not wrapped in CDATA
2 fixable finding(s) in 1 file(s).
```

`check` is report-only and exits non-zero when there is a fixable finding, so it drops
straight into CI. Add `--ruleset strict` to also see the **advisory** IUC
best-practice findings (no `<tests>`, no `<description>`, no citations, no explicit
error handling, and so on). These are reported, never auto-changed, because fixing
them would change the tool's identity rather than preserve its behaviour.

## 2. `format`: apply the safe fixes

`format` applies only the provably behaviour-preserving fixes, then serialises:

```console
$ galaxy-tool-refactor format seqfilter.xml
reformatted seqfilter.xml
1 file(s) reformatted.
```

The diff is exactly the two safe changes, and nothing else moves:

```diff
-        samtools view -b -q $min_qual $input_bam > '$output_bam'
+        samtools view -b -q $min_qual '$input_bam' > '$output_bam'
-    <help>This is the help.</help>
+    <help><![CDATA[This is the help.]]></help>
```

`$input_bam` is an input **file** variable, so single-quoting it is safe against paths
with spaces and cannot change word-splitting (GTR020.1; see the
[soundness](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/docs/guide/soundness.md)
page). `$min_qual` is an `integer` and is left alone, since quoting it would be a no-op
outside the IUC rule's file scope. `format` never touches `profile=`.

## 3. `upgrade`: move the profile only as needed

`upgrade` is **minimal-bump by default**: it keeps `profile=` if the tool already
validates there.

```console
$ galaxy-tool-refactor upgrade seqfilter.xml
unchanged seqfilter.xml
  profile 18.01 kept: the tool validates at its declared profile; rerun with --modernize to walk newer profiles.
1 file(s) left unchanged.
```

`--modernize` opts into the behaviour-preserving walk toward the newest profile:

```console
$ galaxy-tool-refactor upgrade --modernize seqfilter.xml
upgraded seqfilter.xml
  profile walk capped at 25.1, the deployment ceiling: the newest profile every major public Galaxy server runs (snapshot 2026-06-12). A newer declaration could not install on the lagging servers yet; pass --target-profile to upgrade past it deliberately.
  profile 18.01→25.1: upgrade crosses no behaviour change that applies to this tool — behavior-preserving.
1 file(s) upgraded.
```

The walk stopped at the **deployment ceiling** (the newest profile every major public
Galaxy server actually runs), not because anything was unsafe. A newer declaration
simply could not install everywhere yet.

## When the walk must stop early

The gate's real job is to refuse an upgrade it cannot prove safe. When a tool hits a
Galaxy behaviour change the toolchain cannot clear automatically, the walk advances as
far as it provably can, then stops and names the exact blocking change and the next
step. See [When it can't fix it](when-it-stops.md) for that behaviour, worked through on
several real tools. The central guarantee is that the engine credits a fix only by
execution, and where no safe fix exists it tells you which boundary and why rather than
guessing.

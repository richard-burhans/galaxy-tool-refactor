# Demo: rename a tool parameter, everywhere, in one command

Renaming a Galaxy tool parameter by hand is a chore *and* a hazard: the name is
scattered across the `<command>` (often inside `#if` directives and dotted
`$param.metadata.…` accesses), the output `label`s, by-name cross-reference
attributes, and the `<tests>` — miss one and the tool silently breaks. The
`rename-param` command does it in one shot, **atomically**: it rewrites every real
reference or changes nothing.

## 1. A tool that references a parameter all over the place

`seqstats.xml` — note `input_bam` appears in a `#if` condition, a dotted
`.metadata.bam_index` access, a quoted command argument, the output `label`, the
`<param>` definition, and the test:

```xml
<tool id="seqstats" name="Sequence statistics" version="1.0.0" profile="21.09">
    <command><![CDATA[
        #if $input_bam.metadata.bam_index
            ln -s '$input_bam.metadata.bam_index' input.bai &&
        #end if
        samtools stats --threads \${GALAXY_SLOTS:-1} '$input_bam'
            #if $region
                --region '$region'
            #end if
            > '$stats_out'
    ]]></command>
    <inputs>
        <param name="input_bam" type="data" format="bam" label="BAM file"/>
        <param name="region" type="text" optional="true" label="Restrict to region"/>
    </inputs>
    <outputs>
        <data name="stats_out" format="txt" label="${tool.name} on ${input_bam.name}"/>
    </outputs>
    <tests>
        <test>
            <param name="input_bam" value="example.bam"/>
            <output name="stats_out" file="expected.txt"/>
        </test>
    </tests>
</tool>
```

First, see where it's used (read-only — changes nothing):

```console
$ galaxy-tool-refactor find-references input_bam seqstats.xml
seqstats.xml:3  [command]  $input_bam.metadata.bam_index
seqstats.xml:4  [command]  $input_bam.metadata.bam_index
seqstats.xml:6  [command]  $input_bam
seqstats.xml:17  [output_data_label:stats_out]  ${input_bam.name}
4 reference(s) to 'input_bam' across 1 tool(s)
```

## 2. Rename it — one command

```console
$ galaxy-tool-refactor rename-param input_bam aligned_reads seqstats.xml
renamed seqstats.xml: 6 site(s)
renamed 1 tool(s); skipped 0
```

(Six sites: the three `$`-references, the output label, the `<param>` definition,
and the `<test>` reference. Use `--check` first for a dry-run preview that writes
nothing.)

## 3. The result

```diff
     <command><![CDATA[
-        #if $input_bam.metadata.bam_index
-            ln -s '$input_bam.metadata.bam_index' input.bai &&
+        #if $aligned_reads.metadata.bam_index
+            ln -s '$aligned_reads.metadata.bam_index' input.bai &&
         #end if
-        samtools stats --threads \${GALAXY_SLOTS:-1} '$input_bam'
+        samtools stats --threads \${GALAXY_SLOTS:-1} '$aligned_reads'
             #if $region
                 --region '$region'
             #end if
             > '$stats_out'
     ]]></command>
     <inputs>
-        <param name="input_bam" type="data" format="bam" label="BAM file"/>
+        <param name="aligned_reads" type="data" format="bam" label="BAM file"/>
         <param name="region" type="text" optional="true" label="Restrict to region"/>
     </inputs>
     <outputs>
-        <data name="stats_out" format="txt" label="${tool.name} on ${input_bam.name}"/>
+        <data name="stats_out" format="txt" label="${tool.name} on ${aligned_reads.name}"/>
     </outputs>
     <tests>
         <test>
-            <param name="input_bam" value="example.bam"/>
+            <param name="aligned_reads" value="example.bam"/>
```

The renamed tool **still validates** (`galaxy-tool-refactor` parses and checks it
against the 21.09 schema). Every `input_bam` became `aligned_reads`, and nothing
else moved.

## What it got right (and what it deliberately left alone)

- **Followed the reference into a `#if` directive** and through a **dotted access**
  (`$input_bam.metadata.bam_index`) — rewriting only the parameter segment, not the
  `.metadata.bam_index` part.
- **Followed it into the output `label`** (`${input_bam.name}` → `${aligned_reads.name}`).
- **Renamed the `<tests>` reference** — a test references inputs by name, so a rename
  that forgot it would leave the test pointing at a parameter that no longer exists.
- **Left the other parameters alone** (`$region`, `$stats_out`).
- **Left the shell variable `${GALAXY_SLOTS:-1}` alone** — it is not a Galaxy
  parameter.

And it is careful by construction. `rename-param` is built on a *faithful* Cheetah
lexer, so it never rewrites a `$input_bam` that appears inside a `#raw` block, a `##`
comment, or an escaped `\$input_bam` — those are not live references. It also does
**not** touch `<help>` text, because help is rendered documentation (RST/Markdown),
not a Cheetah-templated section.

## Atomic, or nothing

If `rename-param` cannot prove *every* occurrence is safe to rewrite, it changes the
file **not at all** and tells you why — so you never get a half-renamed, broken tool.
It skips (rather than risk a wrong edit) when, for example, a `#set` local variable
shadows the name, or an output `<filter>` references the parameter by bare Python name
(`genome == 'hg19'` rather than `$genome`). Across the public Galaxy tool corpus,
**93.1%** of parameter definitions rename cleanly this way.

---

*`rename-param` is the mutating sibling of `find-references`, and the first
member of the "edit the code inside Cheetah sections" family. See
`galaxy-tool-xml/docs/decisions.md` §20 and the roadmap in
`docs/upgrade_research/cheetah_section_editing.md` (M5.3).*

# Regression fixtures — provenance

Real tools from the public Galaxy tool corpus that crashed `galaxy-tool-xml` or
exposed a violated invariant, retained by `scripts/corpus_check.py` so the
finding can never silently return. Each fixture lives in `<name>/tool.xml`,
alongside any macro files it imports.

- `bedtools` — tools-iuc `tools/bedtools/intersectBed.xml` @ `75560ba43a4b` — TypeError @ config.py:20

- `tools-iuc__gatk2` — tools-iuc `deprecated/tools/gatk2/base_recalibrator.xml` @ `75560ba43a4b` — non-contiguous

- `dazeone__kleborate__kleborate` — dazeone/kleborate `kleborate.xml` @ `latest` — XMLSyntaxError @ parser.pxi:689
- `nml__hivtrace__hivtrace` — nml/hivtrace `hivtrace.xml` @ `latest` — XmlContextError @ primitive.py:71

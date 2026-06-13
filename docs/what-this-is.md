# What galaxy-tool-refactor is (and is not)

A short orientation for anyone wondering what this project is, and in particular
whether it "uses an LLM" (it does not). For the architecture map see
[`../ARCHITECTURE.md`](../ARCHITECTURE.md); for build, test, and lint commands see
[`../CLAUDE.md`](../CLAUDE.md).

## The one-sentence version

galaxy-tool-refactor is a **deterministic refactoring toolkit for Galaxy tool
XML**: think `ruff`, `black`, and LibCST, but for Galaxy tools instead of Python.
It parses, validates, lints, formats, and safely upgrades tool XML. **It does not
run a language model.**

## The guiding principle: fix what is provable, hand back the rest as decisions

A design philosophy crystallized while building the tool, and it now shapes the
whole architecture:

> **Automatically fix everything that can be proven safe to fix, and for
> everything else return useful, actionable information so the human can decide
> what to do.**

The tool never makes a change it cannot justify, and it never just dumps a problem
on you. When it can prove a fix preserves behavior, it applies it. When it cannot,
it does not guess and it does not stay silent: it tells you what is wrong, where it
is, what would change, and what your options are. For example, when a profile
upgrade has to stop, it names the exact Galaxy behavior change that blocks it and
links to a reference explaining what that change means and what to do about it.
The division of labor is deliberate: the machine does the provable mechanical
work, and the human makes the judgment calls, well-informed.

## It is a deterministic program, not a language model

At runtime the tool does pure static analysis and transformation:

1. parse the XML into a faithful tree (the source of truth),
2. validate it against the correct per-release Galaxy schema,
3. lex the Cheetah in `<command>` bodies,
4. apply rule-based transformations,
5. serialize the result.

The same input always produces the same output. There is no model, no inference,
no randomness, and no network call. Every change it makes is explainable and
reproducible, and you can read the rule that made it.

## The syntax and semantics framing

The cleanest way to see the difference from an LLM is *what each one reasons
about*:

- **This tool reasons about formal, provable properties.** Schema grammar (is the
  XML valid against release N's XSD?), macro-expansion semantics (what does Galaxy
  actually produce after expanding the macros?), render equivalence (does the
  converted help render the same?), and Cheetah lexical structure. These questions
  have ground-truth answers, and the tool only auto-fixes a thing when it can
  **prove** the fix preserves behavior. When it cannot prove safety, it declines
  and, at most, reports an advisory.
- **A language model reasons about statistical plausibility.** It produces output
  that looks right, with no correctness guarantee.

So the contrast is: deterministic, provable, and reproducible (this tool) versus
statistical, plausible, and unverified (an LLM).

A concrete illustration arrived unbidden: an automated bot opened a pull request
on this very repository claiming a CI fix "uses the Node 24 runtime." The claim
was simply false, and the change would have passed a basic CI check while not
actually fixing anything. Plausible, and wrong. A deterministic tool gated on
ground truth does not make that class of mistake.

## "Built with AI agents" is not "is an AI agent"

This project *was* written with the help of AI coding agents, under a
corpus-grounded, test-driven discipline (a failing test first, real-world
counterexamples retained as permanent regression fixtures, conventions encoded as
guard tests). That is a fact about **how the software was built**, not about
**what the software is**. The shipped artifact contains no model and makes no
model calls. Built with agents, not an agent.

## It is agent-facing by design (this is not an anti-LLM stance)

The deterministic core is meant to be *called by* agents. The whole framework is
library-first and introspectable, and it ships a Model Context Protocol server so
an AI authoring agent can discover the available rules and invoke discrete
`detect` and `fix` operations. The intended division of labor is simple and, we
think, the right one for trustworthy automation:

> the language model **generates**; this framework **verifies, corrects, and
> gates**.

The deterministic guarantees are exactly what an LLM cannot provide on its own,
and they are what make agent-assisted tool authoring safe.

The guiding principle above is also what makes the tool **dual-use**: the very
same outputs serve a person and a program. The actionable information a human
reads to decide what to do is the same structured detect-and-fix result an agent
consumes programmatically. One tool, useful to people and to machines at once.

Concretely, one library-first facade sits under two thin front-ends: a
command-line interface for people, and a Model Context Protocol (MCP) server for
agents. **An agent working through MCP can do the same things a person does at the
command line** (format, check, upgrade, and the rest), because both front-ends are
just different doors onto one shared implementation. Neither audience is a
second-class citizen.

And there is a third class of user: **developers**. Because every tier is an
independently-installable library with a stable surface (the foundation library
is published to PyPI), a developer can import just the parser, the formatter, the
codemod framework, or the whole facade and build on it for purposes we have not
imagined. The Galaxy Language Server integration is already one such case, built
on the tier-1 offset planner to provide in-editor renames. So the same core
serves people (the CLI), agents (MCP), and developers (the libraries), and the
last of those is open-ended by design.

## Where this is headed

A primary motivation, still early and deliberately underspecified, is to use this
toolkit as the backbone of a future system that **trains an AI agent to wrap
Bioconda packages as Galaxy tool XML**. In that system, this deterministic
framework would serve as the **verification and reward oracle** during training
(does the agent's wrapper validate, lint clean, and behave correctly?) and as the
**runtime guardrail** afterward. The point of building the provable layer first is
that it is what would make such an agent's output trustworthy.

Bioconda was chosen for a specific reason: thousands of Bioconda packages have
*already* been hand-wrapped as Galaxy tools (across the IUC repositories and the
ToolShed), so a **training corpus of package-to-wrapper pairs already exists**,
and it is the very same corpus this framework was built and validated against.
The corpus therefore does triple duty: the regression and QA suite for the
toolkit today, the bug-finding oracle that kept development honest, and the
training data for the wrapping agent tomorrow.

A further, more speculative horizon: if a reliable wrapping agent is achievable,
the next question is whether it can be decomposed (or distilled) into something
that runs on a person's **local computer with a modest, not-very-expensive GPU**,
rather than requiring an expensive cloud service. The deterministic framework is
what makes this plausible: because correctness comes from the provable
verification layer rather than from the raw capability of the model, the
generative part can be smaller and cheaper than it would need to be on its own.
The goal is plain: run it on hardware people already own so they can use it **for
free, without being stuck paying per-token API costs**. Lowering the cost and
hardware bar this way is, ultimately, about accessibility for the whole community,
and it fits the project's open-source, MIT-licensed ethos.

To be clear, this last part is an aspiration, not a roadmap promise. The author
does not yet know whether it is reachable. It is recorded here as the direction
the deterministic groundwork is meant to enable, not as a commitment that it will
arrive.

## A short FAQ

- **Does it use an LLM at runtime?** No. It is a deterministic program.
- **Was it built with AI?** Yes, with coding agents, under a corpus-grounded TDD
  discipline that verifies the agents did what was intended.
- **Is it trying to replace Planemo?** No. It is complementary: Planemo remains the
  reference linter; this adds a fix phase, an autoformatter, a library surface, and
  a behavior-preserving upgrade engine. We reimplemented Planemo's checks largely
  to use Planemo as a bug-finding oracle for our own framework.
- **Will it change my tool's behavior when it formats or upgrades it?** No. Format
  is behavior-preserving by construction, and upgrade moves the profile only as
  far as it can prove is safe (minimal by default; the fuller modernize walk is
  opt-in and gated).
- **Is it associated with the AI bots that file low-quality PRs?** No, the
  opposite: a deterministic, proof-gated tool is the kind of thing that catches
  those.

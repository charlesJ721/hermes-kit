# Conventions

> Design principles and coding conventions for the hermes-kit monorepo.

## Writing Style

1. **English.** All documentation in English — this repo is for sharing with an international audience.
2. **Conclusion-first.** Lead with the actionable takeaway; provide context and evidence below.
3. **Model-agnostic where possible.** When a pattern works with any model family, say so. Name specific models only when the choice is consequential (different model = different failure mode).
4. **Provider is implementation detail.** Never encode provider names (APIs, proxy services, auth schemes) in pattern documentation. Provider logic belongs in config files and env vars, not shared documents.

## Sanitization

Before sharing any pattern extracted from a personal deployment:

- [ ] Provider names replaced with generic roles (primary/secondary/fallback)
- [ ] API keys, tokens, passwords removed
- [ ] Local filesystem paths replaced with generic placeholders
- [ ] Personal identifiers (name, employer, location) removed
- [ ] Session IDs, job IDs, timestamps removed
- [ ] Exact cost figures replaced with relative annotations (if needed at all)

## Module Structure

Each module (e.g., `TOF/`) should be:

1. **Self-contained** — readable without reading other modules
2. **Linkable** — internal references use relative paths, not anchor text
3. **Failure-annotated** — every pattern includes a "what went wrong before this" section
4. **Version-tracked** — major changes noted in the module's changelog

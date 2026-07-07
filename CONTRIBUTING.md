# Contributing

## TOF core changes require review

Changes that touch TOF core files must include a `REVIEW.md` file in the same commit or pull request diff. The review should be produced by a model family different from the one that authored or implemented the change, and it must include a `review.verdict` or `verdict:` field.

The CI guard checks only the current diff for a `REVIEW.md`; a pre-existing `REVIEW.md` in the repository does not satisfy this requirement.

## Generate `REVIEW.md`

From the `TOF/` directory, run:

```bash
tof run --only review <run_dir>
```

Commit the generated `REVIEW.md` together with the TOF core-file changes it reviews.

## TOF docs

See [`TOF/README.md`](TOF/README.md) for the TOF overview, validation checks, project structure, and usage examples.

# Package module

Use this module to assemble the final delivery from explicitly declared artifacts.

## Action

- `assemble`: create an inspectable delivery folder, archive when requested, and machine-readable manifest.

Derive package contents and naming from the user request and the artifact manifest. Do not zip the entire workspace by habit. Include only declared artifacts plus required runtime files, documentation, or source dependencies. Use the exact archive name in the request; when an archive is required but unnamed, use `submit.zip`. Do not add invented suffixes such as "final", "v2", or "AI version".

`submit/` contains **only final deliverable content** the user can hand over directly: documents, slides, images, source folders, and requested runtime files. Never place compiled programs, build output (`dist/`, `build/`, `target/`, `out/`, `bin/`, `obj/`, `.next/`, `*.exe`, `*.dll`, `*.class`, …), editor/tool metadata (`.idea/`, `.vscode/`, `coverage/`), or AutoFlow run metadata (`manifest.json`, `*_manifest.json`, `workflow.json`, `artifact_manifest.json`, `run_state.json`, `requirement_map.json`, `delivery_review.json`) inside `submit/`. These are rejected by the packager as hard errors and by `--verify-only` as pollution.

Write `.autoflow/intermediate/plans/package.json` with `source_root`, `include_paths`, `exclude_globs`, output names, and `requirement_ids` for every included path. Final deliverables must be written below `submit/`. Run all source/application verification first in `.autoflow/intermediate/verification/`; never execute tests, migrations, installers, or applications in `submit/`.

When an archive is required, publish both an inspectable delivery folder and its archive. If only the report is requested, include only the final document; include screenshots, logs, data, video, or code only when the requirement calls for them. Before packaging, review every selected artifact against the requested count, relevance, quality, and naming. Do not treat file existence as acceptance. Duplicate intermediates, editor leftovers, and logs that were not requested are excluded.

Run `package_submission.py --config .autoflow/intermediate/plans/package.json` exactly once after inputs are frozen. It assembles in an isolated staging directory, recursively excludes VCS/runtime/cache/secret/build/metadata paths, validates the folder and archive, then atomically publishes the result. The `autoflow/package-manifest/1.0` manifest is run metadata and is written to `.autoflow/intermediate/plans/`, never inside `submit/`. After publication run only:

```bash
python scripts/package_submission.py --config <package.json> --verify-only
```

Retain the manifest. It must show matching folder/archive listings, per-file hashes, requirement mappings, exclusion counts, ZIP integrity, and no forbidden files in either the folder or the archive.

At PLAN_STOP, run `package_submission.py --config .autoflow/intermediate/plans/package.json --validate-plan`. This checks path containment and requirement mappings without requiring source artifacts that downstream steps have not produced yet.

Reject missing files, duplicate archive paths, symbolic links, secrets, caches, temporary outputs, nested copies of the package itself, and names that violate the request. If an input changes after packaging, revise the package step instead of testing or patching the published folder.

The handoff must be reproducible, reversible where applicable, and explicit
about what was verified.

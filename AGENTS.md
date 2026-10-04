# DevProgress repository

This repository contains the static “北四楼来信 开发进度” website and its local data pipeline.

- `todo.json` is the only task/score/evidence source. Never hand-edit generated website scores or rewrite historical scores using new rules.
- Read `README.md`, `Demo目标.md`, the Todo schema and the game repository's `AGENTS.md` before assessment. Game paths belong in ignored `config.local.json`.
- The game repository is read-only for this project's work. Never run Godot, headless validation, exports, game tests or play-throughs. Website/data checks may run independently.
- Keep manual UI/polish scores and still-valid user verification. Unknown values remain null; feature-branch implementation is distinct from main integration.
- Only `site/` is a deployment artifact. Do not publish story documents, local absolute paths, credentials or unapproved files. Source docs here describe scope/design, not story prose.
- First remote creation/publication needs an explicit request. After the first authorized successful deployment, routine “请更新进度条” includes committing relevant progress changes, normal push and verifying Pages success. Never push game changes or force push.
- Verify with `python3 validate_todo.py`, `python3 -m unittest discover -s tests -v`, and `python3 scripts/build_site.py`. Use a local browser for responsive/interaction checks when UI changes.

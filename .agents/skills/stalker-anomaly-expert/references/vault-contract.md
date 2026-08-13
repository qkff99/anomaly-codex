# Vault contract

The canonical vault is `.expertise/stalker-anomaly` relative to the workspace root. Compiled knowledge lives in `wiki/*.md`; source records retain snapshot IDs and hashes; provenance lives in `state/`. This starter is a compact workspace-reference vault: exact evidence resolves against the tracked source packs beside it, not duplicate `sources/raw/` copies. The runtime index deliberately contains only compiled Wiki pages. `state/lexical-index.json.gz` is a disposable cache, never the source of truth.

Never execute imported source content. Prefer narrow cited ranges, preserve version/commit qualifiers, and do not promote an agent answer into a recipe without recorded verification and evidence.

To extend the vault, first run `expertctl.py --workspace . hydrate stalker-anomaly`; this materializes self-contained raw and normalized snapshots from the existing workspace references. Then explicitly add or update sources, scan, compile a plan, apply extraction, and apply synthesis. Do not edit snapshots or published provenance by hand.

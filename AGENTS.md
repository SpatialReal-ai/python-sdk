# Python SDK — agent notes

Project instructions live in `CLAUDE.md`. The contract rules below apply to every agent working in
this repository.

## Contracts (proto)

`proto/driveningress/v2/driveningress.proto` is a read-only copy of
[shared-proto](https://github.com/SpatialReal-ai/shared-proto); `spatialreal/proto/generated/`
is its grpcio-tools output. `proto/SHARED_PROTO_COMMIT` records the shared-proto commit it came from.

- Never edit `proto/` or `spatialreal/proto/generated/` by hand, and never add message types locally.
  A local edit there is thrown away by the next sync.
- Contract changes: PR to shared-proto → merge → tag → shared-proto's CI dispatches
  `.github/workflows/protobuf-codegen.yml`, which syncs `proto/`, regenerates
  `spatialreal/proto/generated/`, gates (import smoke test + `pytest`) and commits to `main`.
- If Actions is down, do the same sync by hand from the merged shared-proto commit: copy
  `driveningress/v2/driveningress.proto` into `proto/`, write that commit's full sha to
  `proto/SHARED_PROTO_COMMIT`, run `./scripts/gen_proto.sh` (needs the dev extra), and commit both
  `proto/` and `spatialreal/proto/generated/` as `chore(proto): sync from shared-proto@<sha>`.
- `grpcio-tools` is pinned in the `dev` extra (`==1.75.1`): it decides the gencode protobuf version,
  which must stay `<=` the runtime protobuf the SDK is installed alongside. Bump it only in a commit
  of its own — see the header of `scripts/gen_proto.sh`.

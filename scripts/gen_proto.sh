#!/bin/sh
# Regenerate spatialreal/proto/generated from the vendored proto.
#
# The vendored copy under proto/ is the build input; proto/SHARED_PROTO_COMMIT records
# which shared-proto commit it came from. To pick up protocol changes: copy the new
# driveningress/v2/driveningress.proto from shared-proto, update SHARED_PROTO_COMMIT,
# then run this script (needs the dev extra: pip install -e ".[dev]").
#
# grpcio-tools is pinned: its bundled protoc decides the GENCODE version, and the
# protobuf runtime everywhere the SDK is installed (livekit-agents venvs run 6.x)
# must be >= that gencode. Bumping grpcio-tools past a protobuf major without
# raising the runtime floor breaks every consumer at import time.
set -eu
cd "$(dirname "$0")/.."

python -m grpc_tools.protoc \
  -I proto \
  --python_out=spatialreal/proto/generated \
  --pyi_out=spatialreal/proto/generated \
  proto/driveningress/v2/driveningress.proto

# grpc_tools writes package-relative paths; flatten to the layout the SDK imports
# (spatialreal/proto/generated/message_pb2.py) and fix the module name.
mv spatialreal/proto/generated/driveningress/v2/driveningress_pb2.py spatialreal/proto/generated/message_pb2.py
mv spatialreal/proto/generated/driveningress/v2/driveningress_pb2.pyi spatialreal/proto/generated/message_pb2.pyi
rm -rf spatialreal/proto/generated/driveningress

echo "generated: spatialreal/proto/generated/message_pb2.py"

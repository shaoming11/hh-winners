#!/usr/bin/env bash
# Fetch the official SO-101 MuJoCo model + meshes from TheRobotStudio/SO-ARM100.
# These are ~11 MB of third-party assets, so they are gitignored and fetched on demand.
set -euo pipefail

RAW="https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/main/Simulation/SO101"
DEST="$(cd "$(dirname "$0")/.." && pwd)/sim/assets/so101"
mkdir -p "$DEST/assets"

MODELS="so101_new_calib.xml so101_new_calib.urdf joints_properties.xml"
MESHES="base_motor_holder_so101_v1.stl base_so101_v2.stl sts3215_03a_v1.stl \
waveshare_mounting_plate_so101_v2.stl motor_holder_so101_base_v1.stl \
rotation_pitch_so101_v1.stl upper_arm_so101_v1.stl under_arm_so101_v1.stl \
motor_holder_so101_wrist_v1.stl sts3215_03a_no_horn_v1.stl \
wrist_roll_pitch_so101_v2.stl wrist_roll_follower_so101_v1.stl moving_jaw_so101_v1.stl"

for f in $MODELS; do
  [ -s "$DEST/$f" ] && { echo "  have $f"; continue; }
  echo "  get  $f"; curl -fsSL --retry 3 -o "$DEST/$f" "$RAW/$f"
done
for f in $MESHES; do
  [ -s "$DEST/assets/$f" ] && { echo "  have assets/$f"; continue; }
  echo "  get  assets/$f"; curl -fsSL --retry 3 -o "$DEST/assets/$f" "$RAW/assets/$f"
done
echo "SO-101 assets ready in $DEST"

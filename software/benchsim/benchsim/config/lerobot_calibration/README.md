# LeRobot calibration of the two SO-101 followers (2026-10-17)

Made with `lerobot-calibrate --robot.type=so101_follower --robot.port=PORT --robot.id=ID` (lerobot 0.6.1).
LeRobot reads the followers from `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json` and the leader from `.../teleoperators/so_leader/wlb_leader.json`; copy them there
on another machine.

| id | arm | where it sits | USB port on Jerry's Mac |
|---|---|---|---|
| `wlb_transfer` | transfer (carousel <-> scale) | left, seen from behind the arms looking out at the sled; next to the turntable | `/dev/cu.usbmodem58CD1767761` |
| `wlb_pourer` | pourer (rack, scale, funnel) | right, by the rack | `/dev/cu.usbmodem58760435221` |
| `wlb_leader` | SO-101 **leader** (teleop, `--teleop.type=so101_leader`) | hand-held | `/dev/cu.usbmodem5AE60857881` |

Gripper range: fully open to the TPU fin-ray fingertips just touching (no squeeze), so "closed" never stalls the servo.

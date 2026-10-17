"""Fin-ray gripper geometry shared by the scene builder and the planners (metres).

The printed GR-01/02/03 gripper holds a Phi56 beaker with the contact ~40 mm along the 65 mm
fin-ray finger (gripper_design.json contact_u 40.4).  The sim's straight fingers reproduce that
by putting the beaker centre BEAKER_OUT from the jaw hinge along the fingers, so its contact
line falls inside the finger length for both the side grasp and the top-down grasp.
"""
FINGER_L = 0.065
FINGER_W = 0.024
FINGER_T = 0.008
BEAKER_OUT = 0.050                 # hinge -> beaker centre (grasp site), along the finger
TIP_BEYOND_SITE = FINGER_L - BEAKER_OUT   # finger tips reach this far past the grasp site
FIXED_FACE_X = -0.012
SITE_GAP = 0.0007                  # beaker surface to the fixed finger face at the grasp site;
                                   # small so the 1.5 deg sim squeeze presses the beaker onto the
                                   # fixed finger (stall = grasp) before it reaches a pocket wall
JAW_CONTACT = 0.35                 # rad, MJCF gripper joint at Phi56 contact
JAW_TRAVEL_DEG = 14.0

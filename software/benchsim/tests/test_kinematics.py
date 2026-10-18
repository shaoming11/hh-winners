import numpy as np
import pytest

from benchsim import cadmap, kinematics, layout, poses, trajectories

# these compare the sim against the arm paths recorded in the original CAD layout (carousel on Y-left); the trial saddle
# layout moves the carousel, so those recordings no longer describe it. They say nothing about whether the demo works.
TRIAL_LAYOUT = layout.load_final()['carousel']['mount'].startswith('TRIAL')
cad_recording = pytest.mark.skipif(TRIAL_LAYOUT, reason='CAD-recorded paths are for the original carousel position (trial saddle layout active)')


@pytest.fixture(scope='module')
def planner(built):
    model, b = built
    return poses.Planner(model, b)


@cad_recording
def test_sign_search_unique_all_positive(planner):
    rows = trajectories.sign_search(planner.K, planner.b)
    assert rows[0]['signs'] == [1, 1, 1, 1, 1] and rows[0]['all_in_limits']
    assert rows[1]['mean_err_mm'] > 2 * rows[0]['mean_err_mm']


@cad_recording
def test_mapping_reported_approximate(planner):
    ends = trajectories.endpoint_table(planner.K, planner.b)
    assert max(r['residual_mm'] for r in ends) < 15
    assert all(r['binding'] == 'wrist_flex' for r in ends)            # same binding joint as the planner
    assert trajectories.status(ends, trajectories.audit(planner.K, planner.b)) == 'approximate'


def test_ik_round_trip(planner):
    q = np.r_[cadmap.cad_to_mj(np.radians(planner.rec['P_wat']['q_pick'])), 0.3]
    p, R = planner.K.site('pourer', q, 'grasp_side')
    q2, e, a = planner.K.ik('pourer', 'grasp_side', p + [5, -5, 10], z_axis=R[:, 2], q0=q)
    assert e < 0.05 and a < 0.05


def test_native_transfer_plan_clean(planner):
    segs = planner.plan_transfer('P1', 'carousel_pick', 'scale_pan')
    rows = planner.check_plan('transfer', segs, {})
    assert all(r['contacts'] == 0 for r in rows)
    assert all(r['margin_ok'] for r in rows)


@cad_recording
def test_top_down_lift_limit(planner):
    rec = planner.rec['T1']['anim_paths'][0]['qs'][0]
    q = np.r_[cadmap.cad_to_mj(rec), planner.q6_wide]
    _, e, _ = planner.K.ik('transfer', 'grasp_td_taught', planner.station('carousel_pick') + [0, 0, 80], z_axis=[0, 0, 1], q0=q)
    assert e > 5            # +80 mm with the hand pointing down is out of reach (wrist flex limit)

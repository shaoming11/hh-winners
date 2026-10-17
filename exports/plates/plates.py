"""Slice the v2 print plan plate by plate. Each plate must come out as exactly ONE plate; times are recorded.
usage: python plates.py  (reads STLs from the repo exports, writes plates/ and a JSON summary)"""
import os, sys, subprocess, json, shutil, glob, re, zipfile
import numpy as np
P = "C:/Users/User/fusion_bridge/prints_v2"
OUT = os.path.join(os.path.expanduser('~'), 'bbl', 'plates'); os.makedirs(OUT, exist_ok=True)
ST = os.path.join(OUT, 'stl'); os.makedirs(ST, exist_ok=True)
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
from orient_stl import rd, wr
def rot(f, R):
    a = rd(f); v = a['v'].reshape(-1, 3).astype(float) @ np.array(R, float).T; v[:, 2] -= v[:, 2].min()
    a['v'] = v.reshape(-1, 9).astype('f4'); a['n'] = (a['n'].astype(float) @ np.array(R, float).T).astype('f4'); wr(f, a)
def stage(stem, how=None):
    src = os.path.join(P, stem + '.stl'); dst = os.path.join(ST, stem + '.stl'); shutil.copy(src, dst)
    if how == 'best':
        subprocess.run([sys.executable, os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'orient_best.py'), dst], check=True, capture_output=True)
    elif how == 'xup':
        subprocess.run([sys.executable, os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'orient_stl.py'), dst], check=True, capture_output=True)
    elif how == 'rx90':
        rot(dst, [[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    elif how == 'flip':
        rot(dst, [[1, 0, 0], [0, -1, 0], [0, 0, -1]])
    return dst
S = {
    'ST11': stage('ST-11_stage-sled_qty1_SUPPORTS'), 'ST12': stage('ST-12_servo-bridge_qty1', 'flip'), 'ST13': stage('ST-13_crank_qty1'),
    'ST14': stage('ST-14_connecting-rod_qty1'), 'ST15': stage('ST-15_pivot-spacer_qty2'), 'TT01': stage('TT-01_turntable-base-v2_qty1'), 'WS01v3': stage('WS-01_scale-base-v3_qty1'), 'FX01': stage('FX-01_E5-joiner-plate_qty1'),
    'GR03': stage('GR-03_fin-ray-finger_qty4_TPU', 'xup'), 'ST09': stage('ST-09_stop-post-sleeve_qty2_TPU'),
    'GR01': stage('GR-01_gripper-body_qty2_SUPPORTS', 'best'), 'GR02': stage('GR-02_moving-jaw_qty2_SUPPORTS', 'best'),
    'AG01': stage('PS-01_auger-post_qty1', 'rx90'), 'DH01': stage('DH-01_yeast-auger-head-v4_qty1_SUPPORTS'),
    'DH02': stage('DH-02_auger-screw-v3_qty2_SUPPORTS'), 'WS01': stage('WS-01_scale-base-v2_qty1'), 'WS02': stage('WS-02_scale-pan-v2_qty1'),
    'TT04': stage('TT-04_beaker-locator-ring-v2_qty1'), 'RK02': stage('RK-02_reagent-rack-v2_qty1'), 'ST08': stage('ST-08_bearing-race-spacer-v2_qty6'),
    'CAL01': stage('CAL-01_arm-calibration-block_qty2'), 'CAL02': stage('CAL-02_calibration-probe_qty1', 'flip'),
}
# printer, plate name, material, infill, supports, parts (with copies)
PLAN = [
    ('a1',  'A1-1_TPU_fingers-sleeves', 'tpu', 30, False, ['GR03'] * 4 + ['ST09'] * 2),
    ('a1',  'A1-2_PS-01-auger-post', 'pla', 30, False, ['AG01']),
    ('a1',  'A1-3_CAL-01x2', 'pla', 15, False, ['CAL01', 'CAL01']),
    ('h2d', 'H2D-1_gripper-bodies', 'pla', 30, True, ['GR01', 'GR01', 'GR02', 'GR02']),
    ('h2d', 'H2D-2_auger-head-v4', 'pla', 15, True, ['DH01']),
    ('h2d', 'H2D-2b_auger-screw-v3x2', 'pla', 99, True, ['DH02', 'DH02']),
    ('h2d', 'H2D-3_stage-sled-bridge-crank-rod', 'pla', 25, True, ['ST11', 'ST12', 'ST13', 'ST14', 'ST15', 'ST15']),
    ('h2d', 'X2-5_TT-01-v2', 'pla', 15, False, ['TT01']),
    ('a1', 'A1-4_WS-01-v3_FX-01', 'pla', 15, False, ['WS01v3', 'FX01']),
    ('h2d', 'X2-1_scale-pan-spacers', 'pla', 15, False, ['WS02'] + ['ST08'] * 6),
    ('h2d', 'X2-2_TT-04', 'pla', 15, False, ['TT04']),
    ('h2d', 'X2-3_RK-02', 'pla', 15, False, ['RK02']),
    ('h2d', 'X2-4_CAL-02', 'pla', 15, False, ['CAL02']),
]
only = sys.argv[1:]
summary = {}
if os.path.exists(os.path.join(OUT, 'summary.json')): summary = json.load(open(os.path.join(OUT, 'summary.json')))
for printer, name, mat, infill, sup, parts in PLAN:
    if only and not any(o in name for o in only): continue
    env = dict(os.environ); env['KEEP'] = os.path.join(OUT, name + '.gcode.3mf'); env['COLOR'] = '#FFFFFF' if mat == 'pla' else '#202020'
    if sup: env['SUP'] = '1'
    else: env.pop('SUP', None)
    r = subprocess.run([sys.executable, os.path.join(os.path.expanduser('~'), 'bbl', 'slice.py'), printer, str(infill), mat] + [S[p] for p in parts], capture_output=True, text=True, env=env, timeout=3600)
    lines = [l for l in r.stdout.splitlines() if '|' in l]
    times = [l.split('|')[1].strip() for l in lines]; grams = [l.split('|')[2].strip() for l in lines]
    summary[name] = {'printer': printer, 'material': mat, 'infill': infill, 'supports': sup, 'parts': parts, 'plates': len(lines), 'time': times, 'grams': grams}
    print('%-30s plates=%d  %s  %s %s' % (name, len(lines), times, grams, '' if len(lines) == 1 else '  <<< SPLIT INTO %d PLATES' % len(lines)), flush=True)
    json.dump(summary, open(os.path.join(OUT, 'summary.json'), 'w'), indent=1)

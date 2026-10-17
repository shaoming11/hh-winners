"""Render-time effects for the camera views (dashboard video, replays, previews). See ``look`` for what is drawn.

    from benchsim import fx
    r = Renderer(world.m, 960, 540, fx=fx.make(world))     # after the Ledger and the liquid, auger and foam models exist

Effects are drawn into each frame's scene copy only. The model, the data and every simulated number are untouched, and
renderers without ``fx`` (the vision camera, verify_mechanisms) render the plain scene.
"""
from .ctx import Context
from .look import Look, assets  # noqa: F401


def make(world):
    """the bench look for this world, as a callable on a rendered scene: fx(scn)"""
    return Look(Context.from_world(world))

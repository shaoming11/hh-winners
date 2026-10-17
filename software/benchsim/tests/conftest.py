import mujoco
import pytest

from benchsim import scene, state


@pytest.fixture(scope='session')
def built():
    model, b = scene.build()
    return model, b


@pytest.fixture
def sim(built):
    model, b = built
    data = mujoco.MjData(model); state.reset(model, data)
    return model, data, b

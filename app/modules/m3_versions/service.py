from app.modules.m3_versions.rules import apply
from app.modules.m3_versions.ganging import adjudicate

def execute(state):
    return adjudicate(apply(state))

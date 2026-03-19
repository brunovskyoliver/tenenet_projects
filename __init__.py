from . import controllers
from . import models


def pre_init_hook(env):
    env.cr.execute("ALTER TABLE tenenet_project RENAME COLUMN program_director_id TO odborny_garant_id")
    env.cr.execute("ALTER TABLE tenenet_project DROP COLUMN IF EXISTS financial_manager_id")

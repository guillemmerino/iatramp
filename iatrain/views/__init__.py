from .athletes import athlete_create, athlete_detail, athlete_list
from .dashboard import home
from .engine import context_options, training_start
from .groups import group_create, group_detail, group_list, group_member_remove
from .gyms import (
    gym_create,
    gym_detail,
    gym_edit,
    gym_equipment_create,
    gym_equipment_edit,
    gym_list,
)
from .organizations import organization_detail, organization_list
from .profiles import select_perspective, update_profile

__all__ = (
    "athlete_create",
    "athlete_detail",
    "athlete_list",
    "context_options",
    "group_create",
    "group_detail",
    "group_list",
    "group_member_remove",
    "gym_create",
    "gym_detail",
    "gym_edit",
    "gym_equipment_create",
    "gym_equipment_edit",
    "gym_list",
    "home",
    "organization_detail",
    "organization_list",
    "select_perspective",
    "training_start",
    "update_profile",
)

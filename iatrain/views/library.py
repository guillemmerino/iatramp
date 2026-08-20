from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from iatrain.library import build_library

from .common import base_context, require_coach


@login_required
def library(request):
    owner = require_coach(request)
    context = base_context(request)
    context.update({"library": build_library(request=request, owner=owner)})
    return render(request, "iatrain/library/index.html", context)

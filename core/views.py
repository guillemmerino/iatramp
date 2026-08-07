from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from organizations.forms import (
    MembershipAccessForm,
    OrganizationCreateForm,
    OrganizationEditForm,
    OrganizationJoinRequestForm,
)
from organizations.models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
)
from organizations.policies import can_manage_organization, has_organization_permission
from organizations.selectors import (
    current_membership_filter,
    reviewable_membership_requests_for_user,
)
from organizations.services import (
    cancel_organization_membership_request,
    create_organization_for_user,
    request_organization_membership,
    review_organization_membership_request,
    update_membership_access,
)

from .forms import (
    PersonProfileForm,
)
from .models import Person
from .services import person_for_user


def _add_validation_error(form, error):
    if hasattr(error, "message_dict"):
        for field, field_messages in error.message_dict.items():
            target = field if field in form.fields else None
            for message in field_messages:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


def _profile_required(request):
    person = person_for_user(request.user)
    if person is None or person.is_provisional:
        messages.info(request, "Completa el perfil personal per continuar.")
        return None
    return person


def _platform_identity_context(request):
    user = request.user
    person = None
    memberships = []
    if user.is_authenticated:
        person = Person.objects.filter(user=user, is_active=True).first()
        if person is not None:
            today = timezone.localdate()
            memberships = list(
                person.memberships.filter(
                    status=Membership.Status.ACTIVE,
                    organization__is_active=True,
                    start_date__lte=today,
                )
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
                .select_related("organization")
                .prefetch_related(
                    Prefetch("roles", queryset=MembershipRole.objects.filter(is_active=True))
                )
                .order_by("organization__name")
            )
    if person is not None:
        display_name = person.display_name
    elif user.is_authenticated:
        display_name = user.get_full_name().strip() or user.get_username()
    else:
        display_name = "Visitant"
    initials = "".join(part[:1] for part in display_name.split()[:2]).upper() or "IA"
    return {
        "platform_person": person,
        "platform_memberships": memberships,
        "platform_display_name": display_name,
        "platform_initials": initials,
    }


class PlatformContextMixin:

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_platform_identity_context(self.request))
        return context


class PlatformHomeView(PlatformContextMixin, TemplateView):
    template_name = "core/platform_home.html"


def platform_settings_redirect(request):
    return redirect("profile")


@login_required
def profile(request):
    person = Person.objects.filter(user=request.user).first()
    initial = {}
    if person is None:
        initial = {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
        }
    modal_open = person is None or person.is_provisional or request.GET.get("editar") == "1"
    if request.method == "POST":
        form = PersonProfileForm(request.POST, instance=person)
        if form.is_valid():
            with transaction.atomic():
                saved_person = form.save(commit=False)
                saved_person.user = request.user
                saved_person.is_active = True
                saved_person.is_provisional = False
                saved_person.full_clean()
                saved_person.save()
            messages.success(request, "El perfil personal s'ha desat.")
            return redirect("profile")
        modal_open = True
    else:
        form = PersonProfileForm(instance=person, initial=initial)
    pending_by_organization = list(
        reviewable_membership_requests_for_user(request.user)
        .values("organization__name", "organization__slug")
        .annotate(pending_count=Count("id"))
        .order_by("organization__name")
    )
    pending_review_count = sum(item["pending_count"] for item in pending_by_organization)
    context = _platform_identity_context(request)
    context.update(
        {
            "form": form,
            "profile_person": person,
            "profile_modal_open": modal_open,
            "pending_by_organization": pending_by_organization,
            "platform_pending_review_count": pending_review_count,
        }
    )
    return render(
        request,
        "core/profile.html",
        context,
    )


@login_required
def organizations(request):
    person = _profile_required(request)
    if person is None:
        return redirect("profile")
    query = str(request.GET.get("q") or "").strip()
    organization_query = Organization.objects.filter(is_active=True).select_related("created_by")
    if query:
        organization_query = organization_query.filter(
            Q(name__icontains=query) | Q(slug__icontains=query)
        )
    organization_list = list(organization_query.order_by("name")[:100])
    memberships = {
        item.organization_id: item
        for item in Membership.objects.filter(person=person)
        .filter(current_membership_filter())
        .prefetch_related("roles")
    }
    pending_requests = {
        item.organization_id: item
        for item in OrganizationMembershipRequest.objects.filter(
            person=person,
            status=OrganizationMembershipRequest.Status.PENDING,
        ).prefetch_related("requested_roles")
    }
    for organization in organization_list:
        organization.viewer_membership = memberships.get(organization.pk)
        organization.viewer_request = pending_requests.get(organization.pk)
    return render(
        request,
        "core/organizations.html",
        {
            "organizations": organization_list,
            "organization_query": query,
            "active_memberships": list(memberships.values()),
            "pending_requests": list(pending_requests.values()),
        },
    )


@login_required
def organization_create(request):
    if _profile_required(request) is None:
        return redirect("profile")
    form = OrganizationCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            organization = create_organization_for_user(user=request.user, **form.cleaned_data)
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(request, "L'organització s'ha creat i en constes com a responsable.")
            return redirect("organization_detail", slug=organization.slug)
    return render(request, "core/organization_form.html", {"form": form, "mode": "create"})


@login_required
def organization_detail(request, slug):
    person = _profile_required(request)
    if person is None:
        return redirect("profile")
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    membership = (
        Membership.objects.filter(person=person, organization=organization)
        .filter(current_membership_filter())
        .prefetch_related("roles", "permission_overrides")
        .first()
    )
    pending_request = (
        OrganizationMembershipRequest.objects.filter(
            person=person,
            organization=organization,
            status=OrganizationMembershipRequest.Status.PENDING,
        )
        .prefetch_related("requested_roles")
        .first()
    )
    can_review = has_organization_permission(
        request.user,
        organization,
        MembershipPermission.Permission.REVIEW_REQUESTS,
    )
    can_manage_roles = has_organization_permission(
        request.user,
        organization,
        MembershipPermission.Permission.MANAGE_ROLES,
    )
    members = []
    if membership is not None:
        members = list(
            Membership.objects.filter(organization=organization)
            .filter(current_membership_filter())
            .select_related("person")
            .prefetch_related("roles", "permission_overrides")
            .order_by("person__last_name", "person__first_name")
        )
    pending_for_review = []
    if can_review:
        pending_for_review = list(
            organization.membership_requests.filter(
                status=OrganizationMembershipRequest.Status.PENDING
            )
            .select_related("person")
            .prefetch_related("requested_roles")
        )
    return render(
        request,
        "core/organization_detail.html",
        {
            "organization": organization,
            "membership": membership,
            "pending_request": pending_request,
            "join_form": OrganizationJoinRequestForm(),
            "members": members,
            "pending_for_review": pending_for_review,
            "can_review_requests": can_review,
            "can_manage_roles": can_manage_roles,
            "can_manage_organization": can_manage_organization(request.user, organization),
        },
    )


@login_required
def organization_edit(request, slug):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not can_manage_organization(request.user, organization):
        raise PermissionDenied("No pots editar aquesta organització.")
    form = OrganizationEditForm(
        request.POST if request.method == "POST" else None,
        instance=organization,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Les dades de l'organització s'han actualitzat.")
        return redirect("organization_detail", slug=organization.slug)
    return render(
        request,
        "core/organization_form.html",
        {"form": form, "mode": "edit", "organization": organization},
    )


@login_required
@require_POST
def organization_join(request, slug):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    form = OrganizationJoinRequestForm(request.POST)
    if form.is_valid():
        try:
            request_organization_membership(
                user=request.user,
                organization=organization,
                roles=form.cleaned_data["roles"],
                message=form.cleaned_data["message"],
            )
        except ValidationError as error:
            for message in error.messages:
                messages.error(request, message)
        else:
            messages.success(request, "La sol·licitud s'ha enviat als administradors.")
    else:
        messages.error(request, "Revisa els rols sol·licitats.")
    return redirect("organization_detail", slug=organization.slug)


@login_required
@require_POST
def organization_request_cancel(request, pk):
    membership_request = get_object_or_404(OrganizationMembershipRequest, pk=pk)
    organization_slug = membership_request.organization.slug
    try:
        cancel_organization_membership_request(
            user=request.user,
            membership_request=membership_request,
        )
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
    else:
        messages.success(request, "La sol·licitud s'ha cancel·lat.")
    return redirect("organization_detail", slug=organization_slug)


@login_required
@require_POST
def organization_request_review(request, pk, decision):
    membership_request = get_object_or_404(OrganizationMembershipRequest, pk=pk)
    if decision not in {"approve", "reject"}:
        raise PermissionDenied("Decisió no vàlida.")
    try:
        review_organization_membership_request(
            user=request.user,
            membership_request=membership_request,
            approve=decision == "approve",
        )
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
    else:
        action = "aprovat" if decision == "approve" else "rebutjat"
        messages.success(request, f"S'ha {action} la sol·licitud.")
    return redirect("organization_detail", slug=membership_request.organization.slug)


@login_required
def organization_member_access(request, slug, pk):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    membership = get_object_or_404(
        Membership.objects.select_related("person", "organization").prefetch_related(
            "roles", "permission_overrides"
        ),
        pk=pk,
        organization=organization,
    )
    if not has_organization_permission(
        request.user,
        organization,
        MembershipPermission.Permission.MANAGE_ROLES,
    ):
        raise PermissionDenied("No pots gestionar aquest membre.")
    form = MembershipAccessForm(
        request.POST if request.method == "POST" else None,
        membership=membership,
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_membership_access(
                user=request.user,
                membership=membership,
                roles=form.cleaned_data["roles"],
                permissions=form.cleaned_data["permissions"],
            )
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(request, "Els rols i permisos del membre s'han actualitzat.")
            return redirect("organization_detail", slug=organization.slug)
    return render(
        request,
        "core/organization_member_access.html",
        {"organization": organization, "membership": membership, "form": form},
    )

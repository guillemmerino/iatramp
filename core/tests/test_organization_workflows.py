from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    OrganizationMembershipRequest,
    Person,
)
from core.services import (
    can_manage_organization,
    create_organization_for_user,
    grant_membership,
    has_organization_permission,
    request_organization_membership,
    review_organization_membership_request,
    update_membership_access,
)


def complete_person(user, first_name, last_name):
    person = user.person
    person.first_name = first_name
    person.last_name = last_name
    person.is_provisional = False
    person.save()
    return person


class OrganizationDomainTests(TestCase):
    def setUp(self):
        self.owner_user = get_user_model().objects.create_user(username="owner")
        self.owner = complete_person(self.owner_user, "Olga", "Responsable")
        self.organization = create_organization_for_user(
            user=self.owner_user,
            name="Club Delta",
        )

    def make_person(self, username):
        user = get_user_model().objects.create_user(username=username)
        person = complete_person(user, username.title(), "Prova")
        return user, person

    def test_creator_is_traced_and_gets_owner_role(self):
        membership = Membership.objects.get(
            person=self.owner,
            organization=self.organization,
        )

        self.assertEqual(self.organization.created_by, self.owner)
        self.assertTrue(
            membership.roles.filter(role=MembershipRole.Role.OWNER, is_active=True).exists()
        )
        self.assertTrue(can_manage_organization(self.owner_user, self.organization))

    def test_organization_supports_multiple_admins_and_multiple_roles(self):
        first_user, first = self.make_person("admin-one")
        second_user, second = self.make_person("admin-two")
        first_membership = grant_membership(
            person=first,
            organization=self.organization,
            role=MembershipRole.Role.ADMIN,
            approved_by=self.owner,
        )
        first_membership.roles.create(role=MembershipRole.Role.COACH, granted_by=self.owner)
        grant_membership(
            person=second,
            organization=self.organization,
            role=MembershipRole.Role.ADMIN,
            approved_by=self.owner,
        )

        self.assertEqual(
            MembershipRole.objects.filter(
                membership__organization=self.organization,
                role=MembershipRole.Role.ADMIN,
                is_active=True,
            ).count(),
            2,
        )
        self.assertEqual(first_membership.roles.filter(is_active=True).count(), 2)
        self.assertTrue(can_manage_organization(first_user, self.organization))
        self.assertTrue(can_manage_organization(second_user, self.organization))

    def test_permissions_can_override_admin_defaults_per_member(self):
        admin_user, admin = self.make_person("limited-admin")
        membership = grant_membership(
            person=admin,
            organization=self.organization,
            role=MembershipRole.Role.ADMIN,
            approved_by=self.owner,
        )

        update_membership_access(
            user=self.owner_user,
            membership=membership,
            roles=[MembershipRole.Role.ADMIN],
            permissions=[MembershipPermission.Permission.REVIEW_REQUESTS],
        )

        self.assertFalse(can_manage_organization(admin_user, self.organization))
        self.assertTrue(
            has_organization_permission(
                admin_user,
                self.organization,
                MembershipPermission.Permission.REVIEW_REQUESTS,
            )
        )

    def test_request_does_not_grant_access_until_an_admin_approves_it(self):
        admin_user, admin = self.make_person("admin")
        grant_membership(
            person=admin,
            organization=self.organization,
            role=MembershipRole.Role.ADMIN,
            approved_by=self.owner,
        )
        applicant_user, applicant = self.make_person("applicant")
        membership_request = request_organization_membership(
            user=applicant_user,
            organization=self.organization,
            roles=[MembershipRole.Role.COACH, MembershipRole.Role.ATHLETE],
            message="Vull incorporar-me al club.",
        )

        self.assertFalse(
            Membership.objects.filter(person=applicant, organization=self.organization).exists()
        )
        membership = review_organization_membership_request(
            user=admin_user,
            membership_request=membership_request,
            approve=True,
        )

        membership_request.refresh_from_db()
        self.assertEqual(
            membership_request.status,
            OrganizationMembershipRequest.Status.APPROVED,
        )
        self.assertSetEqual(
            set(membership.roles.filter(is_active=True).values_list("role", flat=True)),
            {MembershipRole.Role.COACH, MembershipRole.Role.ATHLETE},
        )

    def test_regular_member_cannot_review_requests(self):
        member_user, member = self.make_person("member")
        grant_membership(
            person=member,
            organization=self.organization,
            role=MembershipRole.Role.MEMBER,
            approved_by=self.owner,
        )
        applicant_user, _ = self.make_person("candidate")
        membership_request = request_organization_membership(
            user=applicant_user,
            organization=self.organization,
            roles=[MembershipRole.Role.MEMBER],
        )

        with self.assertRaises(PermissionDenied):
            review_organization_membership_request(
                user=member_user,
                membership_request=membership_request,
                approve=True,
            )

    def test_last_owner_role_cannot_be_removed(self):
        membership = Membership.objects.get(
            person=self.owner,
            organization=self.organization,
        )

        with self.assertRaises(ValidationError):
            update_membership_access(
                user=self.owner_user,
                membership=membership,
                roles=[MembershipRole.Role.ADMIN],
                permissions=MembershipPermission.Permission.values,
            )


class OrganizationUiTests(TestCase):
    def test_profile_onboarding_creates_person_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username="aina")
        self.client.force_login(user)

        response = self.client.post(
            reverse("profile"),
            {
                "first_name": "Aina",
                "last_name": "Serra",
                "preferred_name": "Aina S.",
                "birth_date": "",
                "email": "aina@example.com",
                "phone": "",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(Person.objects.get(user=user).display_name, "Aina S.")

    def test_user_can_create_organization_and_becomes_owner(self):
        user = get_user_model().objects.create_user(username="creator")
        person = complete_person(user, "Crea", "Dora")
        self.client.force_login(user)

        response = self.client.post(
            reverse("organization_create"),
            {"name": "Club Aurora", "kind": "club"},
        )

        organization = person.created_organizations.get(name="Club Aurora")
        self.assertRedirects(
            response,
            reverse("organization_detail", kwargs={"slug": organization.slug}),
        )
        self.assertTrue(
            organization.memberships.get(person=person).roles.filter(
                role=MembershipRole.Role.OWNER,
                is_active=True,
            ).exists()
        )

    def test_join_and_approval_flow_is_available_through_ui(self):
        owner_user = get_user_model().objects.create_user(username="owner-ui")
        owner = complete_person(owner_user, "Oriol", "Roca")
        organization = create_organization_for_user(user=owner_user, name="Club UI")
        applicant_user = get_user_model().objects.create_user(username="applicant-ui")
        applicant = complete_person(applicant_user, "Anna", "Sol")
        self.client.force_login(applicant_user)

        response = self.client.post(
            reverse("organization_join", kwargs={"slug": organization.slug}),
            {"roles": [MembershipRole.Role.COACH], "message": "Hola"},
        )

        self.assertRedirects(
            response,
            reverse("organization_detail", kwargs={"slug": organization.slug}),
        )
        membership_request = applicant.organization_membership_requests.get()
        self.client.force_login(owner_user)
        response = self.client.post(
            reverse(
                "organization_request_review",
                kwargs={"pk": membership_request.pk, "decision": "approve"},
            )
        )

        self.assertRedirects(
            response,
            reverse("organization_detail", kwargs={"slug": organization.slug}),
        )
        self.assertTrue(
            organization.memberships.get(person=applicant).roles.filter(
                role=MembershipRole.Role.COACH,
                is_active=True,
            ).exists()
        )

    def test_owner_can_assign_multiple_roles_and_custom_permissions_through_ui(self):
        owner_user = get_user_model().objects.create_user(username="access-owner")
        owner = complete_person(owner_user, "Ona", "Owner")
        organization = create_organization_for_user(user=owner_user, name="Club Accessos")
        member_user = get_user_model().objects.create_user(username="access-member")
        member = complete_person(member_user, "Marta", "Membre")
        membership = grant_membership(
            person=member,
            organization=organization,
            role=MembershipRole.Role.MEMBER,
            approved_by=owner,
        )
        self.client.force_login(owner_user)

        response = self.client.post(
            reverse(
                "organization_member_access",
                kwargs={"slug": organization.slug, "pk": membership.pk},
            ),
            {
                "roles": [MembershipRole.Role.ADMIN, MembershipRole.Role.COACH],
                "permissions": [MembershipPermission.Permission.REVIEW_REQUESTS],
            },
        )

        self.assertRedirects(
            response,
            reverse("organization_detail", kwargs={"slug": organization.slug}),
        )
        self.assertSetEqual(
            set(membership.roles.filter(is_active=True).values_list("role", flat=True)),
            {MembershipRole.Role.ADMIN, MembershipRole.Role.COACH},
        )
        self.assertTrue(
            has_organization_permission(
                member_user,
                organization,
                MembershipPermission.Permission.REVIEW_REQUESTS,
            )
        )
        self.assertFalse(can_manage_organization(member_user, organization))

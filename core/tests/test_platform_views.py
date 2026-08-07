from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import resolve, reverse

from core.models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    Person,
)


def complete_person(user, first_name, last_name, preferred_name=""):
    person = user.person
    person.first_name = first_name
    person.last_name = last_name
    person.preferred_name = preferred_name
    person.is_provisional = False
    person.save()
    return person


class PlatformHomeTests(TestCase):
    def test_root_is_public_platform_home(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolve("/").url_name, "home")
        self.assertContains(response, "Iatramp")
        self.assertContains(response, "Què vols fer avui?")
        self.assertNotContains(response, "http-equiv=\"refresh\"")

    def test_home_links_to_existing_competitions_and_profile(self):
        response = self.client.get(reverse("home"))

        competitions_url = reverse("competicions_home")
        profile_url = reverse("profile")
        self.assertContains(response, f'href="{competitions_url}"')
        self.assertContains(response, f'href="{profile_url}"')
        self.assertEqual(resolve(competitions_url).url_name, "competicions_home")

    def test_home_uses_the_platform_avatar_as_decorative_hero_art(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'class="platform-hero-assistant" aria-hidden="true"')
        self.assertContains(response, "core/avatar/assistant-card.webp")
        self.assertContains(response, '<img src="/static/core/avatar/assistant-card.webp', html=False)
        self.assertContains(response, 'alt=""')
        self.assertIsNotNone(finders.find("core/avatar/assistant-card.webp"))

    def test_iatrain_is_available_and_future_modules_do_not_expose_broken_links(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'data-module-status="preparation"', count=2)
        self.assertContains(response, "IA Train")
        self.assertContains(response, 'href="{}"'.format(reverse("iatrain_home")))
        self.assertContains(response, "MVP disponible")
        self.assertContains(response, "Portal de jutges")
        self.assertContains(response, "El meu perfil")
        self.assertContains(response, "En preparació")

    def test_notes_and_judges_use_the_verified_golden_theme_contract(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "platform-feature-item--notes")
        self.assertContains(response, "platform-module-card--judges")
        css_path = finders.find("core/platform.css")
        self.assertIsNotNone(css_path)
        css = Path(css_path).read_text(encoding="utf-8")
        expected_tokens = {
            "--platform-notes: #a16207",
            "--platform-notes-hover: #854d0e",
            "--platform-notes-soft: #fffbeb",
            "--platform-notes-border: #fde68a",
            "--platform-notes-text: #78350f",
            "--platform-notes-secondary: #d97706",
        }
        for token in expected_tokens:
            self.assertIn(token, css)
        self.assertIn(".platform-module-card--judges:hover", css)
        self.assertIn("border-color: var(--platform-notes-hover)", css)
        self.assertIn("border-top-color: var(--platform-notes)", css)
        self.assertIn(".platform-settings-notice", css)
        navigation_css_path = finders.find("core/platform_navigation.css")
        self.assertIsNotNone(navigation_css_path)
        navigation_css = Path(navigation_css_path).read_text(encoding="utf-8")
        for token in {
            "--platform-nav-gold: #a16207",
            "--platform-nav-gold-hover: #854d0e",
            "--platform-nav-gold-soft: #fffbeb",
            "--platform-nav-gold-border: #fde68a",
            "--platform-nav-gold-text: #78350f",
            "--platform-nav-gold-secondary: #d97706",
        }:
            self.assertIn(token, navigation_css)
        self.assertIn(".platform-nav-item--judges", navigation_css)
        self.assertIn("background: var(--platform-nav-surface)", navigation_css)

    def test_global_platform_navigation_replaces_the_top_bar(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "data-platform-navigation")
        self.assertContains(response, 'aria-label="Obrir la navegació d’Iatramp"')
        self.assertContains(response, 'id="platform-nav-panel"')
        self.assertContains(response, 'class="platform-nav-item platform-nav-item--home is-active"')
        self.assertContains(response, 'href="{}"'.format(reverse("competicions_home")))
        self.assertContains(response, 'href="{}"'.format(reverse("profile")))
        self.assertContains(response, 'href="{}"'.format(reverse("iatrain_home")))
        self.assertContains(response, "platform-nav-item--judges is-disabled")
        self.assertNotContains(response, "platform-nav-item--profile")
        self.assertNotContains(response, '<a class="platform-nav-item platform-nav-item--judges')
        self.assertNotContains(response, '<a class="platform-nav-item platform-nav-item--profile')
        self.assertNotContains(response, 'class="header_section"')
        self.assertNotContains(response, 'id="navbarSupportedContent"')

    def test_navigation_marks_profile_as_the_active_platform_context(self):
        user = get_user_model().objects.create_user(username="profile-navigation")
        complete_person(user, "Nora", "Perfil")
        self.client.force_login(user)
        response = self.client.get(reverse("profile"))

        self.assertContains(
            response,
            'class="platform-nav-item platform-nav-item--profile is-active"',
        )
        self.assertContains(response, 'aria-current="page"')

    def test_navigation_assets_include_accessible_drawer_behaviour(self):
        css_path = finders.find("core/platform_navigation.css")
        js_path = finders.find("core/platform_navigation.js")

        self.assertIsNotNone(css_path)
        self.assertIsNotNone(js_path)
        css = Path(css_path).read_text(encoding="utf-8")
        javascript = Path(js_path).read_text(encoding="utf-8")
        self.assertIn("border-radius: 0 999px 999px 0", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("body.competicions-app .platform-nav-rail", css)
        self.assertIn("has-integrated-avatar-assistant", css)
        self.assertIn("body.has-competition-dock .platform-nav-trigger", css)
        self.assertIn('event.key === "Escape"', javascript)
        self.assertIn('event.key !== "Tab"', javascript)
        self.assertIn('panel.setAttribute("inert", "")', javascript)
        self.assertIn('panel.addEventListener("transitionend", focusPanelClose', javascript)
        self.assertIn('navigation.querySelector("[data-platform-avatar-open]")', javascript)
        self.assertIn('document.querySelector(".avatar-helper")', javascript)
        self.assertIn("new MutationObserver(syncAssistantState)", javascript)
        self.assertIn('helperOpenButton.click()', javascript)

    def test_competitions_keep_the_internal_dock_below_platform_navigation(self):
        user = get_user_model().objects.create_superuser(
            username="platform-admin",
            email="admin@example.com",
            password="unused",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("competicions_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-platform-navigation")
        self.assertContains(response, "competition-dock-wrap")
        self.assertContains(response, "data-platform-avatar-open")
        self.assertContains(response, 'aria-label="Obrir l’assistent contextual de Competicions"')
        self.assertContains(response, "core/avatar/controls/avatar_in.png")
        self.assertContains(response, "hidden")
        self.assertContains(
            response,
            'class="platform-nav-item platform-nav-item--competitions is-active"',
        )

    def test_authenticated_user_gets_coherent_provisional_profile(self):
        user = get_user_model().objects.create_user(username="guillem")
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "guillem")
        self.assertTrue(user.person.is_provisional)
        self.assertContains(response, "El perfil personal està pendent de completar")
        self.assertContains(response, "Encara no hi ha organitzacions vinculades")

    def test_linked_person_and_membership_appear_on_home(self):
        user = get_user_model().objects.create_user(username="aina")
        person = complete_person(user, "Aina", "Serra", "Aina S.")
        organization = Organization.objects.create(name="Club Trampolí", slug="club-trampoli")
        Membership.objects.create(
            person=person,
            organization=organization,
        ).roles.create(
            role=MembershipRole.Role.ATHLETE,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Aina S.")
        self.assertContains(response, "Identitat Iatramp connectada")
        self.assertContains(response, "1")
        self.assertContains(response, "vincle d’organització actiu")


class PlatformProfileTests(TestCase):
    def test_legacy_settings_redirects_to_profile(self):
        response = self.client.get(reverse("platform_settings"))

        self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)

    def test_profile_lists_current_membership_context(self):
        user = get_user_model().objects.create_user(username="coach")
        person = complete_person(user, "Joan", "Puig")
        organization = Organization.objects.create(
            name="Federació Catalana",
            slug="federacio-catalana",
            kind=Organization.Kind.FEDERATION,
        )
        membership = Membership.objects.create(
            person=person,
            organization=organization,
        )
        MembershipRole.objects.create(
            membership=membership,
            role=MembershipRole.Role.COACH,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Joan Puig")
        self.assertContains(response, "Federació Catalana")
        self.assertContains(response, "Entrenador/a")
        self.assertContains(response, "Connectat")
        self.assertContains(response, "data-profile-dialog")

    def test_profile_editor_opens_for_onboarding_and_query_parameter(self):
        user = get_user_model().objects.create_user(username="onboarding")
        self.client.force_login(user)

        response = self.client.get(reverse("profile"))
        self.assertContains(response, "data-open-on-load")

        complete_person(user, "Ona", "Board")
        response = self.client.get(f'{reverse("profile")}?editar=1')
        self.assertContains(response, "data-open-on-load")

    def test_owner_sees_pending_review_notification_in_navigation_and_profile(self):
        owner_user = get_user_model().objects.create_user(username="owner-alert")
        owner = complete_person(owner_user, "Olga", "Alert")
        organization = Organization.objects.create(name="Club Alert", slug="club-alert")
        owner_membership = Membership.objects.create(person=owner, organization=organization)
        MembershipRole.objects.create(
            membership=owner_membership,
            role=MembershipRole.Role.OWNER,
        )
        candidate_user = get_user_model().objects.create_user(username="candidate-alert")
        candidate = complete_person(candidate_user, "Candi", "Data")
        OrganizationMembershipRequest.objects.create(
            person=candidate,
            organization=organization,
        )
        self.client.force_login(owner_user)

        response = self.client.get(reverse("profile"))

        self.assertContains(response, 'class="platform-nav-trigger-alert"')
        self.assertContains(response, "1 sol·licitud pendent de revisar")
        self.assertContains(response, "Club Alert")
        self.assertContains(
            response,
            f'{reverse("organization_detail", kwargs={"slug": organization.slug})}#sollicituds-pendents',
        )

    def test_denied_admin_does_not_see_pending_review_notification(self):
        admin_user = get_user_model().objects.create_user(username="admin-denied-alert")
        admin = complete_person(admin_user, "Ada", "Min")
        organization = Organization.objects.create(name="Club Privat", slug="club-privat")
        membership = Membership.objects.create(person=admin, organization=organization)
        MembershipRole.objects.create(membership=membership, role=MembershipRole.Role.ADMIN)
        MembershipPermission.objects.create(
            membership=membership,
            permission=MembershipPermission.Permission.REVIEW_REQUESTS,
            is_allowed=False,
        )
        candidate = Person.objects.create(first_name="Pere", last_name="Pendent")
        OrganizationMembershipRequest.objects.create(person=candidate, organization=organization)
        self.client.force_login(admin_user)

        response = self.client.get(reverse("profile"))

        self.assertNotContains(response, "platform-nav-trigger-alert")
        self.assertNotContains(response, "Acció necessària")

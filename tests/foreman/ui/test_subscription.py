"""Test module for Subscriptions/Manifests UI

:Requirement: Subscription

:CaseAutomation: Automated

:CaseComponent: SubscriptionManagement

:team: Phoenix-subscriptions

:CaseImportance: High

"""
from tempfile import mkstemp
import time

from fauxfactory import gen_string
import pytest

from robottelo.config import settings
from robottelo.constants import (
    DEFAULT_SUBSCRIPTION_NAME,
    PRDS,
    REPOS,
    REPOSET,
    VDC_SUBSCRIPTION_NAME,
    VIRT_WHO_HYPERVISOR_TYPES,
)
from robottelo.utils.manifest import clone

pytestmark = [pytest.mark.run_in_one_thread, pytest.mark.skip_if_not_set('fake_manifest')]


@pytest.fixture(scope='module')
def golden_ticket_host_setup(function_entitlement_manifest_org, module_target_sat):
    org = function_entitlement_manifest_org
    rh_repo_id = module_target_sat.api_factory.enable_rhrepo_and_fetchid(
        basearch='x86_64',
        org_id=org.id,
        product=PRDS['rhel'],
        repo=REPOS['rhst7']['name'],
        reposet=REPOSET['rhst7'],
        releasever=None,
    )
    rh_repo = module_target_sat.api.Repository(id=rh_repo_id).read()
    rh_repo.sync()
    custom_product = module_target_sat.api.Product(organization=org).create()
    custom_repo = module_target_sat.api.Repository(
        name=gen_string('alphanumeric').upper(), product=custom_product
    ).create()
    custom_repo.sync()
    ak = module_target_sat.api.ActivationKey(
        content_view=org.default_content_view,
        max_hosts=100,
        organization=org,
        environment=module_target_sat.api.LifecycleEnvironment(id=org.library.id),
        auto_attach=True,
    ).create()
    return org, ak


@pytest.mark.e2e
@pytest.mark.tier2
@pytest.mark.upgrade
def test_positive_end_to_end(session, target_sat):
    """Upload a manifest with minimal input parameters, attempt to
    delete it with checking the warning message and hit 'Cancel' button after than delete it.

    :id: 580fc072-01e0-4f83-8cbb-2a8522d76243

    :expectedresults:
        1. The manifest was uploaded successfully.
        2. Manifest import is reflected at the dashboard
        3. When attempting to delete the manifest the confirmation dialog contains informative
            message which warns user about downsides and consequences of manifest deletion.
        4. When hitting cancel the manifest was not deleted.
        5. When deleting and confirming deletion, the manifest was deleted successfully.
        6. When reimporting manifest, the manifest is reimported successfully and the candlepin log
            shows no error.

    :BZ: 1266827, 2066899, 2076684

    :SubComponent: Candlepin

    :customerscenario: true

    :CaseImportance: Critical
    """
    expected_message_lines = [
        'Are you sure you want to delete the manifest?',
        'Note: Deleting a subscription manifest is STRONGLY discouraged.',
        'This action should only be taken for debugging purposes.',
    ]
    org = target_sat.api.Organization().create()
    _, temporary_local_manifest_path = mkstemp(prefix='manifest-', suffix='.zip')
    with clone() as manifest:
        with open(temporary_local_manifest_path, 'wb') as file_handler:
            file_handler.write(manifest.content.read())
    with session:
        session.organization.select(org.name)
        # Ignore "Danger alert: Katello::Errors::UpstreamConsumerNotFound'" as server will connect
        # to upstream subscription service to verify
        # the consumer uuid, that will be displayed in flash error messages
        # Note: this happen only when using clone manifest.
        session.subscription.add_manifest(
            temporary_local_manifest_path,
            ignore_error_messages=['Danger alert: Katello::Errors::UpstreamConsumerNotFound'],
        )
        assert session.subscription.has_manifest
        subscriptions = session.subscription.read_subscriptions()
        assert len(subscriptions) >= 1
        assert any('Red Hat' in subscription['Name'] for subscription in subscriptions)
        assert int(subscriptions[0]['Entitlements']) > 0
        assert int(subscriptions[0]['Consumed']) >= 0
        # manifest delete testing
        delete_message = session.subscription.read_delete_manifest_message()
        assert ' '.join(expected_message_lines) == delete_message
        assert session.subscription.has_manifest
        session.subscription.delete_manifest(
            ignore_error_messages=['Danger alert: Katello::Errors::UpstreamConsumerNotFound']
        )
        assert not session.subscription.has_manifest
        # reimport manifest
        session.subscription.add_manifest(
            temporary_local_manifest_path,
            ignore_error_messages=['Danger alert: Katello::Errors::UpstreamConsumerNotFound'],
        )
        assert session.subscription.has_manifest
        results = target_sat.execute(
            'grep -E "NullPointerException|CandlepinError" /var/log/candlepin/candlepin.log'
        )
        assert results.stdout == ''


@pytest.mark.tier2
def test_positive_access_with_non_admin_user_without_manifest(test_name, target_sat):
    """Access subscription page with non admin user that has the necessary
    permissions to check that there is no manifest uploaded.

    :id: dab9dc15-39a8-4105-b7ff-ecef909dc6e6

    :expectedresults: Subscription page is rendered properly without errors

    :BZ: 1417082

    :CaseImportance: Critical
    """
    org = target_sat.api.Organization().create()
    role = target_sat.api.Role(organization=[org]).create()
    target_sat.api_factory.create_role_permissions(
        role,
        {
            'Katello::Subscription': [
                'view_subscriptions',
                'manage_subscription_allocations',
                'import_manifest',
                'delete_manifest',
            ],
            'Organization': ['view_organizations', 'edit_organizations'],
        },
    )
    user_password = gen_string('alphanumeric')
    user = target_sat.api.User(
        admin=False,
        role=[role],
        password=user_password,
        organization=[org],
        default_organization=org,
    ).create()
    with target_sat.ui_session(test_name, user=user.login, password=user_password) as session:
        assert not session.subscription.has_manifest


@pytest.mark.tier2
@pytest.mark.upgrade
def test_positive_access_with_non_admin_user_with_manifest(
    test_name, function_entitlement_manifest_org, target_sat
):
    """Access subscription page with user that has only view_subscriptions and view organizations
    permission and organization that has a manifest uploaded.

    :id: 9184fcf6-36be-42c8-984c-3c5d7834b3b4

    :expectedresults: Subscription page is rendered properly without errors
        and the default subscription is visible

    :BZ: 1417082, 1651981

    :customerscenario: true

    :CaseImportance: Critical
    """
    org = function_entitlement_manifest_org
    role = target_sat.api.Role(organization=[org]).create()
    target_sat.api_factory.create_role_permissions(
        role,
        {'Katello::Subscription': ['view_subscriptions'], 'Organization': ['view_organizations']},
    )
    user_password = gen_string('alphanumeric')
    user = target_sat.api.User(
        admin=False,
        role=[role],
        password=user_password,
        organization=[org],
        default_organization=org,
    ).create()
    with target_sat.ui_session(test_name, user=user.login, password=user_password) as session:
        assert (
            session.subscription.search(f'name = "{DEFAULT_SUBSCRIPTION_NAME}"')[0]['Name']
            == DEFAULT_SUBSCRIPTION_NAME
        )


@pytest.mark.tier2
def test_positive_access_manifest_as_another_admin_user(
    test_name, target_sat, function_entitlement_manifest
):
    """Other admin users should be able to access and manage a manifest
    uploaded by a different admin.

    :id: 02e319da-3b7a-4694-9164-475c2c71b9a8

    :expectedresults: Other admin user should see/manage the manifest

    :BZ: 1669241

    :customerscenario: true

    :CaseImportance: High
    """
    org = target_sat.api.Organization().create()
    user1_password = gen_string('alphanumeric')
    user1 = target_sat.api.User(
        admin=True, password=user1_password, organization=[org], default_organization=org
    ).create()
    user2_password = gen_string('alphanumeric')
    user2 = target_sat.api.User(
        admin=True, password=user2_password, organization=[org], default_organization=org
    ).create()
    # use the first admin to upload a manifest
    with target_sat.ui_session(test_name, user=user1.login, password=user1_password) as session:
        target_sat.upload_manifest(org.id, function_entitlement_manifest.content)
        assert session.subscription.has_manifest
        # store subscriptions that have "Red Hat" in the name for later
        rh_subs = session.subscription.search("Red Hat")
    # try to view and delete the manifest with another admin
    with target_sat.ui_session(test_name, user=user2.login, password=user2_password) as session:
        assert session.subscription.has_manifest
        assert rh_subs == session.subscription.search("Red Hat")
        session.subscription.delete_manifest(
            ignore_error_messages=['Danger alert: Katello::Errors::UpstreamConsumerNotFound']
        )
        assert not session.subscription.has_manifest


@pytest.mark.tier3
def test_positive_view_vdc_subscription_products(
    session, rhel7_contenthost, target_sat, function_entitlement_manifest_org
):
    """Ensure that Virtual Datacenters subscription provided products is
    not empty and that a consumed product exist in content products.

    :id: cc4593f0-66ab-4bf6-87d1-d4bd9c89eba5

    :customerscenario: true

    :steps:
        1. Upload a manifest with Virtual Datacenters subscription
        2. Enable a products provided by Virtual Datacenters subscription,
           and synchronize the auto created repository
        3. Create content view with the product repository, and publish it
        4. Create a lifecycle environment and promote the content view to
           it.
        5. Create an activation key with the content view and lifecycle
           environment
        6. Subscribe a host to the activation key
        7. Goto Hosts -> Content hosts and select the created content host
        8. Attach VDC subscription to content host
        9. Goto Content -> Red Hat Subscription
        10. Select Virtual Datacenters subscription

    :expectedresults:
        1. assert that the provided products is not empty
        2. assert that the enabled product is in subscription Product Content

    :BZ: 1366327

    :parametrized: yes
    """
    org = function_entitlement_manifest_org
    lce = target_sat.api.LifecycleEnvironment(organization=org).create()
    repos_collection = target_sat.cli_factory.RepositoryCollection(
        distro='rhel7',
        repositories=[target_sat.cli_factory.RHELAnsibleEngineRepository(cdn=True)],
    )
    product_name = repos_collection.rh_repos[0].data['product']
    repos_collection.setup_content(org.id, lce.id, rh_subscriptions=[DEFAULT_SUBSCRIPTION_NAME])
    rhel7_contenthost.contenthost_setup(
        target_sat,
        org.label,
        activation_key=repos_collection.setup_content_data['activation_key']['name'],
    )
    with session:
        session.organization.select(org.name)
        session.contenthost.add_subscription(rhel7_contenthost.hostname, VDC_SUBSCRIPTION_NAME)
        provided_products = session.subscription.provided_products(VDC_SUBSCRIPTION_NAME)
        # ensure that subscription provided products list is not empty and that the product is
        # in the provided products.
        assert product_name in provided_products
        content_products = session.subscription.content_products(VDC_SUBSCRIPTION_NAME)
        # ensure that subscription enabled products list is not empty and that product is in
        # content products.
        assert product_name in content_products


@pytest.mark.skip_if_not_set('libvirt')
@pytest.mark.tier3
def test_positive_view_vdc_guest_subscription_products(
    session, rhel7_contenthost, target_sat, function_entitlement_manifest_org
):
    """Ensure that Virtual Data Centers guest subscription Provided
    Products and Content Products are not empty.

    :id: 4a6f6933-8e26-4c47-b544-a300e11a8454

    :customerscenario: true

    :steps:
        1. Upload a manifest with Virtual Datacenters subscription
        2. Config a virtual machine virt-who service for a hypervisor
        3. Ensure virt-who hypervisor host exist
        4. Attach Virtual Datacenters subscription to the virt-who
           hypervisor
        5. Go to Content -> Red Hat Subscription
        6. Select Virtual Datacenters subscription with type Guests of
           virt-who hypervisor

    :expectedresults:
        1. The Virtual Data Centers guests subscription Provided Products
           is not empty and one of the provided products exist
        2. The Virtual Data Centers guests subscription Product Content is
           not empty and one of the consumed products exist

    :BZ: 1395788, 1506636, 1487317

    :parametrized: yes
    """
    org = function_entitlement_manifest_org
    lce = target_sat.api.LifecycleEnvironment(organization=org).create()
    provisioning_server = settings.libvirt.libvirt_hostname
    rh_product_repository = target_sat.cli_factory.RHELAnsibleEngineRepository(cdn=True)
    product_name = rh_product_repository.data['product']
    # Create a new virt-who config
    virt_who_config = target_sat.cli_factory.virt_who_config(
        {
            'organization-id': org.id,
            'hypervisor-type': VIRT_WHO_HYPERVISOR_TYPES['libvirt'],
            'hypervisor-server': f'qemu+ssh://{provisioning_server}/system',
            'hypervisor-username': 'root',
        }
    )
    # configure virtual machine and setup virt-who service
    virt_who_data = rhel7_contenthost.virt_who_hypervisor_config(
        target_sat,
        virt_who_config['general-information']['id'],
        org_id=org.id,
        lce_id=lce.id,
        hypervisor_hostname=provisioning_server,
        configure_ssh=True,
        subscription_name=VDC_SUBSCRIPTION_NAME,
        upload_manifest=False,
        extra_repos=[rh_product_repository.data],
    )
    virt_who_hypervisor_host = virt_who_data['virt_who_hypervisor_host']
    with session:
        session.organization.select(org.name)
        # ensure that VDS subscription is assigned to virt-who hypervisor
        content_hosts = session.contenthost.search(
            f'subscription_name = "{VDC_SUBSCRIPTION_NAME}" '
            f'and name = "{virt_who_hypervisor_host["name"]}"'
        )
        assert content_hosts
        assert content_hosts[0]['Name'] == virt_who_hypervisor_host['name']
        # ensure that hypervisor guests subscription provided products list is not empty and
        # that the product is in provided products.
        provided_products = session.subscription.provided_products(
            VDC_SUBSCRIPTION_NAME, virt_who=True
        )
        assert product_name in provided_products
        # ensure that hypervisor guests subscription content products list is not empty and
        # that product is in content products.
        content_products = session.subscription.content_products(
            VDC_SUBSCRIPTION_NAME, virt_who=True
        )
        assert product_name in content_products


@pytest.mark.tier3
def test_select_customizable_columns_uncheck_and_checks_all_checkboxes(
    session, function_org, function_entitlement_manifest
):
    """Ensures that no column headers from checkboxes show up in the table after
    unticking everything from selectable customizable column

    :id: 88e140c7-ab4b-4d85-85bd-d3eff12162d7

    :steps:
        1. Login and go to Content -> Subscription
        2. Click selectable customizable column icon next to search button
        3. Iterate through list of checkboxes
        4. Unchecks all ticked checkboxes
        5. Verify that the table header column is empty after filter
        6. Check all ticked checkboxes
        7. Verify that the table header column is the same as the Checkbox_dict

        Note: Table header will always contain 'Select all rows' header in html,
        but will not be displayed in UI

    :expectedresults:
        1. No column headers show up

    :CaseImportance: Medium
    """
    checkbox_dict = {
        'Name': False,
        'SKU': False,
        'Contract': False,
        'Start Date': False,
        'End Date': False,
        'Requires Virt-Who': False,
        'Type': False,
        'Consumed': False,
        'Entitlements': False,
    }
    org = function_org
    with session:
        session.organization.select(org.name)
        session.subscription.add_manifest(
            function_entitlement_manifest.path,
            ignore_error_messages=['Danger alert: Katello::Errors::UpstreamConsumerNotFound'],
        )
        headers = session.subscription.filter_columns(checkbox_dict)
        assert headers == ('Select all rows',)
        assert len(checkbox_dict) == 9
        time.sleep(3)
        checkbox_dict.update((k, True) for k in checkbox_dict)
        col = session.subscription.filter_columns(checkbox_dict)
        checkbox_dict.update({'Select all rows': ''})
        assert set(col) == set(checkbox_dict)


@pytest.mark.tier3
def test_positive_subscription_status_disabled_golden_ticket(
    session, golden_ticket_host_setup, rhel7_contenthost, target_sat
):
    """Verify that Content host Subscription status is set to 'Disabled'
     for a golden ticket manifest

    :id: 115595ef-929d-4c42-bf34-aadd1bd36a5f

    :expectedresults: subscription status is 'Disabled'

    :customerscenario: true

    :BZ: 1789924

    :parametrized: yes

    :CaseImportance: Medium
    """
    rhel7_contenthost.install_katello_ca(target_sat)
    org, ak = golden_ticket_host_setup
    rhel7_contenthost.register_contenthost(org.label, ak.name)
    assert rhel7_contenthost.subscribed
    with session:
        session.organization.select(org_name=org.name)
        host = session.contenthost.read(rhel7_contenthost.hostname, widget_names='details')[
            'details'
        ]['subscription_status']
        assert 'Simple Content Access' in host


@pytest.mark.tier2
def test_positive_candlepin_events_processed_by_STOMP(
    session, rhel7_contenthost, target_sat, function_entitlement_manifest_org
):
    """Verify that Candlepin events are being read and processed by
       attaching subscriptions, validating host subscriptions status,
       and viewing processed and failed Candlepin events

    :id: 9510fd1c-2efb-4132-8665-9a72273cd1af

    :steps:

        1. Register Content Host without subscriptions attached
        2. Verify subscriptions status is red "invalid"
        3. Import a Manifest
        4. Attach subs to content host
        5. Verify subscription status is green "valid"
        6. Check for processed and failed Candlepin events

    :expectedresults: Candlepin events are being read and processed
                      correctly without any failures

    :BZ: 1826515

    :parametrized: yes

    :CaseImportance: High
    """
    org = function_entitlement_manifest_org
    repo = target_sat.api.Repository(
        product=target_sat.api.Product(organization=org).create()
    ).create()
    repo.sync()
    ak = target_sat.api.ActivationKey(
        content_view=org.default_content_view,
        max_hosts=100,
        organization=org,
        environment=target_sat.api.LifecycleEnvironment(id=org.library.id),
    ).create()
    rhel7_contenthost.install_katello_ca(target_sat)
    rhel7_contenthost.register_contenthost(org.name, ak.name)
    with session:
        session.organization.select(org_name=org.name)
        host = session.contenthost.read(rhel7_contenthost.hostname, widget_names='details')[
            'details'
        ]
        assert 'Unentitled' in host['subscription_status']
        session.contenthost.add_subscription(rhel7_contenthost.hostname, DEFAULT_SUBSCRIPTION_NAME)
        session.browser.refresh()
        updated_sub_status = session.contenthost.read(
            rhel7_contenthost.hostname, widget_names='details'
        )['details']['subscription_status']
        assert 'Fully entitled' in updated_sub_status
        response = target_sat.api.Ping().search_json()['services']['candlepin_events']
        assert response['status'] == 'ok'
        assert '0 Failed' in response['message']


def test_positive_prepare_for_sca_only_subscription(target_sat, function_entitlement_manifest_org):
    """Verify that the Subcsription page notifies users that Simple Content Access
        will be required for all organizations in Satellite 6.16

    :id: cb6fdfdd-04ee-4acb-9460-c78556cef11e

    :expectedresults: The Subscription page notifies users that Simple Content Access will
        be required for all organizations in Satellite 6.16
    """
    with target_sat.ui_session() as session:
        session.organization.select(function_entitlement_manifest_org.name)
        sca_alert = session.subscription.sca_alert()
        assert (
            'This organization is not using Simple Content Access. Entitlement-based subscription '
            'management is deprecated and will be removed in Satellite 6.16.' in sca_alert
        )

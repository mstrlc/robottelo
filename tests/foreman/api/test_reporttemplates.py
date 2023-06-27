"""Unit tests for the ``report_templates`` paths.

:Requirement: Report templates

:CaseAutomation: Automated

:CaseLevel: Component

:CaseComponent: Reporting

:team: Phoenix-subscriptions

:TestType: Functional

:CaseImportance: High

:Upstream: No
"""
from datetime import datetime

import pytest
from broker import Broker
from fauxfactory import gen_string
from nailgun import entities
from requests import HTTPError
from wait_for import wait_for

from robottelo.config import settings
from robottelo.constants import DEFAULT_SUBSCRIPTION_NAME
from robottelo.constants import FAKE_1_CUSTOM_PACKAGE
from robottelo.constants import FAKE_1_CUSTOM_PACKAGE_NAME
from robottelo.constants import FAKE_2_CUSTOM_PACKAGE
from robottelo.constants import PRDS
from robottelo.constants import REPOS
from robottelo.constants import REPOSET
from robottelo.hosts import ContentHost
from robottelo.utils.datafactory import parametrized
from robottelo.utils.datafactory import valid_data_list
from robottelo.utils.issue_handlers import is_open


@pytest.fixture(scope='module')
def setup_content(module_entitlement_manifest_org, module_target_sat):
    org = module_entitlement_manifest_org
    rh_repo_id = module_target_sat.api_factory.enable_rhrepo_and_fetchid(
        basearch='x86_64',
        org_id=org.id,
        product=PRDS['rhel'],
        repo=REPOS['rhst7']['name'],
        reposet=REPOSET['rhst7'],
        releasever=None,
    )
    rh_repo = entities.Repository(id=rh_repo_id).read()
    rh_repo.sync()
    custom_repo = entities.Repository(
        product=entities.Product(organization=org).create(),
    ).create()
    custom_repo.sync()
    lce = entities.LifecycleEnvironment(organization=org).create()
    cv = entities.ContentView(
        organization=org,
        repository=[rh_repo_id, custom_repo.id],
    ).create()
    cv.publish()
    cvv = cv.read().version[0].read()
    cvv.promote(data={'environment_ids': lce.id, 'force': False})
    ak = entities.ActivationKey(
        content_view=cv, max_hosts=100, organization=org, environment=lce, auto_attach=True
    ).create()
    subscription = entities.Subscription(organization=org).search(
        query={'search': f'name="{DEFAULT_SUBSCRIPTION_NAME}"'}
    )[0]
    ak.add_subscriptions(data={'quantity': 1, 'subscription_id': subscription.id})
    return ak, org


# Tests for ``katello/api/v2/report_templates``.


@pytest.mark.tier1
@pytest.mark.parametrize('name', **parametrized(valid_data_list()))
def test_positive_CRUDL(name):
    """Create, Read, Update, Delete, List

    :id: a2a577db-144e-4761-a42e-e83885464786

    :parametrized: yes

    :setup: User with reporting access rights

    :steps:

        1. Create Report Template
        2. List Report Templates, verify it's there
        3. Read Report Template
        4. Update Report Template, read again
        5. Delete Report template, check it's not present

    :expectedresults: All operations succeed, no template present in the end

    :CaseImportance: Critical
    """
    # Create
    template1 = gen_string('alpha')
    rt = entities.ReportTemplate(name=name, template=template1).create()
    # List
    res = entities.ReportTemplate().search(query={'search': f'name="{name}"'})
    assert name in list(map(lambda x: x.name, res))
    # Read
    rt = entities.ReportTemplate(id=rt.id).read()
    assert name == rt.name
    assert template1 == rt.template
    # Update
    template2 = gen_string('alpha')
    entities.ReportTemplate(id=rt.id, template=template2).update(['template'])
    rt = entities.ReportTemplate(id=rt.id).read()
    assert template2 == rt.template
    # Delete
    entities.ReportTemplate(id=rt.id).delete()
    with pytest.raises(HTTPError):
        rt = entities.ReportTemplate(id=rt.id).read()


@pytest.mark.tier1
def test_positive_generate_report_nofilter():
    """Generate Host - Statuses report

    :id: a4b687db-144e-4761-a42e-e93887464986

    :setup: User with reporting access rights, some report template, at least two hosts

    :steps:

        1. POST /api/report_templates/:id/generate

    :expectedresults: Report is generated for all hosts visible to user

    :CaseImportance: Critical
    """
    host_name = gen_string('alpha').lower()
    entities.Host(name=host_name).create()
    rt = entities.ReportTemplate().search(query={'search': 'name="Host - Statuses"'})[0].read()
    res = rt.generate()
    for column_name in [
        'Name',
        'Global',
        'Addons',
        'Build',
        'Compliance',
        'Configuration',
        'Errata',
        'Execution',
        'Insights',
        'Inventory',
        'OVAL scan',
        'Role',
        'Service level',
        'Subscription',
        'System purpose',
        'Traces',
        'Usage',
    ]:
        assert column_name in res
    assert host_name in res


@pytest.mark.tier2
def test_positive_generate_report_filter():
    """Generate Host - Statuses report

    :id: a4b677cb-144e-4761-a42e-e93887464986

    :setup: User with reporting access rights, some report template, at least two hosts

    :steps:

        1. POST /api/report_templates/:id/generate ... # define input_values

    :expectedresults: Report is generated (only) for the host specified by the filter

    :CaseImportance: High
    """
    host1_name = gen_string('alpha').lower()
    host2_name = gen_string('alpha').lower()
    entities.Host(name=host1_name).create()
    entities.Host(name=host2_name).create()
    rt = entities.ReportTemplate().search(query={'search': 'name="Host - Statuses"'})[0].read()
    res = rt.generate(data={"input_values": {"hosts": host2_name}})
    for column_name in [
        'Name',
        'Global',
        'Addons',
        'Build',
        'Compliance',
        'Configuration',
        'Errata',
        'Execution',
        'Insights',
        'Inventory',
        'OVAL scan',
        'Role',
        'Service level',
        'Subscription',
        'System purpose',
        'Traces',
        'Usage',
    ]:
        assert column_name in res
    assert host1_name not in res
    assert host2_name in res


@pytest.mark.tier2
def test_positive_report_add_userinput():
    """Add user input to template, use it in template, generate template

    :id: a4a577db-144e-4761-a42e-e86887464986

    :setup: User with reporting access rights

    :steps:

        1. PUT /api/templates/:template_id/template_inputs/:id ... # add user input

    :expectedresults: User input is assigned to the report template and used in template

    :CaseImportance: High
    """
    host_name = gen_string('alpha').lower()
    input_name = gen_string('alpha').lower()
    input_value = gen_string('alpha').lower()
    template_name = gen_string('alpha').lower()
    template = f'<%= "value=\\"" %><%= input(\'{input_name}\') %><%= "\\"" %>'
    entities.Host(name=host_name).create()
    rt = entities.ReportTemplate(name=template_name, template=template).create()
    entities.TemplateInput(
        name=input_name,
        input_type="user",
        template=rt.id,
    ).create()
    ti = entities.TemplateInput(template=rt.id).search()[0].read()
    assert input_name == ti.name
    res = rt.generate(data={"input_values": {input_name: input_value}})
    assert f'value="{input_value}"' in res


@pytest.mark.tier2
def test_positive_lock_clone_nodelete_unlock_report():
    """Lock report template. Check it can be cloned and can't be deleted or edited.
       Unlock. Check it can be deleted and edited.

    :id: a4c577db-144e-4761-a42e-e83887464986

    :setup: User with reporting access rights, some report template that is not locked

    :steps:

        1. Create template
        2. Lock template
        3. Clone template, check cloned data
        4. Try to delete template
        5. Try to edit template
        6. Unlock template
        7. Edit template
        8. Delete template

    :expectedresults: Report is locked

    :CaseImportance: High

    :BZ: 1680458
    """
    # 1. Create template
    template_name = gen_string('alpha').lower()
    template_clone_name = gen_string('alpha').lower()
    template1 = gen_string('alpha')
    template2 = gen_string('alpha')
    rt = entities.ReportTemplate(name=template_name, template=template1).create()
    # 2. Lock template
    entities.ReportTemplate(id=rt.id, locked=True).update(["locked"])
    rt = rt.read()
    assert rt.locked is True
    # 3. Clone template, check cloned data
    rt.clone(data={'name': template_clone_name})
    cloned_rt = (
        entities.ReportTemplate()
        .search(query={'search': f'name="{template_clone_name}"'})[0]
        .read()
    )
    assert template_clone_name == cloned_rt.name
    assert template1 == cloned_rt.template
    # 4. Try to delete template
    if not is_open('BZ:1680458'):
        with pytest.raises(HTTPError):
            rt.delete()
        # In BZ1680458, exception is thrown but template is deleted anyway
        assert (
            len(entities.ReportTemplate().search(query={'search': f'name="{template_name}"'})) != 0
        )
    # 5. Try to edit template
    with pytest.raises(HTTPError):
        entities.ReportTemplate(id=rt.id, template=template2).update(["template"])
    rt = rt.read()
    assert template1 == rt.template
    # 6. Unlock template
    entities.ReportTemplate(id=rt.id, locked=False).update(["locked"])
    rt = rt.read()
    assert rt.locked is False
    # 7. Edit template
    entities.ReportTemplate(id=rt.id, template=template2).update(["template"])
    rt = rt.read()
    assert template2 == rt.template
    # 8. Delete template
    rt.delete()
    assert len(entities.ReportTemplate().search(query={'search': f'name="{template_name}"'})) == 0


@pytest.mark.tier2
@pytest.mark.stubbed
def test_positive_export_report():
    """Export report template

    :id: a4b577db-144e-4761-a42e-a83887464986

    :setup: User with reporting access rights, some report template

    :steps:

        1. /api/report_templates/:id/export

    :expectedresults: Report script is shown

    :CaseImportance: High
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_positive_generate_report_sanitized():
    """Generate report template where there are values in comma outputted which might
    break CSV format

    :id: a4b577db-144e-4961-a42e-e93887464986

    :setup: User with reporting access rights, Host Statuses report,
            a host with OS that has comma in its name

    :steps:

        1. POST /api/report_templates/:id/generate

    :expectedresults: Report is generated in proper CSV format (value with comma is quoted)

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_negative_create_report_without_name():
    """Try to create a report template with empty name

    :id: a4b577db-144e-4771-a42e-e93887464986

    :setup: User with reporting access rights

    :steps:

        1. POST /api/report_templates

    :expectedresults: Report is not created

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.rhel_ver_match(r'^(?!6$)\d+$')
@pytest.mark.no_containers
def test_positive_applied_errata(
    module_org, module_location, module_cv, module_lce, rhel_contenthost, target_sat
):
    """Generate an Applied Errata report

    :id: a4b577db-141e-4871-a42e-e93887464986

    :setup: A Host with some applied errata.

    :steps:

        1. Generate an Applied Errata report

    :expectedresults: A report is generated with all applied errata listed

    :CaseImportance: Medium
    """
    activation_key = target_sat.api.ActivationKey(
        environment=module_lce, organization=module_org
    ).create()
    ERRATUM_ID = str(settings.repos.yum_6.errata[2])
    target_sat.cli_factory.setup_org_for_a_custom_repo(
        {
            'url': settings.repos.yum_9.url,
            'organization-id': module_org.id,
            'content-view-id': module_cv.id,
            'lifecycle-environment-id': module_lce.id,
            'activationkey-id': activation_key.id,
        }
    )
    result = rhel_contenthost.register(module_org, module_location, activation_key.name, target_sat)
    assert f'The registered system name is: {rhel_contenthost.hostname}' in result.stdout
    assert rhel_contenthost.subscribed
    assert rhel_contenthost.execute(f'yum install -y {FAKE_1_CUSTOM_PACKAGE}').status == 0
    assert rhel_contenthost.execute(f'rpm -q {FAKE_1_CUSTOM_PACKAGE}').status == 0
    task_id = target_sat.api.JobInvocation().run(
        data={
            'feature': 'katello_errata_install',
            'inputs': {'errata': ERRATUM_ID},
            'targeting_type': 'static_query',
            'search_query': f'name = {rhel_contenthost.hostname}',
            'organization_id': module_org.id,
        },
    )['id']
    target_sat.wait_for_tasks(
        search_query=(f'label = Actions::RemoteExecution::RunHostsJob and id = {task_id}'),
        search_rate=15,
        max_tries=10,
    )
    rt = (
        target_sat.api.ReportTemplate()
        .search(query={'search': 'name="Host - Applied Errata"'})[0]
        .read()
    )
    res = rt.generate(
        data={
            'organization_id': module_org.id,
            'report_format': 'json',
            'input_values': {
                'Filter Errata Type': 'all',
                'Include Last Reboot': 'no',
                'Status': 'all',
            },
        }
    )
    assert res[0]['erratum_id'] == ERRATUM_ID
    assert res[0]['issued']


@pytest.mark.tier2
@pytest.mark.stubbed
def test_positive_generate_nonblocking():
    """Generate an Applied Errata report

    :id: a4b577db-142e-4871-a42e-e93887464986

    :setup: User with reporting access rights, some host with applied errata

    :steps:

        1. POST /api/report_templates/:id/schedule_report
        2. GET /api/report_templates/:id/report_data/:job_id

    :expectedresults: A report is generated asynchronously

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_positive_generate_email_compressed():
    """Generate an Applied Errata report, get it by e-mail, compressed

    :id: a4b577db-143e-4871-a42e-e93887464986

    :setup: User with reporting access rights, some host with applied errata

    :steps:

        1. POST /api/report_templates/:id/schedule_report

    :expectedresults: A report is generated asynchronously, the result
                      is compressed and mailed to the specified address

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_positive_generate_email_uncompressed():
    """Generate an Applied Errata report, get it by e-mail, uncompressed

    :id: a4b577db-143f-4871-a42e-e93887464986

    :setup: User with reporting access rights, some host with applied errata

    :steps:

        1. POST /api/report_templates/:id/schedule_report

    :expectedresults: A report is generated asynchronously, the result
                      is not compressed and is mailed
                      to the specified address

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_negative_bad_email():
    """Report can't be generated when incorrectly formed mail specified

    :id: a4b577db-164e-4871-a42e-e93887464986

    :setup: User with reporting access rights, some host with applied errata

    :steps:

        1. POST /api/report_templates/:id/schedule_report

    :expectedresults: Error message about wrong e-mail address, no task is triggered

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_positive_cleanup_task_running():
    """Report can't be generated when incorrectly formed mail specified

    :id: a4b577db-145e-4871-a42e-e93887464986

    :setup: Installed Satellite, user that can list running tasks

    :steps:

        1. List running tasks

    :expectedresults: Report cleanup task is running

    :CaseImportance: Medium
    """


@pytest.mark.tier2
@pytest.mark.stubbed
def test_negative_nonauthor_of_report_cant_download_it():
    """The resulting report should only be downloadable by
       the user that generated it or admin. Check.

    :id: a4b577db-146e-4871-a42e-e93887464986

    :setup: Installed Satellite, user that can list running tasks

    :steps:

        1. POST /api/report_templates/:id/schedule_report
        2. GET /api/report_templates/:id/report_data/:job_id (as a different non-admin user)

    :expectedresults: Report can't be downloaded. Error.

    :CaseImportance: Medium
    """


@pytest.mark.tier3
def test_positive_generate_entitlements_report(setup_content, target_sat):
    """Generate a report using the Subscription - Entitlement Report template.

    :id: 722e8802-367b-4399-bcaa-949daab26632

    :setup: Installed Satellite with Organization, Activation key,
            Content View, Content Host, and Subscriptions.

    :steps:

        1. Get
        /api/report_templates/130-Subscription - Entitlement Report/generate/id/report_format

    :expectedresults: Report is generated showing all necessary information for entitlements.

    :CaseImportance: High
    """
    with Broker(nick='rhel7', host_class=ContentHost) as vm:
        ak, org = setup_content
        vm.install_katello_ca(target_sat)
        vm.register_contenthost(org.label, ak.name)
        assert vm.subscribed
        rt = (
            entities.ReportTemplate()
            .search(query={'search': 'name="Subscription - Entitlement Report"'})[0]
            .read()
        )
        res = rt.generate(
            data={
                "organization_id": org.id,
                "report_format": "json",
                "input_values": {"Days from Now": "no limit"},
            }
        )
        assert res[0]['Host Name'] == vm.hostname
        assert res[0]['Subscription Name'] == DEFAULT_SUBSCRIPTION_NAME


@pytest.mark.tier3
def test_positive_schedule_entitlements_report(setup_content, target_sat):
    """Schedule a report using the Subscription - Entitlement Report template.

    :id: 5152c518-b0da-4c27-8268-2be78289249f

    :setup: Installed Satellite with Organization, Activation key,
            Content View, Content Host, and Subscriptions.

    :steps:

        1. POST /api/report_templates/130-Subscription - Entitlement Report/schedule_report/

    :expectedresults: Report is scheduled and contains all necessary
                      information for entitlements.

    :CaseImportance: High
    """
    with Broker(nick='rhel7', host_class=ContentHost) as vm:
        ak, org = setup_content
        vm.install_katello_ca(target_sat)
        vm.register_contenthost(org.label, ak.name)
        assert vm.subscribed
        rt = (
            entities.ReportTemplate()
            .search(query={'search': 'name="Subscription - Entitlement Report"'})[0]
            .read()
        )
        scheduled_csv = rt.schedule_report(
            data={
                'id': f'{rt.id}-Subscription - Entitlement Report',
                'organization_id': org.id,
                'report_format': 'csv',
                "input_values": {"Days from Now": "no limit"},
            }
        )
        data_csv, _ = wait_for(
            rt.report_data,
            func_kwargs={'data': {'id': rt.id, 'job_id': scheduled_csv['job_id']}},
            fail_condition=None,
            timeout=300,
            delay=10,
        )
        assert vm.hostname in data_csv
        assert DEFAULT_SUBSCRIPTION_NAME in data_csv


@pytest.mark.no_containers
@pytest.mark.tier3
def test_positive_generate_job_report(setup_content, target_sat, rhel7_contenthost):
    """Generate a report using the Job - Invocation Report template.

    :id: 946c39db-3061-43d7-b922-1be61f0c7d93

    :BZ: 1761012

    :steps:
        1. Register a host and properly setup REX for it.
        2. Run a simple job with predictable output
        3. Using the Job ID, generate a report using the Job - Invocation
           report template.

    :expectedresults: Report returns correct information (Hostname is set correctly,
        the output is what would be expected.)

    :customerscenario: true
    """
    ak, org = setup_content
    rhel7_contenthost.install_katello_ca(target_sat)
    rhel7_contenthost.register_contenthost(org.label, ak.name)
    rhel7_contenthost.add_rex_key(target_sat)
    assert rhel7_contenthost.subscribed
    # Run a Job on the Host
    template_id = (
        target_sat.api.JobTemplate()
        .search(query={'search': 'name="Run Command - Script Default"'})[0]
        .id
    )
    job = target_sat.api.JobInvocation().run(
        synchronous=False,
        data={
            'job_template_id': template_id,
            'inputs': {
                'command': 'pwd',
            },
            'targeting_type': 'static_query',
            'search_query': f'name = {rhel7_contenthost.hostname}',
        },
    )
    target_sat.wait_for_tasks(f'resource_type = JobInvocation and resource_id = {job["id"]}')
    result = target_sat.api.JobInvocation(id=job['id']).read()
    assert result.succeeded == 1
    rt = (
        target_sat.api.ReportTemplate()
        .search(query={'search': 'name="Job - Invocation Report"'})[0]
        .read()
    )
    res = rt.generate(
        data={
            'organization_id': org.id,
            'report_format': "json",
            'input_values': {"job_id": job["id"]},
        }
    )
    assert res[0]['Host'] == rhel7_contenthost.hostname
    assert '/root' in res[0]['stdout']


@pytest.mark.tier2
@pytest.mark.no_containers
@pytest.mark.rhel_ver_match(r'^(?!6$)\d+$')
def test_positive_installable_errata(
    module_org, module_target_sat, module_location, module_cv, module_lce, rhel_contenthost
):
    """Generate an Installable Errata report

    :id: 6263a0fa-5021-4553-939b-84fb71c81d59

    :setup: A Host with some applied errata

    :steps:
        1. Downgrade a package contained within the errata
        2. Generate an Installable Errata report

    :expectedresults: A report is generated with the installable errata listed

    :CaseImportance: Medium

    :customerscenario: true

    :BZ: 1726504
    """
    activation_key = module_target_sat.api.ActivationKey(
        environment=module_lce, organization=module_org
    ).create()
    ERRATUM_ID = str(settings.repos.yum_6.errata[2])
    module_target_sat.cli_factory.setup_org_for_a_custom_repo(
        {
            'url': settings.repos.yum_9.url,
            'organization-id': module_org.id,
            'content-view-id': module_cv.id,
            'lifecycle-environment-id': module_lce.id,
            'activationkey-id': activation_key.id,
        }
    )
    result = rhel_contenthost.register(
        module_org, module_location, activation_key.name, module_target_sat
    )
    assert f'The registered system name is: {rhel_contenthost.hostname}' in result.stdout
    assert rhel_contenthost.subscribed
    result = rhel_contenthost.run(f'yum install -y {FAKE_2_CUSTOM_PACKAGE}')
    assert result.status == 0
    rhel_contenthost.add_rex_key(satellite=module_target_sat)
    # Install/Apply the errata
    task_id = module_target_sat.api.JobInvocation().run(
        data={
            'feature': 'katello_errata_install',
            'inputs': {'errata': ERRATUM_ID},
            'targeting_type': 'static_query',
            'search_query': f'name = {rhel_contenthost.hostname}',
            'organization_id': module_org.id,
        },
    )['id']
    module_target_sat.wait_for_tasks(
        search_query=(f'label = Actions::RemoteExecution::RunHostsJob and id = {task_id}'),
        search_rate=15,
        max_tries=10,
    )
    # Downgrade the package impacted by the erratum
    result = rhel_contenthost.run(f'yum downgrade -y {FAKE_1_CUSTOM_PACKAGE}')
    assert result.status == 0

    _data_for_generate = {
        'organization_id': module_org.id,
        'report_format': "json",
        'input_values': {
            'Filter Errata Type': 'all',
            'Include Last Reboot': 'no',
            'Status': 'all',
        },
    }
    search_query = {'search': 'name="Host - Applicable Errata"'}
    template = module_target_sat.api.ReportTemplate()
    # Wait for the search to finish collecting results, it may take some time
    wait_for(
        lambda: (
            template.search(query=search_query)[0].read().generate(data=_data_for_generate) != []
        ),
        timeout=120,
        delay=10,
    )
    # Generate final report and check the entry
    report = template.search(query=search_query)[0].read().generate(data=_data_for_generate)

    assert report != []
    assert datetime.now().strftime("%Y-%m-%d") in report[0]['Available since']
    assert FAKE_1_CUSTOM_PACKAGE_NAME in report[0]['Packages']
    assert report[0]['Erratum'] == ERRATUM_ID

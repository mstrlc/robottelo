"""Test Activation Key related Upgrade Scenario's

:Requirement: UpgradedSatellite

:CaseAutomation: Automated

:CaseComponent: ActivationKeys

:Team: Phoenix-subscriptions

:CaseImportance: High

"""
import pytest
from requests.exceptions import HTTPError


class TestActivationKey:
    """
    The test class contains steps to test the activation keys exists post upgrade and can be
    operated/modified.
    """

    @pytest.fixture
    def activation_key_setup(self, request, target_sat):
        """
        The purpose of this fixture is to setup the activation key based on the provided
        organization, content_view and activation key name.
        """
        org = target_sat.api.Organization(name=f"{request.param}_org").create()
        custom_repo = target_sat.api.Repository(
            product=target_sat.api.Product(organization=org).create()
        ).create()
        custom_repo.sync()
        cv = target_sat.api.ContentView(
            organization=org, repository=[custom_repo.id], name=f"{request.param}_cv"
        ).create()
        cv.publish()
        ak = target_sat.api.ActivationKey(
            content_view=cv, organization=org, name=f"{request.param}_ak"
        ).create()
        ak_details = {'org': org, "cv": cv, 'ak': ak, 'custom_repo': custom_repo}
        return ak_details

    @pytest.mark.pre_upgrade
    @pytest.mark.parametrize(
        'activation_key_setup', ['test_pre_create_activation_key'], indirect=True
    )
    def test_pre_create_activation_key(self, activation_key_setup, target_sat):
        """Before Upgrade, Creates the activation key with different entities and update their
        contents.

        :id: preupgrade-a7443b54-eb2e-497b-8a50-92abeae01496

        :steps:
            1. Create the activation key.
            2. Add subscription in the activation key.
            3. Check the subscription id of the activation key and compare it with custom_repos
                product id.
            4. Update the host collection in the activation key.

        :parametrized: yes

        :expectedresults: Activation key should be created successfully and it's subscription id
            should be same with custom repos product id.
        """
        ak = activation_key_setup['ak']
        org_subscriptions = target_sat.api.Subscription(
            organization=activation_key_setup['org']
        ).search()
        for subscription in org_subscriptions:
            ak.add_subscriptions(data={'quantity': 1, 'subscription_id': subscription.id})
        ak_subscriptions = ak.product_content()['results']
        subscr_id = {subscr['product']['id'] for subscr in ak_subscriptions}
        assert subscr_id == {activation_key_setup['custom_repo'].product.id}
        ak.host_collection.append(target_sat.api.HostCollection().create())
        ak.update(['host_collection'])
        assert len(ak.host_collection) == 1

    @pytest.mark.post_upgrade(depend_on=test_pre_create_activation_key)
    def test_post_crud_activation_key(self, dependent_scenario_name, target_sat):
        """After Upgrade, Activation keys entities remain the same and
        all their functionality works.

        :id: postupgrade-a7443b54-eb2e-497b-8a50-92abeae01496

        :steps:
            1. Postupgrade, Verify activation key has same entities associated.
            2. Update existing activation key with new entities.
            3. Delete activation key.

        :expectedresults: Activation key's entities should be same after upgrade and activation
            key update and delete should work.
        """
        pre_test_name = dependent_scenario_name
        org = target_sat.api.Organization().search(query={'search': f'name={pre_test_name}_org'})
        ak = target_sat.api.ActivationKey(organization=org[0]).search(
            query={'search': f'name={pre_test_name}_ak'}
        )
        cv = target_sat.api.ContentView(organization=org[0]).search(
            query={'search': f'name={pre_test_name}_cv'}
        )
        assert f'{pre_test_name}_ak' == ak[0].name
        assert f'{pre_test_name}_cv' == cv[0].name
        ak[0].host_collection.append(target_sat.api.HostCollection().create())
        ak[0].update(['host_collection'])
        assert len(ak[0].host_collection) == 2
        custom_repo2 = target_sat.api.Repository(
            product=target_sat.api.Product(organization=org[0]).create()
        ).create()
        custom_repo2.sync()
        cv2 = target_sat.api.ContentView(organization=org[0], repository=[custom_repo2.id]).create()
        cv2.publish()
        org_subscriptions = target_sat.api.Subscription(organization=org[0]).search()
        for subscription in org_subscriptions:
            provided_products_ids = [prod.id for prod in subscription.read().provided_product]
            if custom_repo2.product.id in provided_products_ids:
                ak[0].add_subscriptions(data={'quantity': 1, 'subscription_id': subscription.id})
        ak_subscriptions = ak[0].product_content()['results']
        assert custom_repo2.product.id in {subscr['product']['id'] for subscr in ak_subscriptions}
        ak[0].delete()
        with pytest.raises(HTTPError):
            target_sat.api.ActivationKey(id=ak[0].id).read()
        for cv_object in [cv2, cv[0]]:
            cv_contents = cv_object.read_json()
            cv_object.delete_from_environment(cv_contents['environments'][0]['id'])
            cv_object.delete(cv_object.organization.id)
        custom_repo2.delete()
        org[0].delete()

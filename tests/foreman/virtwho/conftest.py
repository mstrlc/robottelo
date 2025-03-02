from fauxfactory import gen_string
import pytest
from requests.exceptions import HTTPError

from robottelo.logging import logger


@pytest.fixture(scope='module')
def module_user(request, module_target_sat, default_org, default_location):
    """Creates admin user with default org set to module org and shares that
    user for all tests in the same test module. User's login contains test
    module name as a prefix.

    :rtype: :class:`nailgun.entities.Organization`
    """
    # take only "module" from "tests.foreman.virtwho.test_module"
    test_module_name = request.module.__name__.split('.')[-1].split('_', 1)[-1]
    login = f'{test_module_name}_{gen_string("alphanumeric")}'
    password = gen_string('alphanumeric')
    logger.debug('Creating session user %r', login)
    user = module_target_sat.api.User(
        admin=True,
        default_organization=default_org,
        default_location=default_location,
        description=f'created automatically by airgun for module "{test_module_name}"',
        login=login,
        password=password,
    ).create()
    user.password = password
    yield user
    try:
        logger.debug('Deleting session user %r', user.login)
        user.delete(synchronous=False)
    except HTTPError as err:
        logger.warning('Unable to delete session user: %s', str(err))


@pytest.fixture
def session(test_name, module_user, module_target_sat):
    """Session fixture which automatically initializes (but does not start!)
    airgun UI session and correctly passes current test name to it. Uses shared
    module user credentials to log in.


    Usage::

        def test_foo(session):
            with session:
                # your ui test steps here
                session.architecture.create({'name': 'bar'})
    """
    return module_target_sat.ui_session(test_name, module_user.login, module_user.password)


@pytest.fixture(scope='module')
def module_user_sca(request, module_target_sat, module_org, module_location):
    """Creates admin user with default org set to module org and shares that
    user for all tests in the same test module. User's login contains test
    module name as a prefix.

    :rtype: :class:`nailgun.entities.Organization`
    """
    # take only "module" from "tests.foreman.virtwho.test_module"
    test_module_name = request.module.__name__.split('_', 1)[-1]
    login = f'{test_module_name}_{gen_string("alphanumeric")}'
    password = gen_string('alphanumeric')
    logger.debug('Creating session user %r', login)
    user = module_target_sat.api.User(
        admin=True,
        default_organization=module_org,
        default_location=module_location,
        description=f'created automatically by airgun for module "{test_module_name}"',
        login=login,
        password=password,
    ).create()
    user.password = password
    yield user
    try:
        logger.debug('Deleting session user %r', user.login)
        user.delete(synchronous=False)
    except HTTPError as err:
        logger.warning('Unable to delete session user: %s', str(err))


@pytest.fixture
def session_sca(test_name, module_user_sca, module_target_sat):
    """Session fixture which automatically initializes (but does not start!)
    airgun UI session and correctly passes current test name to it. Uses shared
    module user credentials to log in.


    Usage::

        def test_foo(session):
            with session:
                # your ui test steps here
                session.architecture.create({'name': 'bar'})
    """
    return module_target_sat.ui_session(test_name, module_user_sca.login, module_user_sca.password)

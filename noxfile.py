import nox.sessions


nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ['tests', 'test_redis']


@nox.session(python=['3.7', '3.8'])
def tests(session: nox.sessions.Session, redis=None):
    """ Run all tests """
    session.install('poetry')
    session.run('poetry', 'install')

    # Test
    session.run('pytest', 'tests/', '--cov=matroska_cache')


@nox.session()
@nox.parametrize(
    'redis', [
        '3.0.1',
        '3.1.0',
        '3.2.0',
        '3.2.1',
        '3.3.0', '3.3.1', '3.3.2', '3.3.3', '3.3.4', '3.3.5', '3.3.6', '3.3.7', '3.3.8', '3.3.9', '3.3.10', '3.3.11',
        '3.4.0', '3.4.1',
        '3.5.0', '3.5.1', '3.5.2', '3.5.3',
    ]
)
def test_redis(session, redis):
    tests(session, redis=redis)

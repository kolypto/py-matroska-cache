import nox.sessions


nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ['tests']


@nox.session(python=['3.6', '3.7', '3.8', 'pypy3.6-7.3.1'])
def tests(session: nox.sessions.Session):
    """ Run all tests """
    session.install('poetry')
    session.run('poetry', 'install')

    # Test
    session.run('pytest', 'tests/', '--cov=matroska_cache')

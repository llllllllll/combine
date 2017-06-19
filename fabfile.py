from fabric.api import task, run, cd, settings, sudo, prefix, env
from fabric.contrib.project import rsync_project


def add_apt(*paths):
    """Add apt PPAs.

    Parameters
    ----------
    *paths : Iterable[str]
        The PPA paths without the prefixing ``ppa:``.
    """
    for path in paths:
        sudo('add-apt-repository -ry ppa:%s' % path)
        sudo('add-apt-repository -y ppa:%s' % path)
    sudo('apt update')


def apt_install(*packages):
    """Install packages with apt.

    Parameters
    ----------
    *packages : Iterable[str]
        The packages to install.
    """
    sudo('apt install -y %s' % ' '.join(packages))


def git_pull():
    run('git pull')
    run('git submodule update')


def restart_nginx():
    with settings(warn_only=True):
        sudo('pkill nginx')

    sudo('nginx -c combine/etc/nginx.conf -p `pwd`')


@task
def setup_system():
    """Setup the system dependencies and repo.
    """
    add_apt('fkrull/deadsnakes')
    apt_install(
        'emacs-nox',
        'python3.6-dev',
        'python3.6-gdbm',
        'python3.6-venv',
        'nginx',
        'screen',
        'gcc',
        'libssl-dev',
        'supervisor',
    )
    ensure_venv()

    sudo('mkdir -p /tmp/gunicorn_run')
    sudo('chmod 777 /tmp/gunicorn_run')

    restart_nginx()

    sudo('mkdir -p /var/run/watch-ip')
    sudo('chmod 777 /var/run/watch-ip')


def ensure_venv(name='venv'):
    sudo('mkdir -p /venvs')
    sudo('chmod 777 /venvs')

    with settings(warn_only=True):
        venv_exists = run('test -d /venvs/%s' % name).succeeded

    if not venv_exists:
        run('python3.6 -m venv /venvs/%s' % name)


def command_with_venv(command, name='venv'):
    return 'source /venvs/%s/bin/activate && %s' % (name, command)


def venv(name='venv'):
    return prefix('source /venvs/%s/bin/activate' % name)


def run_screen(command, name=None):
    cmd = 'screen'
    if name is not None:
        cmd += ' -S %s' % name
    cmd += ' -d -m %r' % command

    run(cmd, pty=False)


@task
def rebuild_library():
    update()
    run('python -m slider library --beatmaps data/maps')


def supervisorctl(command):
    return sudo(
        ' '.join((
            'supervisorctl',
            '-c',
            'etc/supervisord.conf',
            '-s',
            'unix:///var/run/supervisord.sock',
            command,
        )),
    )


@task
def update():
    rsync_project(
        '/home/%s/combine' % env.user,
        '.',
        exclude=(
            '.git',
            'data',
            'config.yml',
        ),
    )

    with cd('combine'), venv('venv'):
        run('mv config.yml{.prd,}')

        run('pip install -r etc/requirements.txt')
        run('pip install -e .')

        run(
            'sed "s|{cwd}|`pwd`|g" etc/supervisord.conf.template'
            ' > etc/supervisord.conf',
        )
        supervisorctl('shutdown')
        sudo('supervisord -c etc/supervisord.conf')

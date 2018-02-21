from io import StringIO
import os

from fabric.api import task, run, cd, settings, sudo, prefix, env, put
from fabric.contrib.project import rsync_project
import jinja2


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
        'nginx-core',
        'screen',
        'gcc',
        'libssl-dev',
    )
    ensure_venv('combine')

    sudo('mkdir -p /tmp/gunicorn_run')
    sudo('chmod 777 /tmp/gunicorn_run')

    restart_nginx()

    sudo('mkdir -p /var/run/watch-ip')
    sudo('chmod 777 /var/run/watch-ip')


def ensure_venv(name):
    sudo('mkdir -p /venvs')
    sudo('chmod 777 /venvs')

    with settings(warn_only=True):
        venv_exists = run('test -d /venvs/%s' % name).succeeded

    if not venv_exists:
        run('python3.6 -m venv /venvs/%s' % name)


def command_with_venv(command, name='venv'):
    return 'source /venvs/%s/bin/activate && %s' % (name, command)


def venv(name):
    return prefix('source /venvs/%s/bin/activate' % name)


@task
def rebuild_library():
    update()
    with venv('combine'):
        run('LC_LANG=C.UTF-8 LANG=C.UTF-8 python -m slider library /data/maps')


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


def put_systemd_services():
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.abspath('systemd')),
    )
    services = (
        'combine-uploader.service.template',
        'combine-irc.service.template',
        'combine-train.service.template',
        'watch-ip.service.template',
    )
    template_variables = {
        'VENV': '/venvs/combine',
        'COMBINE_CONFIG_FILE': '/home/%s/combine/config.yml' % env.user,
        'IP_FILE': '/var/run/watch-ip/ip',
    }
    for name in services:
        result = environment.get_template(name).render(template_variables)
        put(
            StringIO(result),
            '/etc/systemd/system/%s' % name[:-len('.template')],
            use_sudo=True,
        )

    put(
        'systemd/watch-ip.timer',
        '/etc/systemd/system/watch-ip.timer',
        use_sudo=True,
    )

    sudo('systemctl daemon-reload')


def systemctl_start(service):
    sudo('systemctl restart %s' % service)


def mkdir(path):
    sudo('mkdir -p {path!r} && chown {user} {path!r}'.format(
        path=path,
        user=env.user,
    ))


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

    with cd('combine'), venv('combine'):
        run('pip install -r etc/requirements.txt')
        run('pip install -e .')


@task
def deploy():
    update()

    with cd('combine'), venv('combine'):
        run('mv config.yml{.prd,}')

        put_systemd_services()

        mkdir('/var/run/gunicorn')
        systemctl_start('combine-uploader')
        systemctl_start('combine-irc')
        systemctl_start('combine-train')

        mkdir('/var/run/watch-ip')
        systemctl_start('watch-ip.timer')
        systemctl_start('watch-ip.service')

        run('systemctl is-active combine-uploader')
        run('systemctl is-active combine-irc')
        run('systemctl is-active combine-train')

    restart_nginx()

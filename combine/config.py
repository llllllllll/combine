from functools import partial
import pathlib

from straitlets import StrictSerializable, Unicode, Instance, Integer, Enum
from straitlets.py3 import Path


class Config(StrictSerializable):
    """The configuration needed to run the combine processes.
    """
    maps = Path(example='data/maps')
    models = Path(example='data/models')
    model_cache_size = Integer(example=24)
    token_secret_path = Path(example='data/token-secret')
    api_key = Unicode(example='<api-key>')
    username = Unicode(example='<username>')
    password = Unicode(example='<password>')
    github_url = Unicode(example='http://github.com/example-user/example-repo')
    upload_url = Unicode(example='http://localhost/')
    email_address = Unicode(example='example@example.com')

    @Instance
    class irc(StrictSerializable):
        server = Unicode(example='cho.ppy.sh')
        port = Integer(example=6667)

    @Instance
    class gunicorn(StrictSerializable):
        bind = Unicode(example='localhost:5000')
        workers = Integer(example=2)
        timeout = Integer(example=6000)
        accesslog = Path(example='-')
        error = Path(example='-')

    @partial(Instance, default_value=None, allow_none=True, example=None)
    class logging_email(StrictSerializable):
        from_address = Unicode(example='example@example.com')
        to_address = Unicode(example='example@example.com')
        server_address = Unicode(example='smtp.gmail.com')
        server_port = Integer(example=587)
        password = Unicode(example='<password>')
        log_level = Enum(
            values=['debug', 'info' 'notice', 'warning', 'error', 'critical'],
            example='error',
            default='error',
        )

    @property
    def token_secret(self):
        with open(self.token_secret_path, 'rb') as f:
            return f.read()


# the absolute path to the template file
template_path = pathlib.Path(__file__).parent / 'config.yml.template'

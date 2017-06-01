import pathlib

from straitlets import StrictSerializable, Unicode, Instance, Integer
from straitlets.py3 import Path


class Config(StrictSerializable):
    """The configuration needed to run the fundamentals process.
    """
    maps = Path(example='data/maps')
    models = Path(example='data/models')
    model_cache_size = Integer(example=24)
    token_secret_path = Path(example='data/token-secret')
    api_key = Unicode(example='<api-key>')
    username = Unicode(example='<username>')
    password = Unicode(example='<password>')
    upload_url = Unicode(example='http://localhost/')

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

    @property
    def token_secret(self):
        with open(self.token_secret_path, 'rb') as f:
            return f.read()


# the absolute path to the template file
template_path = pathlib.Path(__file__).parent / 'config.yml.template'

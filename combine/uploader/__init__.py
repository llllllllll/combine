import pathlib

from cryptography.fernet import Fernet
import flask
from gunicorn.app.base import BaseApplication

from .views import api


def build_app(*,
              model_cache_dir,
              replay_cache_dir,
              token_secret,
              client,
              bot_user,
              github_url,
              email_address,
              gunicorn_options,
              train_queue):
    """Build the app object.

    Parameters
    ----------
    model_cache_dir : path-like
        The path to the model directory.
    replay_cache_dir : path-like
        The path to the replay directory.
    token_secret : bytes
        The shared secret for the uploader and irc server.
    client : Library
        The client used to fetch beatmaps.
    bot_user : str
        The username of the bot.
    github_url : str
        The url of the repo on github.
    email_address : str
        The email address for support / comments.
    gunicorn_options : dict
        Options to forward to gunicorn.
    train_queue : TrainQueue
        The queue to store tasks in.

    Returns
    -------
    app : App
        The app to run.
    """
    inner_app = flask.Flask(__name__)
    inner_app.register_blueprint(api)
    inner_app.secret_key = Fernet.generate_key().decode('ascii')

    model_cache_dir = pathlib.Path(model_cache_dir)
    replay_cache_dir = pathlib.Path(replay_cache_dir)
    token_secret = Fernet(token_secret)

    @inner_app.before_request
    def setup_globals():
        flask.g.model_cache_dir = model_cache_dir
        flask.g.replay_cache_dir = replay_cache_dir
        flask.g.token_secret = token_secret
        flask.g.client = client
        flask.g.bot_user = bot_user
        flask.g.github_url = github_url
        flask.g.email_address = email_address
        flask.g.train_queue = train_queue

    class app(BaseApplication):
        def load(self):
            return inner_app

        def load_config(self, *, _cfg=gunicorn_options):
            for k, v in _cfg.items():
                k = k.lower()
                if k in self.cfg.settings and v is not None:
                    self.cfg.set(k.lower(), v)

    return app()

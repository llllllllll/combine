import click
from logbook import lookup_level
from straitlets.ext.click import YamlConfigFile

from .config import Config
from .logging import AlternateColorizedStderrHandler


@click.group()
@click.option(
    '--config',
    default='config.yml',
    type=YamlConfigFile(Config),
)
@click.option(
    '--log-level',
    default='info',
    help='The minimum log level to show.',
)
@click.pass_context
def main(ctx, config, log_level):
    ctx.obj = config

    AlternateColorizedStderrHandler(
        level=lookup_level(log_level.upper()),
    ).push_application()


@main.command()
@click.pass_obj
def irc(obj):
    """Serve the irc bot an enter into a repl where you can send the bot user
    messages directly.
    """
    import readline  # noqa
    from textwrap import dedent

    from slider import Library, Client

    from . import irc
    from .handler import CombineHandler

    library = Library(obj.maps)
    osu_client = Client(library, obj.api_key)

    username = obj.username
    handler = CombineHandler(
        username,
        osu_client,
        obj.models,
        obj.model_cache_size,
        obj.token_secret,
        obj.upload_url,
    )

    c = irc.Client(
        obj.irc.server,
        obj.irc.port,
        username,
        obj.password,
        'osu',
        handler,
    )

    print(dedent(
        """Running combine IRC server!

        Commands:

          !r[ec[ommend]] : send yourself a recommendation
          !gen-token     : generate an upload token for yourself
        """,
    ))
    with c:
        while True:
            try:
                command = input('> ')
            except EOFError:
                print()
                break

            if command:
                handler(c, username, username, command)


@main.command('gen-token')
@click.option(
    '-u',
    '--user',
    help='The user to create a token for.',
    required=True,
)
@click.pass_obj
def gen_token(obj, user):
    """Generate a token for a user.
    """
    from cryptography.fernet import Fernet

    from .token import gen_token

    print(gen_token(Fernet(obj.token_secret), user))


@main.command()
@click.pass_obj
def uploader(obj):
    """Serve the replay upload page.
    """
    from slider import Library, Client

    from .uploader import build_app

    build_app(
        model_cache_dir=obj.models,
        token_secret=obj.token_secret,
        client=Client(Library(obj.maps), obj.api_key),
        bot_user=obj.username,
        github_url=obj.github_url,
        email_address=obj.email_address,
        gunicorn_options=obj.gunicorn.to_dict(),
    ).run()


@main.command()
@click.option(
    '--user',
    required=True,
    help='The user the train the model for.',
)
@click.option(
    '--replays',
    required=True,
    help='The directory of replays to train against with.'
)
@click.option(
    '--age',
    help='The age of replays to consider when training.',
)
@click.pass_obj
def train(obj, user, replays, age):
    """Manually train the model for a given user.
    """
    import os
    import pickle

    import pandas as pd
    from slider import Library, Client
    from slider.model import train_from_replay_directory

    if age is not None:
        age = pd.Timedelta(age)

    m = train_from_replay_directory(
        replays,
        client=Client(Library(obj.maps), obj.api_key),
        age=age,
    )
    with open(os.path.join(obj.models, user), 'wb') as f:
        pickle.dump(m, f)


if __name__ == '__main__':
    main()

import click
from logbook import lookup_level
from straitlets.ext.click import YamlConfigFile

from .config import Config
from .logging import AlternateColorizedStderrHandler


@click.group()
@click.option(
    '--config',
    default='config.yml',
    envvar='COMBINE_CONFIG_FILE',
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

    logging_email = config.logging_email
    if logging_email is not None:
        from logbook import MailHandler

        MailHandler(
            logging_email.from_address,
            logging_email.to_address,
            server_addr=(
                logging_email.server_address,
                logging_email.server_port,
            ),
            credentials=(
                logging_email.from_address,
                logging_email.password,
            ),
            level=lookup_level(logging_email.log_level.upper()),
            secure=True,
            subject='Combine Error!',
            bubble=True,
        ).push_application()

    AlternateColorizedStderrHandler(
        level=lookup_level(log_level.upper()),
        bubble=True,
    ).push_application()


@main.command()
@click.option(
    '--daemon/--no-daemon',
    default=False,
    help='Run without the repl?',
)
@click.option(
    '--repl-only/--no-repl-only',
    default=False,
    help='Run just the repl without listening to external user commands.',
)
@click.pass_obj
def irc(obj, daemon, repl_only):
    """Serve the irc bot an enter into a repl where you can send the bot user
    messages directly.
    """
    import readline  # noqa
    import sys
    from textwrap import dedent

    from . import irc
    from .handler import CombineHandler, ReplCombineHandler

    if daemon and repl_only:
        print('cannot set --repl-only and --daemon', file=sys.stderr)
        exit(-1)

    osu_client = obj.client

    username = obj.username
    handler = (ReplCombineHandler if repl_only else CombineHandler)(
        username,
        osu_client,
        obj.models,
        obj.model_cache_size,
        obj.token_secret,
        obj.upload_url,
        obj.train_queue,
    )

    c = irc.Client(
        obj.irc.server,
        obj.irc.port,
        username,
        obj.password,
        'osu',
        handler,
    )

    if daemon:
        c.run()
        return

    print(dedent(
        f"""Running combine IRC server!{' (REPL ONLY)' if repl_only else ''}

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
    from .uploader import build_app

    build_app(
        model_cache_dir=obj.models,
        replay_cache_dir=obj.replays,
        token_secret=obj.token_secret,
        client=obj.client,
        bot_user=obj.username,
        github_url=obj.github_url,
        email_address=obj.email_address,
        gunicorn_options=obj.gunicorn.to_dict(),
        train_queue=obj.train_queue,
    ).run()


@main.command()
@click.pass_obj
def train(obj):
    """Run the model training service.
    """
    from .train import run_train_queue

    run_train_queue(
        train_queue=obj.train_queue,
        replay_cache_dir=obj.replays,
        model_cache_dir=obj.models,
        client=obj.client,
    )


@main.command('train-single')
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
def train_single(obj, user, replays, age):
    """Manually train the model for a given user.
    """
    import os
    import pickle

    import pandas as pd
    from slider.model import train_from_replay_directory

    if age is not None:
        age = pd.Timedelta(age)

    m = train_from_replay_directory(
        replays,
        client=obj.client,
        age=age,
    )
    with open(os.path.join(obj.models, user), 'wb') as f:
        pickle.dump(m, f)


@main.command(name='check-ip')
@click.argument('ip-file')
@click.pass_obj
def check_ip(obj, ip_file):
    """Check the current ip address against the saved value ip-file.
    """
    from combine.check_ip import main

    main(obj, ip_file)


if __name__ == '__main__':
    main()

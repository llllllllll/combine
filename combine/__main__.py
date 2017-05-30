import click


@click.group()
def main():
    pass


@main.command()
@click.option(
    '--maps',
    envvar='COMBINE_MAPS',
    required=True,
)
@click.option(
    '--models',
    envvar='COMBINE_MODELS',
    required=True,
)
@click.option(
    '--model-cache-size',
    envvar='COMBINE_MODEL_CACHE_SIZE',
    default=24,
    type=int,
)
@click.option(
    '--token-secret',
    envvar='COMBINE_TOKEN_SECRET',
    required=True,
)
@click.option(
    '--api-key',
    envvar='COMBINE_API_KEY',
    required=True,
)
@click.option(
    '--username',
    envvar='COMBINE_USERNAME',
    required=True,
)
@click.option(
    '--password',
    envvar='COMBINE_PASSWORD',
    required=True,
)
@click.option(
    '--irc-server',
    envvar='COMBINE_IRC_SERVER',
    default='cho.ppy.sh',
)
@click.option(
    '--irc-port',
    envvar='COMBINE_IRC_PORT',
    default=6667,
    type=int,
)
def serve(maps,
          models,
          model_cache_size,
          token_secret,
          api_key,
          username,
          password,
          irc_server,
          irc_port):
    from slider import Library, Client

    from . import irc
    from .handler import CombineHandler

    library = Library(maps)
    osu_client = Client(library, api_key)

    handler = CombineHandler(
        username,
        osu_client,
        models,
        model_cache_size,
        token_secret,
    )

    c = irc.Client(
        irc_server,
        irc_port,
        username,
        password,
        'osu',
        handler,
    )

    c = irc.Client(
        irc_server,
        irc_port,
        username,
        password,
        'osu',
        handler,
    )
    with c:
        while True:
            try:
                input('hit enter to send youself a recommendation ')
            except EOFError:
                print()
                break

            handler(c, username, username, '!r')
            print('sent!')


@main.command()
@click.option(
    '--user',
    required=True,
)
@click.option(
    '--replays',
    required=True,
)
@click.option(
    '--age',
)
@click.option(
    '--maps',
    envvar='COMBINE_MAPS',
    required=True,
)
@click.option(
    '--models',
    envvar='COMBINE_MODELS',
    required=True,
)
def train(user, replays, age, maps, models):
    import os
    import pickle

    import pandas as pd
    from slider import Library
    from slider.model import train_from_replay_directory

    if age is not None:
        age = pd.Timedelta(age)

    m = train_from_replay_directory(replays, Library(maps), age=age)
    with open(os.path.join(models, user), 'wb') as f:
        pickle.dump(m, f)



if __name__ == '__main__':
    main()

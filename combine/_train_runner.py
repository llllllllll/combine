import click


@click.command()
@click.option(
    '--user',
    help='The user to train for.',
    required=True,
)
@click.option(
    '--replay-cache-dir',
    help='The path to the root replay directory.',
    required=True,
)
@click.option(
    '--model-cache-dir',
    help='The path to the root model directory.',
    required=True,
)
@click.option(
    '--age',
    help='The maximum age of replays to include in the training data.'
)
@click.option(
    '--library',
    help='The path to the library.',
    required=True,
)
@click.option(
    '--api-key',
    help='The osu! API key to use when creating the client.',
    required=True,
)
def run_job(user,
            replay_cache_dir,
            model_cache_dir,
            age,
            library,
            api_key):
    import pathlib

    from lain import ErrorModel
    from lain.train import load_replay_directory
    import pandas as pd
    from slider import Client, Library

    osu_client = Client(Library(library), api_key)
    replays = load_replay_directory(
        pathlib.Path(replay_cache_dir) / user,
        client=osu_client,
        age=pd.Timedelta(age) if age is not None else None,
        save=True,
        verbose=True,
    )

    model = ErrorModel()
    model.fit(replays)

    user_models = pathlib.Path(model_cache_dir) / user
    user_models.mkdir(exist_ok=True)
    model.save_path(user_models)


if __name__ == '__main__':
    run_job()

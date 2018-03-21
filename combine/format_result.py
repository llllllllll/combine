def format_mods(*, double_time, half_time, hidden, hard_rock):
    """Format mods into a short name to render to the user.

    Parameters
    ----------
    double_time : bool
        Is the double time mod used?
    half_time : bool
        Is the half time mod used?
    hidden : bool
        Is the hidden mod used?
    hard_rock : bool
        Is the hard rock mod used?

    Returns
    -------
    formatted : str
        The formatted mod string.
    """
    out = ''
    if double_time:
        out += 'DT'
    elif half_time:
        out += 'HT'

    if hidden:
        out += 'HD'

    if hard_rock:
        out += 'HR'

    return out


def format_link(beatmap):
    """Format a beatmap link to send back to the user.

    Parameters
    ----------
    beatmap : Beatmap
        The beatmap to format.

    Returns
    -------
    link : str
        The link to send back.
    """
    # intentionally add a space at the end, it looks nice in game
    return (
        f'[https://osu.ppy.sh/b/{beatmap.beatmap_id}'
        f' {beatmap.display_name}] '
    )


def format_result(beatmap,
                  mods,
                  prediction,
                  pp_curve=None,
                  *,
                  show_link):
    """Format the results for a beatmap.

    Parameters
    ----------
    beatmap : Beatmap
        The beatmap this is the result for.
    mods : str
        The formatted mods.
    prediction : lain.error_model.Prediction
        The predicted results.
    pp_curve : np.ndarray[float] or None, optional
        The pp curve for 95-100%. If not given, this will not be displayed.
    show_link : bool
        Display the beatmap as a link?

    Returns
    -------
    formatted : str
        The formatted message.
    """
    if prediction is None:
        accuracy = pp = '<unknown>'
    else:
        accuracy = (
            f'{prediction.accuracy_mean * 100:.2f}%'
            f' +- {prediction.accuracy_std * 100:.2f}% (mean +- stddev)'
        )
        pp = (
            f'{prediction.pp_mean:.2f}pp'
            f' +- {prediction.pp_std:.2f}pp (mean +- stddev)'
        )

    if show_link:
        beatmap_display = format_link(beatmap)
    else:
        beatmap_display = beatmap.display_name

    sp = ' ' if mods else ''
    out = (
        f'{beatmap_display} {mods}{sp}predicted high score: {accuracy} | {pp}'
    )
    if pp_curve is not None:
        formatted_curve = (
            f"95-100%: [{', '.join(f'{p:.2f}' for p in pp_curve)}]"
        )
        out += f'; actual: {formatted_curve}pp'

    return out

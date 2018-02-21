combine
=======

IRC bot for suggesting beatmaps based on your replay data.

Try it out by uploading your replays to http://combine.jevnik.moe and then
messaging JoeJev ``!r`` in osu!.

Commands
--------

``!r[ec[ommend]] [MODS] [-MODS]``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Recommend a beatmap to play. This will return a link to the beatmap with your
predicted accuracy and PP.

If ``MODS`` is provided, it will only make recommendations that include the
specified mods. If ``-MODS`` is provided, it will not make recommendations that
include the given mods.

The valid mods are:

- ``hd``: hidden
- ``dt``: double time
- ``hr``: hard rock

Example
```````

.. code-block::

   > !r
   04:20 JoeJev: FELT - New World [Euny's Insane] with DT predicted: 97.04% | 223.32pp
   > !r HD -HR
   04:20 JoeJev: Kohinata Miho (CV: Tsuda Minami) - Naked Romance [Karen's Insane] with DTHD predicted 95.82% | 245.81pp
   > !r hdhr
   04:20 JoeJev: fhana - What a Wonderful World Line [Melencholy] with HDHR predicted: 99.36% | 240.14pp

Note: the second recommendation specified ``HD`` so we ensured that we suggested
a map with ``HD``; however, it also has ``DT`` because we did explicit block
it. The suggestion could not have ``HR`` because we specified ``-HR``.

``!gen-token``
~~~~~~~~~~~~~~

Generate a token to authenticate with the replay upload server.

Example
```````

.. code-block::

   > !gen-token
   04:20 JoeJev: token: <lots of characters>
   04:20 JoeJev: To copy the token, type `/savelog` and then navigate to your osu!/Char directory and open the newest file.

FAQ
---

How does it make recommendations?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When you upload your replays, we extract information about your play and the
beatmap being played. I throw this into a simple neural network to predict your
accuracy based on the map. With the predicted accuracy we can compute the
expected PP for playing a new map with some set of mods applied. The IRC bot
holds a queue of beatmaps to inspect; when you ask for a recommendation, it pops
a map from the queue and checks to see if your expected PP is better than your
average and not unrealistically high. If the map doesn't pass, we pop another
candidate and try again, otherwise we send back the suggestion.

Why do you need to use ``!gen-token``?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Users shouldn't need to make an account to use this service, your osu! account
should sufficiently identify a player. ``gen-token`` creates a unique identifier
for the player based on the name of the user sending the message so that we know
who to associate the replays with. This assumes that being able to log into
bancho as a given user means you are the user.

How is this different from `Tillerino <https://github.com/Tillerino/Tillerinobot/wiki>`_?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tillerino's model is based on clustering users on their top 10 PP earning
plays. Tillerino does not inspect the metadata of the beatmaps at all. Combine
not only looks at the metadata of the maps, it is personally trained to your
particular play style.

Note: I have not actually seen how Tillerino is implemented, this info may not
be 100% accurate.

Why is this called Combine?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The name comes from a `combine harvester
<https://en.wikipedia.org/wiki/Combine_harvester>`_, which is often just called
a combine. A combine is a type of industrial farm equipment for real crops and
the Combine bot is industrial farm equipment for circles.

Why are the recommendations bad?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The predictions are highly dependent on the uploaded replays. If you never play
with hard rock, the predictions for hard rock will be worse than the predictions
for the mods that you do play with. You should inform ``!r`` of your mod
preferences when asking for a recommendation. For example: I personally always
play with hidden, and rarely play with hard rock, so I would ask for
recommendations with ``!r HD -HR``. I have no strong preference for ``DT`` so I
leave it optional.

Other than biases in the input, I am not smart enough to explain why the model
makes the predictions it makes. If you would like to help improve the
performance please contact me or open a PR to `lain
<https://github.com/llllllllll/lain>`_ which is the repo where the actual model
implementation lives.

Developer Usage
---------------

Combine requires Python 3.6.

To install Combine, run ``pip install -r etc/requirements.txt`` and then ``pip
install -e .`` from the repo root.

.. code-block::

   Usage: __main__.py [OPTIONS] COMMAND [ARGS]...

   Options:
     --config YAML-FILE
     --log-level TEXT    The minimum log level to show.
     --help              Show this message and exit.

   Commands:
     check-ip      Check the current ip address against the...
     gen-token     Generate a token for a user.
     irc           Serve the irc bot an enter into a repl where...
     train         Run the model training service.
     train-single  Manually train the model for a given user.
     uploader      Serve the replay upload page.


Fabric
~~~~~~

To make it easy to deploy, combine uses `fabric <http://www.fabfile.org/>`_ to
set up instances. The fabfile will install all of the needed packages and launch
the services under supervisord. The provided fabfile targets an Ubuntu 16.04 LTS
install because that is an easy distro to set up; however, combine runs any any
GNU+Linux system (it is even developed on an Arch Linux machine and then
deployed to Ubuntu with fabric)!.

IRC Bot
~~~~~~~

To host your own IRC bot, copy ``combine/config.yml.template`` to ``config.yml``
and fill in the missing information. Start the bot with ``python -m combine
irc``. In the osu! client, you cannot message yourself so the ``irc`` command
will drop you in a repl where you can send IRC messages to yourself.

Training Locally
~~~~~~~~~~~~~~~~

To train a model for yourself locally, you can use ``python -m combine
train-single --user <user> --replays <replay-dir> --age <replay-age>``. This will train
the neural network against your <age> most recent replays. If age is not
provided, all replays will be used. I have found using the last 6 months (182
days) to be pretty good.

Replay Upload Server
~~~~~~~~~~~~~~~~~~~~

To serve the replay upload service, run ``python -m combine uploader``. This
will run as a flask app behind gunicorn. If you would like to open this service
up to the public (like http://combine.jevnik.moe), I would recommend running it
behind nginx, a simple nginx config file is provided in ``etc/nginx.conf``.

Model Training Service
~~~~~~~~~~~~~~~~~~~~~~

The replay upload server just saves the replays and enqueues a job in the
training queue. The model training service reads from the training queue and
trains a single model at a time. To run this service, run ``python -m combine
train``. This depends on a shared sqlite database with the replay upload server,
but they may be run independent from each other.

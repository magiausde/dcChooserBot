import os
import pickle
import traceback
from random import randint
import logging
import discord
import configparser

from discord.ext import commands

# setup logging
logger = logging.getLogger('dcChooserBot_main')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.CRITICAL)
logformat = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(logformat)
logger.addHandler(ch)

# Get the config
logger.debug("Loading config")
cfg_main = configparser.ConfigParser()
cfg_main.read('chooserbot.ini')

LOG_LEVEL = cfg_main["Logging"]["LogLevel"]
if LOG_LEVEL == "Critical":
    ch.setLevel(logging.CRITICAL)
elif LOG_LEVEL == "Error":
    ch.setLevel(logging.ERROR)
elif LOG_LEVEL == "Warning":
    ch.setLevel(logging.WARNING)
elif LOG_LEVEL == "Info":
    ch.setLevel(logging.INFO)
elif LOG_LEVEL == "Debug":
    ch.setLevel(logging.DEBUG)

MY_TOKEN = cfg_main['Auth']['Token']
logger.debug("MY_TOKEN: " + MY_TOKEN)

RESET_TREASURE = cfg_main.getboolean('Global', 'ResetTreasureEachRound')
logger.debug("RESET_TREASURE: " + str(RESET_TREASURE))
REQUIRE_TREASURE = cfg_main.getboolean('Global', 'TreasureRequiredForChoosing')
logger.debug("REQUIRE_TREASURE: " + str(REQUIRE_TREASURE))

logger.debug("Starting bot")


logger.debug("Preparing bot object")
intents = discord.Intents.default()
intents.guild_messages = True

reference_new = -1

runtime_data = {}

bot = commands.Bot(command_prefix=commands.when_mentioned_or("$"),
                   description='Chooser Bot', status=discord.Status.dnd, intents=intents,
                   activity=discord.Game(name="preferring people since 2023"))


def save_runtime_data():
    global runtime_data
    logger.debug("Saving runtime data")

    original_channels = {}
    original_roles = {}

    # first of all, remove all empty/none attributes
    for server in runtime_data:
        for attrib in list(runtime_data[server]):
            if not runtime_data[server][attrib]:
                logger.debug("Cleanup - removed: " + str(server) + " - " + str(attrib))
                runtime_data[server].pop(attrib)

    # workaround for pickle that cannot save weakref objects (channel object)
    for server in runtime_data:
        for attrib in runtime_data[server]:
            value = runtime_data[server][attrib]
            logger.debug('runtime_data for ' + str(server) + ', ' + attrib + ': ' + str(value))

            if attrib == 'userchannel':
                original_channels[server] = value
                runtime_data[server][attrib] = value.id
            if attrib == 'modrole':
                original_roles[server] = value
                runtime_data[server][attrib] = value.id

    with open('runtimedata.pkl', 'wb+') as f:
        pickle.dump(runtime_data, f, pickle.HIGHEST_PROTOCOL)

    # restore the real channels
    for server in original_channels:
        runtime_data[server]['userchannel'] = original_channels[server]

    # restore the real roles
    for server in original_roles:
        runtime_data[server]['modrole'] = original_roles[server]


async def load_runtime_data():
    global runtime_data
    logger.debug("Loading runtime data")

    if os.path.exists('runtimedata.pkl'):
        with open('runtimedata.pkl', 'rb') as f:
            runtime_data = pickle.load(f)

    # workaround for pickle that cannot save weakref objects (channel object)
    for server in runtime_data:
        for attrib in runtime_data[server]:
            if attrib == 'userchannel':
                channel = await bot.fetch_channel(runtime_data[server][attrib])
                runtime_data[server][attrib] = channel
            if attrib == 'modrole':
                serverobject = bot.get_guild(server)
                modrole = discord.utils.get(serverobject.roles, id=runtime_data[server][attrib])
                runtime_data[server][attrib] = modrole


def set_runtime_data(serverid, key, value):
    logger.debug("SET runtime data - " + str(serverid) + ", " + key + ": " + str(value))
    if serverid not in runtime_data:
        runtime_data[serverid] = {}

    runtime_data[serverid][key] = value
    save_runtime_data()


def get_runtime_data(serverid, key):
    logger.debug("GET runtime data - " + str(serverid) + ", " + key)
    if serverid in runtime_data:
        if key in runtime_data[serverid]:
            return runtime_data[serverid][key]

    logger.debug("No data saved. Returning None")
    return None


def get_context_summary(context):
    return "[" + printuser(context.author) + "@" + context.guild.name + "/" + context.channel.name + "]"


def printuser(user):
    return str(user) + " (" + str(user.id) + ")"


def is_management_permitted(context):
    logger.debug("Checking management permissions for user " + printuser(context.author))
    imp = context.author.guild_permissions.administrator or (
            get_runtime_data(context.guild.id, 'modrole') in context.guild.roles)
    logger.debug("Is permitted? " + str(imp))
    return imp


def get_chosen_unweighted(choose_list, amount):
    logger.debug("Choosing unweighted")
    chosen = []

    if amount > len(choose_list):
        logger.warning(str(amount) + " demanded, but only " + str(len(choose_list)) + " to choose from.")
        amount = len(choose_list)
    else:
        logger.debug(str(amount) + " demanded and " + str(len(choose_list)) + " reacted.")

    logger.debug("Choosing starts")
    while len(chosen) < amount:
        upper_index_boundary = len(choose_list) - 1

        random_index = 0
        if upper_index_boundary > 0:
            random_index = randint(0, upper_index_boundary)

        logger.debug("RandomIndex " + str(random_index) + ", UpperIndexBoundary " + str(upper_index_boundary))
        logger.debug("This user was chosen: " + printuser((choose_list[random_index])))

        chosen.append(choose_list[random_index])
        choose_list.remove(choose_list[random_index])
    logger.debug("Choosing ended")

    return chosen


@bot.event
async def on_ready():
    logger.info(f'Logged on as {bot.user}!')
    await load_runtime_data()
    logger.debug("Ready! Startup completed.")


@bot.command()
async def new(context):
    if is_management_permitted(context):
        global reference_new
        logger.info('New lobby demanded ' + get_context_summary(context))

        userchannel = get_runtime_data(context.guild.id, 'userchannel')
        if userchannel:
            logger.debug("Everything okay. Sending message to react to userchannel")
            reference_new = await userchannel.send('Okay everyone! React with thumbs up if you would like to be added!')
            await reference_new.add_reaction('👍')

            # reset treasure if wanted
            if RESET_TREASURE:
                logger.debug("Resetting treasure as desired and informing user")
                set_runtime_data(context.guild.id, 'treasure', None)
                await context.send("_Cleared the treasure. Don't forget to set a new one._")
        else:
            logger.warning("Userchannel not set. Informing user")
            await context.send("Channel for user messages not set yet. Will not continue! RTFM ;)")


@bot.command()
async def settreasure(context, arg):
    if is_management_permitted(context):
        logger.info('Setting new treasure ' + get_context_summary(context))
        logger.debug("Argument: " + arg)
        set_runtime_data(context.guild.id, 'treasure', arg)
        await context.send("Okay! Treasure set to: " + arg)


@bot.command()
async def setuserchannel(context, arg):
    if is_management_permitted(context):
        logger.info('Setting new userchannel ' + get_context_summary(context))
        try:
            channel = await bot.fetch_channel(arg)
            set_runtime_data(context.guild.id, 'userchannel', channel)
            logger.debug("New user channel was set!")
            await context.send("New user channel: " + channel.name)
        except:
            traceback.print_exc()
            logger.error("Something went wrong while setting new userchannel")
            await context.send("Whoops! Something went wrong while setting a new channel for user messages!")


@bot.command()
async def setmodrole(context, arg):
    # this can definitely only be done by an administrator
    if context.author.guild_permissions.administrator:
        logger.info('Setting new modrole ' + get_context_summary(context))
        modrole = discord.utils.get(context.guild.roles, id=int(arg))
        set_runtime_data(context.guild.id, 'modrole', modrole)
        await getmodrole(context)


@bot.command()
async def getmodrole(context):
    if is_management_permitted(context):
        logger.debug('Modrole requested ' + get_context_summary(context))
        modrole = get_runtime_data(context.guild.id, 'modrole')
        if modrole:
            logger.debug("Modrole is set, id: " + str(modrole.id))
            await context.send("Current modrole: " + modrole.name + "\nAdministrators are always able to use me, too.")
        else:
            logger.debug("Modrole is NOT set")
            await context.send("Currently no modrole is set.\nAdministrators are always able to use me.")


@bot.command()
async def choose(context, arg):
    if is_management_permitted(context):
        logger.info('Choosing demanded ' + get_context_summary(context))

        treasure = get_runtime_data(context.guild.id, 'treasure')
        if REQUIRE_TREASURE and (not treasure):
            logger.warning("Required treasure not set, informing user")
            await context.send("I will not choose! The required treasure is not set! Do this first.")
        else:
            if not arg:
                logger.warning("Argument not present, informing user")
                await context.send("Okay I would choose, but I don't know **how many** to choose. Try again!")
            else:
                if type(reference_new) == discord.message.Message:
                    logger.debug("Getting the up-to-date message users had to react to")
                    cached_reference_new = discord.utils.get(bot.cached_messages, id=reference_new.id)
                    reference_reactions = cached_reference_new.reactions
                    logger.debug("Counting reactions")
                    for reaction in reference_reactions:
                        if reaction.emoji == '👍':
                            thumbsup_users = [user async for user in reaction.users()]
                            thumbsup_users.remove(bot.user)

                            lobby_users_amount = len(thumbsup_users)
                            if lobby_users_amount > 0:
                                logger.info(str(lobby_users_amount) + ' user(s) in lobby: ' + ", ".join(
                                    [printuser(user) for user in thumbsup_users]))

                                try:
                                    arg_int = int(arg)

                                    if arg_int > 0:
                                        chosen = get_chosen_unweighted(thumbsup_users, arg_int)
                                        userchannel = get_runtime_data(context.guild.id, 'userchannel')

                                        # delete the encouraging message
                                        logger.debug("Deleting message to react to")
                                        await reference_new.delete()

                                        logger.debug("Informing users about the chosen ones")
                                        await userchannel.send(
                                            "Alright... So who's it gonna be?\n**I choose you:**\n- <@" + "\n- <@".join(
                                                [str(user.id) + ">" for user in chosen]))

                                        logger.debug("Sending DMs to chosen users")
                                        for user in chosen:
                                            msg = "**Congrats! You were chosen!**"

                                            if treasure:
                                                msg += '\n**Your treasure:** ' + treasure

                                            try:
                                                await user.send(msg)
                                            except discord.errors.Forbidden:
                                                logger.warning(
                                                    "User does not allow DMs, informing context - " + printuser(user))
                                                await context.send("Oh no! <@" + str(
                                                    user.id) + "> was chosen, but does not allow DMs from me. Help!")

                                    else:
                                        logger.warning("Informing user as argument is out of allowed range: " + arg)
                                        await context.send(
                                            "Hey silly! I cannot choose from " + arg + " user(s). **Try again, please!**")
                                except ValueError:
                                    # traceback.print_exc()
                                    logger.warning("Informing user about invalid argument (ValueError): " + arg)
                                    await context.send("This is not something I can work with. Try again!")
                            else:
                                logger.info("No user reacted to message")
                                await context.send("Whoops! No one was in the lobby! I cannot choose from 0 users!")

                            break
                else:
                    logger.info("No choosing active for server, informing user")
                    await context.send(
                        "Hey silly! You can't choose if you didn't even start yet! => try the `new` command!")


bot.run(MY_TOKEN)
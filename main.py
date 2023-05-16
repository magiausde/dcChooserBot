# dcChooserBot - Discord bot for randomly choosing a certain amount of people
# Copyright (C) 2023 Marvin Giesemann
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# https://github.com/magiausde/dcChooserBot

# Generic imports
import configparser
import logging
import os
import pickle
import secrets
import traceback

# Specific imports
import discord
from discord.ext import commands

# version info
VERSION_INFO = '2023-05-15a'

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

# get the desired loglevel from config and set it
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

# load the bot token from config
MY_TOKEN = cfg_main['Auth']['Token']
logger.debug("MY_TOKEN: " + MY_TOKEN)

# load global options from config
# Reset treasure after each round?
RESET_TREASURE = cfg_main.getboolean('Global', 'ResetTreasureEachRound')
logger.debug("RESET_TREASURE: " + str(RESET_TREASURE))

# Require treasure to use choose-command?
REQUIRE_TREASURE = cfg_main.getboolean('Global', 'TreasureRequiredForChoosing')
logger.debug("REQUIRE_TREASURE: " + str(REQUIRE_TREASURE))

# Should multiple benefits be applied?
MULTIPLE_BENEFITS = cfg_main.getboolean('Global', 'MultipleBenefits')
logger.debug("MULTIPLE_BENEFITS: " + str(MULTIPLE_BENEFITS))

logger.debug("Starting bot")

logger.debug("Preparing bot object")
intents = discord.Intents.default()
# we need access to guild messages, otherwise the bot won't get the message content
intents.guild_messages = True

# reference_new will contain the reference to a "new/react" message
reference_new = -1

# runtime_data stores all the settings and will be loaded from the filesystem (if available)
runtime_data = {}

# Setup of the bot
bot = commands.Bot(command_prefix=commands.when_mentioned_or("$"),
                   description='Chooser Bot', status=discord.Status.dnd, intents=intents,
                   activity=discord.Game(name="preferring people since 2023"))


def save_runtime_data():
    """
    Saves the runtime_data variable to the filesystem.
    Usually executed after runtime_data was updated.
    :return: nothing
    """
    global runtime_data
    logger.debug("Saving runtime data")

    # These will contain objects. For saving to the filesystem they get converted to IDs later
    original_channels = {}
    original_roles = {}

    # first of all, remove all empty/none attributes
    for server in runtime_data:
        for attrib in list(runtime_data[server]):
            if not runtime_data[server][attrib]:  # empty
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

    # save runtime data to the filesystem
    with open('runtimedata.pkl', 'wb+') as f:
        pickle.dump(runtime_data, f, pickle.HIGHEST_PROTOCOL)

    # restore the real channels
    for server in original_channels:
        runtime_data[server]['userchannel'] = original_channels[server]

    # restore the real roles
    for server in original_roles:
        runtime_data[server]['modrole'] = original_roles[server]


async def load_runtime_data():
    """
    Loads saved settings from the filesystem into runtime_data.
    Usually only executed on startup.
    :return: nothing
    """
    global runtime_data
    logger.debug("Loading runtime data")

    if os.path.exists('runtimedata.pkl'):  # if data was saved before
        with open('runtimedata.pkl', 'rb') as f:
            runtime_data = pickle.load(f)

    # workaround for pickle that cannot save weakref objects (channel object)
    # turn IDs into the corresponding objects
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
    """
    Sets and saves a new value for runtime_data.
    :param serverid: The server's id this key and value belongs to
    :param key: The key of the value
    :param value: Value to be saved into runtime_data
    :return: nothing
    """
    logger.debug("SET runtime data - " + str(serverid) + ", " + key + ": " + str(value))
    # Create empty dict for server, if it does not exist yet
    if serverid not in runtime_data:
        runtime_data[serverid] = {}

    # Store the value and save
    runtime_data[serverid][key] = value
    save_runtime_data()


def get_runtime_data(serverid, key):
    """
    Returns a value from runtime_data
    :param serverid: The server's id the key belongs to
    :param key: Key that states which data to retrieve
    :return: Stored value or None if nothing stored
    """
    logger.debug("GET runtime data - " + str(serverid) + ", " + key)
    if serverid in runtime_data:
        if key in runtime_data[serverid]:
            return runtime_data[serverid][key]

    logger.debug("No data saved. Returning None")
    return None  # if nothing is set


def set_rolebenefit(serverid, roleid, benefit):
    """
    Internal method for saving a role's benefit value to runtime_data
    :param serverid: Server's id the benefit belongs to
    :param roleid: The role id where the benefit was set for
    :param benefit: Amount of benefit to store for the role
    :return: nothing
    """
    logger.debug("SET role-benefit - " + str(serverid) + ", " + str(roleid) + ": " + str(benefit))
    # create empty dict for server, if it does not exist yet
    if serverid not in runtime_data:
        runtime_data[serverid] = {}

    # Check if benefit to be set or deleted
    if benefit > 0:
        if 'rolebenefits' not in runtime_data[serverid]:
            logger.debug('rolebenefits not yet in runtime_data for server, creating dict')
            runtime_data[serverid]['rolebenefits'] = {}

        runtime_data[serverid]['rolebenefits'][roleid] = benefit
    else:
        runtime_data[serverid]['rolebenefits'].pop(roleid)

    save_runtime_data()


def get_context_summary(context):
    """
    Provides a context summary, mainly used by logging.
    Summary consists of the user, guild/server name and channel name
    :param context: Context object for which to get the summary for
    :return: String with summary of context
    """
    # Example - [RandomUser#1234@MyCoolServer/botcmnd]
    return "[" + printuser(context.author) + "@" + context.guild.name + "/" + context.channel.name + "]"


def printuser(user):
    """
    Returns detailed identification of a User-object.
    This includes the username, discriminator and also the user-id
    :param user: User-object to get the identification for
    :return: String with detailed identification of User-object.
    """
    # Example - RandomUser#123 (12345678987654321)
    return str(user) + " (" + str(user.id) + ")"


def is_management_permitted(context):
    """
    Checks if a user (from context) is allowed to perform management-actions.
    This is True if the user is a server administrator or modrole member.
    :param context: Context to check
    :return: if the user (from context) is allowed to perform management-actions
    """
    logger.debug("Checking management permissions for user " + printuser(context.author))
    imp = context.author.guild_permissions.administrator or (
            get_runtime_data(context.guild.id, 'modrole') in context.guild.roles)
    logger.debug("Is permitted? " + str(imp))
    return imp


def log_probabilities(users_list):
    """
    Debug-method which calculates each user's probability of being chosen.
    :param users_list: List of User-objects to count/calculate
    :return: nothing
    """
    logger.debug("Logging the probabilities for this turn:")

    counts = {}

    # count how often the user is in the users_list
    for user in users_list:
        if user.id in counts:
            counts[user.id] += 1
        else:
            counts[user.id] = 1

    # calculate the probability for each user
    # Example - 16.6667% 1/6: 12345678987654321
    for entry in counts:
        logger.debug(str(round(counts[entry] / len(users_list) * 100, 4)) + "% " + str(counts[entry]) + "/" + str(
            len(users_list)) + ": " + str(entry))


def get_maximum_benefit(member, benefit_roles):
    """
    Checks all roles a user has and returns the maximum benefit found.
    :param member: Which member to check for
    :param benefit_roles: List of roles with benefits set (get them from runtime_data!)
    :return: The maximum benefit found for the given user
    """
    logger.debug("Checking the maximum single benefit for " + printuser(member))

    temp_max = 0  # the maximum benefit found
    for member_role in member.roles:  # go through all roles a member has
        if member_role.id in benefit_roles:  # if this role has benefits
            benefit = benefit_roles[member_role.id]  # get the benefit
            logger.debug(printuser(member) + " role-benefit for " + str(member_role) + ": " + str(benefit))

            if benefit > temp_max:  # is the benefit higher than the earlier ones?
                temp_max = benefit

    logger.debug("Maximum single benefit is " + str(temp_max))
    return temp_max


async def get_chosen_weighted(choose_list, amount, server):
    """
    Chooses the people and also applies benefits (if available).
    :param choose_list: List of users to choose from
    :param amount: How many people to choose
    :param server: The server where choosing takes place
    :return: List of users that were chosen (unique users)
    """
    logger.debug("Choosing weighted")
    chosen = []  # will contain a list of users that were chosen

    # check if more users were demanded than we can choose from
    if amount > len(choose_list):
        logger.warning(str(amount) + " demanded, but only " + str(len(choose_list)) + " to choose from.")
        amount = len(choose_list)
    else:
        logger.debug(str(amount) + " demanded and " + str(len(choose_list)) + " reacted.")

    # go through all users, go through all of their server roles and apply role-benefit
    logger.debug("choose_list before: " + ", ".join([printuser(user) for user in choose_list]))
    logger.debug("Applying benefits to users")
    benefit_roles = get_runtime_data(server.id, 'rolebenefits')

    if benefit_roles:  # only do this if there are any benefit roles set for this server
        # we need to keep a copy of the original list
        # else we would end with an infinite loop as users get added
        choose_list_original = choose_list.copy()

        for user in choose_list_original:  # for every user that would like to be chosen
            # to check the roles, we have to get the Member object, as we only have User objects
            member = await server.fetch_member(user.id)

            if member:  # did we get a member object? This is False if the User is not a member of the server (anymore)
                if MULTIPLE_BENEFITS:  # apply benefits from multiple roles or only the highest one?
                    logger.debug("Multiple benefits will be applied")

                    for member_role in member.roles:  # for every role the member has on this server
                        if member_role.id in benefit_roles:  # if a benefit is set for this role
                            benefit = benefit_roles[member_role.id]  # get the benefit for this role
                            logger.debug(
                                printuser(user) + " role-benefit for " + str(member_role) + ": " + str(benefit))

                            # add the user as often as the role has set as a benefit
                            for _ in range(benefit):
                                logger.debug("Adding user once more to choose_list")
                                choose_list.append(user)
                else:  # only apply the highest benefit a user has
                    logger.debug("Only the highest benefit will be applied")
                    benefit = get_maximum_benefit(member, benefit_roles)

                    # add the user as often as the role has set as a benefit
                    for _ in range(benefit):
                        logger.debug("Adding user once more to choose_list")
                        choose_list.append(user)
            else:  # user NOT member of the server (anymore)
                logger.warning("User is no longer member of server, benefits not applied: " + printuser(user))
    else:  # no benefit roles set for this server
        logger.debug("No benefit roles set. Skipping.")

    logger.debug("Applying done")
    logger.debug("choose_list after: " + ", ".join([printuser(user) for user in choose_list]))

    logger.debug("Choosing starts")
    # as long as we do not have enough users chosen
    while len(chosen) < amount:
        # Log the probabilities (for debugging reasons only)
        log_probabilities(choose_list)

        # Highest index to choose
        upper_index_boundary = len(choose_list) - 1

        # random_index defaults to zero...
        random_index = 0
        # ... in case there is only one user left that can be chosen
        if upper_index_boundary > 0:
            # using secrets as random was not random enough
            random_index = secrets.randbelow(upper_index_boundary + 1)

        # get the random user object
        chosen_user = choose_list[random_index]

        logger.debug("RandomIndex " + str(random_index) + ", UpperIndexBoundary was " + str(upper_index_boundary))
        logger.debug("This user was chosen: " + printuser(chosen_user))

        # add user to list of chosen users (will be returned later)
        chosen.append(chosen_user)

        # loop through the list to remove the chosen user entirely - else he could be chosen multiple times
        for entry in list(choose_list):
            if entry == chosen_user:
                choose_list.remove(chosen_user)
                logger.debug("Removed " + printuser(chosen_user) + " from choose_list")

    logger.debug("Choosing ended")

    return chosen


@bot.event
async def on_ready():
    """
    Called when the Discord bot is ready.
    Will load saved runtime_data (if available).
    :return:
    """
    logger.info(f'Logged on as {bot.user}!')
    # Now that the bot is ready, we can load runtime_data
    # this is a prerequisite as channel and role objects will be loaded
    await load_runtime_data()
    logger.debug("Ready! Startup completed.")


@bot.command()
async def new(context):
    """
    Bot command to start a new choosing-round.
    Posts a message to react to the public channel
    :param context: Command context
    :return: nothing
    """
    if is_management_permitted(context):
        global reference_new
        logger.info('New lobby demanded ' + get_context_summary(context))

        userchannel = get_runtime_data(context.guild.id, 'userchannel')  # get the public/user channel for this server
        if userchannel:  # if the channel is set
            logger.debug("Everything okay. Sending message to react to userchannel")
            # send message to public channel and also react to make it more convenient for the users
            reference_new = await userchannel.send('Okay everyone! React with thumbs up if you would like to be added!')
            await reference_new.add_reaction('👍')

            # reset treasure if wanted
            if RESET_TREASURE:
                logger.debug("Resetting treasure as desired and informing user")
                set_runtime_data(context.guild.id, 'treasure', None)
                await context.send("_Cleared the treasure. Don't forget to set a new one._")
        else:  # public/user channel NOT set for this server
            logger.warning("Userchannel not set. Informing user")
            await context.send("Channel for user messages not set yet. Will not continue! RTFM ;)")


@bot.command()
async def settreasure(context, arg):
    """
    Bot command to set the treasure on a server.
    :param context: Command context
    :param arg: Treasure to set
    :return: nothing
    """
    if is_management_permitted(context):
        logger.info('Setting new treasure ' + get_context_summary(context))
        logger.debug("Argument: " + arg)
        set_runtime_data(context.guild.id, 'treasure', arg)
        await context.send("Okay! Treasure set to: " + arg)


@bot.command()
async def setuserchannel(context, arg):
    """
    Bot command to set the public/user channel on a server.
    :param context: Command context
    :param arg: Channel id to set
    :return: nothing
    """
    if is_management_permitted(context):
        logger.info('Setting new userchannel ' + get_context_summary(context))

        try:
            channel = await bot.fetch_channel(arg)  # get the channel object using the provided ID
            set_runtime_data(context.guild.id, 'userchannel', channel)  # update runtime_data
            logger.debug("New user channel was set!")
            await context.send("New user channel: " + channel.name)  # informing user
        except:
            traceback.print_exc()
            logger.error("Something went wrong while setting new userchannel")
            await context.send("Whoops! Something went wrong while setting a new channel for user messages!")


@bot.command()
async def setmodrole(context, arg):
    """
    Bot command to set the modrole on a server.
    :param context: Command context
    :param arg: Modrole id to set
    :return: nothing
    """
    # this can definitely only be done by an administrator
    if context.author.guild_permissions.administrator:
        logger.info('Setting new modrole ' + get_context_summary(context))
        modrole = discord.utils.get(context.guild.roles, id=int(arg))  # get the role object using the provided ID
        set_runtime_data(context.guild.id, 'modrole', modrole)  # update runtime_data
        await getmodrole(context)  # list the currently configured roles


@bot.command()
async def getmodrole(context):
    """
    Bot command to get the modrole set on a server.
    Result will be sent to the context (message will be posted).
    :param context: Command context
    :return: nothing
    """
    if is_management_permitted(context):
        logger.debug('Modrole requested ' + get_context_summary(context))
        modrole = get_runtime_data(context.guild.id, 'modrole')  # get the role for this server from runtime_data
        if modrole:  # if a modrole is set for this server
            logger.debug("Modrole is set, id: " + str(modrole.id))
            await context.send("Current modrole: " + modrole.name + "\nAdministrators are always able to use me, too.")
        else:  # if a modrole is NOT set for this server
            logger.debug("Modrole is NOT set")
            await context.send("Currently no modrole is set.\nAdministrators are always able to use me.")


@bot.command()
async def setbenefit(context, raw_roleid, raw_benefit):
    """
    Bot command to set a benefit for a role on a server.
    :param context: Command context
    :param raw_roleid: Role id where the benefit will be apllied to
    :param raw_benefit: The benefit value
    :return: nothing
    """
    if is_management_permitted(context):
        logger.debug('User setting benefit ' + get_context_summary(context))

        # benefit must be greater than zero and a valid integer
        try:
            roleid = int(raw_roleid)  # string to integer (could cause exception in this try-block)
            benefit = int(raw_benefit)  # string to integer (could cause exception in this try-block)
            if (roleid > 0) and (benefit > -1):  # must be valid role id and useful benefit
                # first of all check, if the role exists
                role = context.guild.get_role(roleid)

                if role:  # role exists
                    if benefit > 99:  # very high benefit, might impact performance with lots of people
                        logger.warning("User set benefit > 99, informing about possible performance impact")
                        await context.send(
                            "**Please note that benefits over 100 are not recommended because of performance reasons!**")

                    logger.debug('Everything okay, passing data to internal save method')
                    set_rolebenefit(context.guild.id, roleid, benefit)
                    await listbenefits(context)
                else:  # role does not exist on this server
                    logger.warning("User passed an invalid role, informing")
                    await context.send("The role you entered does not exist on this server!")
            else:  # invalid arguments provided
                logger.warning("User passed invalid integer, informing user")
                await context.send(
                    "Please check you entered valid values for the role id and the benefit!")
        except ValueError:  # usually when raw_roleid or raw_benefit weren't integers
            logger.warning("User passed invalid argument (ValueError), informing user")
            await context.send("Whoops! Something went wrong. Did you pass valid numbers to me?")


@bot.command()
async def listbenefits(context):
    """
    Bot command to get the benefits set on a server.
    Result will be sent to the context (message will be posted).
    :param context: Command context
    :return: nothing
    """
    if is_management_permitted(context):
        benefitroles = get_runtime_data(context.guild.id, 'rolebenefits')  # get benefit roles for this server

        summary = "These are the benefits currently configured for " + str(context.guild) + ":"
        if benefitroles:  # if benefit roles are set for this server
            for benefitroleid in benefitroles:  # for every role that has a benefit set
                benefit_role = discord.utils.get(context.guild.roles, id=benefitroleid)  # get the role
                summary += "\n- " + str(benefit_role) + ": " + str(benefitroles[benefitroleid])  # add benefit info
        else:  # server has NO benefit roles set
            summary += '\n- None configured!'

        # send summary to user/context
        await context.send(summary)


@bot.command()
async def choose(context, arg):
    """
    Bot command to start the choosing.
    Takes care of all relevant choosing parts, like getting a list of chosen users and also informing them.
    Also checks for some requirements.
    :param context: Command context
    :param arg: How many to choose
    :return: nothing
    """
    if is_management_permitted(context):
        logger.info('Choosing demanded ' + get_context_summary(context))

        treasure = get_runtime_data(context.guild.id, 'treasure')  # get treasure set for this server
        if REQUIRE_TREASURE and (not treasure):  # if setting TreasureRequiredForChoosing = 1, but none set yet
            logger.warning("Required treasure not set, informing user")
            await context.send("I will not choose! The required treasure is not set! Do this first.")
        else:  # treasure set or not required
            if not arg:  # if command misses argument how many users to choose
                logger.warning("Argument not present, informing user")
                await context.send("Okay I would choose, but I don't know **how many** to choose. Try again!")
            else:  # user told us how many to choose
                if type(reference_new) == discord.message.Message:  # if reference is valid
                    # we have to get the cached message, otherwise it appears as no one had reacted to it
                    logger.debug("Getting the up-to-date message users had to react to")
                    cached_reference_new = discord.utils.get(bot.cached_messages, id=reference_new.id)

                    if cached_reference_new:  # if the cached message could be retrieved
                        reference_reactions = cached_reference_new.reactions  # get the reactions to the message
                        logger.debug("Counting reactions")

                        for reaction in reference_reactions:  # for each reaction users added to the message
                            if reaction.emoji == '👍':  # we are only interested in the thumbs up reaction
                                # convert the result of reaction.users() to a list we can work with
                                # caution! we get User objects here, not Members!
                                thumbsup_users = [user async for user in reaction.users()]
                                thumbsup_users.remove(bot.user)

                                lobby_users_amount = len(thumbsup_users)  # how many users reacted with thumbs up
                                if lobby_users_amount > 0:  # if users reacted at all
                                    logger.info(str(lobby_users_amount) + ' user(s) in lobby: ' + ", ".join(
                                        [printuser(user) for user in thumbsup_users]))

                                    try:
                                        arg_int = int(arg)  # how many users to choose - try converting it to int

                                        if arg_int > 0:  # check if at least one user should be chosen
                                            logger.debug("Sending info message to context")
                                            modmsg = await context.send(
                                                "Choosing and informing " + str(arg_int) + " user(s). Please wait...")

                                            # use the choosing function to select the users
                                            chosen = await get_chosen_weighted(thumbsup_users, arg_int, context.guild)

                                            # delete the encouraging message
                                            logger.debug("Deleting message to react to")
                                            await reference_new.delete()

                                            logger.debug("Informing users about the chosen ones")
                                            # post result to the public chanel
                                            userchannel = get_runtime_data(context.guild.id, 'userchannel')
                                            await userchannel.send(
                                                "Alright... So who's it gonna be?\n**I choose you:**\n- <@" + "\n- <@".join(
                                                    [str(user.id) + ">" for user in chosen]))

                                            # send individual DMs to the chosen users
                                            logger.debug("Sending DMs to chosen users")
                                            for user in chosen:  # for every user that was chosen
                                                msg = "**Congrats! You were chosen!**"

                                                if treasure:  # send the treasure, if it is set for this server
                                                    msg += '\n**Your treasure:** ' + treasure

                                                try:
                                                    await user.send(msg)
                                                except discord.errors.Forbidden:
                                                    logger.warning(
                                                        "User does not allow DMs, informing context - " + printuser(
                                                            user))
                                                    await context.send("Oh no! <@" + str(
                                                        user.id) + "> was chosen, but does not allow DMs from me. Help!")

                                            logger.debug("Choosing done - editing info message")
                                            await modmsg.edit(content="Done! => <#" + str(userchannel.id) + ">")
                                        else:  # user told us to choose zero or fewer people - senseless!
                                            logger.warning("Informing user as argument is out of allowed range: " + arg)
                                            await context.send(
                                                "Hey silly! I cannot choose from " + arg + " user(s). **Try again, please!**")
                                    except ValueError:  # "how many users to choose" was not a valid integer
                                        logger.warning("Informing user about invalid argument (ValueError): " + arg)
                                        await context.send("This is not something I can work with. Try again!")
                                else:  # no users reacted to the message
                                    logger.info("No user reacted to message")
                                    await context.send("Whoops! No one was in the lobby! I cannot choose from 0 users!")

                                # since we "found" the "thumbs up" reaction, we do not need to look any further. break.
                                break
                    else:  # reference message was not found - probably it was deleted
                        logger.warning(
                            "Message to react to disappeared - choosing already ended or message was deleted, informing user")
                        await context.send(
                            "Choosing already done or my message to react to was deleted. Start a new round!")
                else:  # no round active
                    logger.info("No choosing active for server, informing user")
                    await context.send(
                        "Hey silly! You can't choose if you didn't even start yet! => try the `new` command!")


@bot.command()
async def version(context):
    """
    Bot command to get the bot version.
    Result will be sent to the context (message will be posted).
    :param context: Command context
    :return: nothing
    """
    await context.send(
        "**This is dcChooserBot, version " + VERSION_INFO +
        "**\nI am an open source project, initiated by magiausde! Find me at https://github.com/magiausde/dcChooserBot")

# start the bot!
bot.run(MY_TOKEN)

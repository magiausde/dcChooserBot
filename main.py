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
from discord import app_commands

# version info
VERSION_INFO = '2023-05-23a'

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

# Development settings
# Get the development server ID, if existent
DEV_GUILD_ID = cfg_main.getint("Dev", "DevGuildID", fallback=None)

logger.debug("Starting bot")

# runtime_data stores all the settings and will be loaded from the filesystem (if available)
runtime_data = {}
# if a user does not allow bot messages initially, these will be sent when the user messages the bot once via DM
dm_backlog = {}


class ChooserClient(discord.Client):
    def __init__(self, *, intents: discord.Intents, status: discord.Status, activity):
        super().__init__(intents=intents, status=status, activity=activity)
        # Setup the command tree
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # If DEV_GUILD_ID is set, we sync the command tree to that server.
        # This makes development easier,
        # as we do not have to wait up to an hour before the commands are synced globally.
        if DEV_GUILD_ID:
            logger.debug("A server for development purposes is set - syncing commands")
            dev_guild = discord.Object(id=DEV_GUILD_ID)
            self.tree.copy_global_to(guild=dev_guild)
            await self.tree.sync(guild=dev_guild)
        else:
            logger.debug("Development server not set.")


logger.debug("Preparing bot object")
myIntents = discord.Intents.default()

# Setup of the bot
client = ChooserClient(intents=myIntents, status=discord.Status.dnd,
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
    original_references = {}

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
            if attrib == 'reference_new':
                original_references[server] = value
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

    # restore the real references
    for server in original_roles:
        runtime_data[server]['reference_new'] = original_references[server]


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
        if "userchannel" in runtime_data[server]:
            channel = await client.fetch_channel(runtime_data[server]["userchannel"])
            if channel:
                logger.debug("Userchannel fetched successfully!")
            else:
                logger.warning("Userchannel failed to fetch!")
            runtime_data[server]["userchannel"] = channel
        if "modrole" in runtime_data[server]:
            serverobject = client.get_guild(server)
            modrole = discord.utils.get(serverobject.roles, id=runtime_data[server]["modrole"])
            if modrole:
                logger.debug("Modrole fetched successfully!")
            else:
                logger.warning("Modrole failed to fetch!")
            runtime_data[server]["modrole"] = modrole
        if "reference_new" in runtime_data[server] and channel:
            messageobject = await channel.fetch_message(runtime_data[server]["reference_new"])
            if messageobject:
                logger.debug("Reference fetched successfully!")
            else:
                logger.warning("Reference failed to fetch!")
            runtime_data[server]["reference_new"] = messageobject

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


def get_interaction_summary(interaction: discord.Interaction):
    """
    Provides a interaction summary, mainly used by logging.
    Summary consists of the user, guild/server name and channel name
    :param interaction: interaction object for which to get the summary for
    :return: String with summary of interaction
    """
    # Example - [RandomUser#1234@MyCoolServer/botcmnd]
    return "[" + printuser(interaction.user) + "@" + interaction.guild.name + "/" + interaction.channel.name + "]"


def printuser(user):
    """
    Returns detailed identification of a User-object.
    This includes the username, discriminator and also the user-id
    :param user: User-object to get the identification for
    :return: String with detailed identification of User-object.
    """
    # Example - RandomUser#123 (12345678987654321)
    return str(user) + " (" + str(user.id) + ")"


def is_management_permitted(interaction: discord.Interaction):
    """
    Checks if a user (from interaction) is allowed to perform management-actions.
    This is True if the user is a server administrator or modrole member.
    :param interaction: interaction to check
    :return: if the user (from interaction) is allowed to perform management-actions
    """
    logger.debug("Checking management permissions for user " + printuser(interaction.user))
    imp = interaction.user.guild_permissions.administrator or (
            get_runtime_data(interaction.guild.id, 'modrole') in interaction.user.roles)
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


@client.event
async def on_ready():
    """
    Called when the Discord bot is ready.
    Will load saved runtime_data (if available).
    :return:
    """
    logger.info(f'Logged on as {client.user}!')
    # Now that the bot is ready, we can load runtime_data
    # this is a prerequisite as channel and role objects will be loaded
    await load_runtime_data()
    logger.debug("Ready! Startup completed.")


@client.tree.command()
async def new(interaction: discord.Interaction):
    """
    Start a new choosing-round.
    Posts a message to react to the public channel.
    """
    if is_management_permitted(interaction):
        global reference_new
        logger.info('New lobby demanded ' + get_interaction_summary(interaction))

        userchannel = get_runtime_data(interaction.guild.id,
                                       'userchannel')  # get the public/user channel for this server
        if userchannel:  # if the channel is set
            # reset treasure if wanted
            additional = ""
            if RESET_TREASURE:
                logger.debug("Resetting treasure as desired and informing user")
                set_runtime_data(interaction.guild.id, 'treasure', None)
                additional = "\n_Cleared the treasure. Don't forget to set a new one._"

            logger.debug("Everything okay. Sending message to react to userchannel")
            # send message to public channel and also react to make it more convenient for the users
            reference_new = await userchannel.send('Okay everyone! React with thumbs up if you would like to be added!')
            await reference_new.add_reaction('👍')
            await interaction.response.send_message("Okay, message posted to <#" + str(userchannel.id) + ">" + additional)
            set_runtime_data(interaction.guild.id, "reference_new", reference_new)
        else:  # public/user channel NOT set for this server
            logger.warning("Userchannel not set. Informing user")
            await interaction.response.send_message("Channel for user messages not set yet. Will not continue! RTFM ;)")
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
@app_commands.describe(
    treasure='Treasure to set (e.g. a link or code)'
)
async def settreasure(interaction: discord.Interaction, treasure: str):
    """
    Set the treasure - Users will receive this via DM if they are chosen.
    """
    if is_management_permitted(interaction):
        logger.info('Setting new treasure ' + get_interaction_summary(interaction))
        logger.debug("Argument: " + treasure)
        set_runtime_data(interaction.guild.id, 'treasure', treasure)
        await interaction.response.send_message("Okay! Treasure set to: " + treasure)
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
@app_commands.describe(
    channel='ID of channel to set as the user channel'
)
async def setuserchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    """
    Set the public/user channel for this server.
    """
    if is_management_permitted(interaction):
        logger.info('Setting new userchannel ' + get_interaction_summary(interaction))

        try:
            set_runtime_data(interaction.guild.id, 'userchannel', channel)  # update runtime_data
            logger.debug("New user channel was set!")
            await interaction.response.send_message("New user channel: " + channel.name)  # informing user
        except:
            traceback.print_exc()
            logger.error("Something went wrong while setting new userchannel")
            await interaction.response.send_message(
                "Whoops! Something went wrong while setting a new channel for user messages!")
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
@app_commands.describe(
    modrole='ID of role to set as the moderator role'
)
async def setmodrole(interaction: discord.Interaction, modrole: discord.Role):
    """
    Set the modrole for your server. Members of the modrole are able to use ChooserBot.
    """
    # this can definitely only be done by an administrator
    if interaction.user.guild_permissions.administrator:
        logger.info('Setting new modrole ' + get_interaction_summary(interaction))
        set_runtime_data(interaction.guild.id, 'modrole', modrole)  # update runtime_data
        await interaction.response.send_message("Updated modrole. View the configured one with /getmodrole")
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
async def getmodrole(interaction: discord.Interaction):
    """
    Shows you the currently configured modrole.
    """
    if is_management_permitted(interaction):
        logger.debug('Modrole requested ' + get_interaction_summary(interaction))
        modrole = get_runtime_data(interaction.guild.id, 'modrole')  # get the role for this server from runtime_data
        if modrole:  # if a modrole is set for this server
            logger.debug("Modrole is set, id: " + str(modrole.id))
            await interaction.response.send_message(
                "Current modrole: " + modrole.name + "\nAdministrators are always able to use me, too.")
        else:  # if a modrole is NOT set for this server
            logger.debug("Modrole is NOT set")
            await interaction.response.send_message(
                "Currently no modrole is set.\nAdministrators are always able to use me.")
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
@app_commands.rename(
    benefitrole='role'
)
@app_commands.describe(
    benefitrole='Role to set the benefit for',
    benefit='Benefit value'
)
async def setbenefit(interaction: discord.Interaction, benefitrole: discord.Role, benefit: int):
    """
    Set the benefit for a role. Set to 0 to remove.
    """
    if is_management_permitted(interaction):
        logger.debug('User setting benefit ' + get_interaction_summary(interaction))

        # benefit must be greater than zero and a valid integer
        try:
            if benefit > -1:  # must be valid role id and useful benefit
                # first of all check, if the role exists

                if benefitrole:  # role exists
                    logger.debug('Everything okay, passing data to internal save method')
                    set_rolebenefit(interaction.guild.id, benefitrole.id, benefit)

                    if benefit > 99:  # very high benefit, might impact performance with lots of people
                        logger.warning("User set benefit > 99, informing about possible performance impact")
                        await interaction.response.send_message(
                            "**Please note that benefits over 100 are not recommended because of performance "
                            "reasons!**\nUpdated benefit. View all benefits with /listbenefits")
                    else:
                        await interaction.response.send_message("Updated benefit. View all benefits with /listbenefits")
                else:  # role does not exist on this server
                    logger.warning("User passed an invalid role, informing")
                    await interaction.response.send_message("The role you entered does not exist on this server!")
            else:  # invalid arguments provided
                logger.warning("User passed invalid integer, informing user")
                await interaction.response.send_message(
                    "Please check you entered valid values for the role id and the benefit!")
        except ValueError:  # usually when raw_roleid or raw_benefit weren't integers
            logger.warning("User passed invalid argument (ValueError), informing user")
            await interaction.response.send_message("Whoops! Something went wrong. Did you pass valid numbers to me?")
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
async def listbenefits(interaction: discord.Interaction):
    """
    List the benefits on this server
    """
    if is_management_permitted(interaction):
        benefitroles = get_runtime_data(interaction.guild.id, 'rolebenefits')  # get benefit roles for this server

        summary = "These are the benefits currently configured for " + str(interaction.guild) + ":"
        if benefitroles:  # if benefit roles are set for this server
            for benefitroleid in benefitroles:  # for every role that has a benefit set
                benefit_role = discord.utils.get(interaction.guild.roles, id=benefitroleid)  # get the role
                summary += "\n- " + str(benefit_role) + ": " + str(benefitroles[benefitroleid])  # add benefit info
        else:  # server has NO benefit roles set
            summary += '\n- None configured!'

        # send summary to user/interaction
        await interaction.response.send_message(summary)
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.tree.command()
@app_commands.describe(
    amount='How many users to choose'
)
async def choose(interaction: discord.Interaction, amount: int):
    """
    Choose a specified amount of users.
    """
    # Bot command to start the choosing.
    # Takes care of all relevant choosing parts, like getting a list of chosen users and also informing them.
    # Also checks for some requirements.

    if is_management_permitted(interaction):
        logger.info('Choosing demanded ' + get_interaction_summary(interaction))

        treasure = get_runtime_data(interaction.guild.id, 'treasure')  # get treasure set for this server
        if REQUIRE_TREASURE and (not treasure):  # if setting TreasureRequiredForChoosing = 1, but none set yet
            logger.warning("Required treasure not set, informing user")
            await interaction.response.send_message(
                "I will not choose! The required treasure is not set! Do this first.")
        else:  # treasure set or not required
            if not amount:  # if command misses argument how many users to choose
                logger.warning("Argument not present, informing user")
                await interaction.response.send_message(
                    "Okay I would choose, but I don't know **how many** to choose. Try again!")
            else:  # user told us how many to choose
                reference_new = get_runtime_data(interaction.guild.id, "reference_new")
                if type(reference_new) == discord.message.Message:  # if reference is valid
                    # we have to get the cached message, otherwise it appears as no one had reacted to it
                    logger.debug("Getting the up-to-date message users had to react to")
                    cached_reference_new = discord.utils.get(client.cached_messages, id=reference_new.id)
                    # fallback if no cache available (e.g. restart of bot)
                    if not cached_reference_new:
                        logger.debug("Cached message not available, fetching")
                        cached_reference_new = await reference_new.channel.fetch_message(reference_new.id)

                    if cached_reference_new:  # if the cached message could be retrieved
                        reference_reactions = cached_reference_new.reactions  # get the reactions to the message
                        logger.debug("Counting reactions")

                        for reaction in reference_reactions:  # for each reaction users added to the message
                            if reaction.emoji == '👍':  # we are only interested in the thumbs up reaction
                                # convert the result of reaction.users() to a list we can work with
                                # caution! we get User objects here, not Members!
                                thumbsup_users = [user async for user in reaction.users()]
                                thumbsup_users.remove(client.user)

                                lobby_users_amount = len(thumbsup_users)  # how many users reacted with thumbs up
                                if lobby_users_amount > 0:  # if users reacted at all
                                    logger.info(str(lobby_users_amount) + ' user(s) in lobby: ' + ", ".join(
                                        [printuser(user) for user in thumbsup_users]))

                                    try:
                                        arg_int = int(amount)  # how many users to choose - try converting it to int

                                        if arg_int > 0:  # check if at least one user should be chosen
                                            logger.debug("Sending info message to interaction")
                                            await interaction.response.send_message(
                                                "Choosing and informing " + str(arg_int) + " user(s). Please wait...")

                                            # use the choosing function to select the users
                                            chosen = await get_chosen_weighted(thumbsup_users, arg_int,
                                                                               interaction.guild)

                                            # delete the encouraging message
                                            logger.debug("Deleting message to react to")
                                            await reference_new.delete()

                                            logger.debug("Informing users about the chosen ones")
                                            # post result to the public chanel
                                            userchannel = get_runtime_data(interaction.guild.id, 'userchannel')
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
                                                        "User does not allow DMs, informing interaction - " + printuser(
                                                            user))
                                                    dm_backlog[user.id] = msg
                                                    await userchannel.send(
                                                        "<@" + str(user.id) + "> I am not allowed to send you a "
                                                                              "message (Right click on the server "
                                                                              "icon -> Privacy -> \"Direct messages\" "
                                                                              "is not enabled). If you enable it (at "
                                                                              "least for a short time) and send me a "
                                                                              "DM, I will inform you, too.")

                                            logger.debug("Choosing done - editing info message")
                                            await interaction.edit_original_response(
                                                content="Done! 🡺 <#" + str(userchannel.id) + ">")
                                        else:  # user told us to choose zero or fewer people - senseless!
                                            logger.warning(
                                                "Informing user as argument is out of allowed range: " + str(amount))
                                            await interaction.response.send_message(
                                                "Hey silly! I cannot choose from " + str(
                                                    amount) + " user(s). **Try again, please!**")
                                    except ValueError:  # "how many users to choose" was not a valid integer
                                        logger.warning(
                                            "Informing user about invalid argument (ValueError): " + str(amount))
                                        await interaction.response.send_message(
                                            "This is not something I can work with. Try again!")
                                else:  # no users reacted to the message
                                    logger.info("No user reacted to message")
                                    await interaction.response.send_message(
                                        "Whoops! No one was in the lobby! I cannot choose from 0 users!")

                                # since we "found" the "thumbs up" reaction, we do not need to look any further. break.
                                break
                    else:  # reference message was not found - probably it was deleted
                        logger.warning(
                            "Message to react to disappeared - choosing already ended or message was deleted, informing user")
                        await interaction.response.send_message(
                            "Choosing already done or my message to react to was deleted. Start a new round!")
                else:  # no round active
                    logger.info("No choosing active for server, informing user")
                    await interaction.response.send_message(
                        "Hey silly! You can't choose if you didn't even start yet! 🡺 try the `/new` command!")
    else:
        await interaction.response.send_message("You do not have permission to use this command, sorry!")


@client.event
async def on_message(message):
    """
    Reacts to user messages.
    This is to take care if someone did not allow bot messages initially.
    """
    if not message.guild:
        if message.author.id in dm_backlog:
            msg = "Thanks! If you want to, feel free to disable DMs for the server again.\n\n"
            msg += dm_backlog[message.author.id]
            await message.channel.send(msg)
            dm_backlog.pop(message.author.id)


@client.tree.command()
async def version(interaction: discord.Interaction):
    """
    Shows the current version of ChooserBot you are using.
    """
    await interaction.response.send_message(
        "**This is dcChooserBot, version " + VERSION_INFO +
        "**\nI am an open source project, initiated by magiausde! Find me at https://github.com/magiausde/dcChooserBot")


# start the bot!
client.run(MY_TOKEN)

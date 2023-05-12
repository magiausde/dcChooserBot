import os
import pickle
import traceback
from random import randint

import discord
import configparser

from discord.ext import commands

intents = discord.Intents.default()
intents.guild_messages = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or("$"),
                   description='Chooser Bot', status=discord.Status.dnd, intents=intents,
                   activity=discord.Game(name="preferring people since 2023"))

reference_new = -1

runtime_data = {}


def save_runtime_data():
    global runtime_data

    original_channels = {}

    # workaround for pickle that cannot save weakref objects (channel object)
    for server in runtime_data:
        for attrib in runtime_data[server]:
            if attrib == 'userchannel':
                original_channels[server] = runtime_data[server][attrib]
                runtime_data[server][attrib] = runtime_data[server][attrib].id

    with open('runtimedata.pkl', 'wb+') as f:
        pickle.dump(runtime_data, f, pickle.HIGHEST_PROTOCOL)

    # restore the real channels
    for server in original_channels:
        runtime_data[server]['userchannel'] = original_channels[server]


async def load_runtime_data():
    global runtime_data
    if os.path.exists('runtimedata.pkl'):
        with open('runtimedata.pkl', 'rb') as f:
            runtime_data = pickle.load(f)

    # workaround for pickle that cannot save weakref objects (channel object)
    for server in runtime_data:
        for attrib in runtime_data[server]:
            if attrib == 'userchannel':
                channel = await bot.fetch_channel(runtime_data[server][attrib])
                runtime_data[server][attrib] = channel


def set_runtime_data(serverid, key, value):
    if serverid not in runtime_data:
        runtime_data[serverid] = {}

    runtime_data[serverid][key] = value
    save_runtime_data()


def get_runtime_data(serverid, key):
    if serverid in runtime_data:
        if key in runtime_data[serverid]:
            return runtime_data[serverid][key]

    return None


def get_chosen_unweighted(choose_list, amount):
    chosen = []

    if amount > len(choose_list):
        print("! " + str(amount) + " demanded, but only " + str(len(choose_list)) + " to choose.")
        amount = len(choose_list)

    while len(chosen) < amount:
        upper_index_boundary = len(choose_list) - 1

        random_index = 0
        if upper_index_boundary > 0:
            random_index = randint(0, upper_index_boundary)

        # print("RI " + str(random_index) + ", UIP " + str(upper_index_boundary))

        chosen.append(choose_list[random_index])
        choose_list.remove(choose_list[random_index])

    return chosen


@bot.event
async def on_ready():
    print(f'Logged on as {bot.user}!')
    await load_runtime_data()


@bot.command()
async def new(context):
    if context.author.guild_permissions.administrator:
        global reference_new
        print('New lobby demanded!')

        userchannel = get_runtime_data(context.guild.id, 'userchannel')
        if userchannel:
            reference_new = await userchannel.send('Okay everyone! React with thumbs up if you would like to be added!')
            await reference_new.add_reaction('👍')

            # reset treasure if wanted
            if RESET_TREASURE:
                set_runtime_data(context.guild.id, 'treasure', None)
                await context.send("_Cleared the treasure. Don't forget to set a new one._")
        else:
            await context.send("Channel for user messages not set yet. Will not continue! RTFM ;)")


@bot.command()
async def settreasure(context, arg):
    if context.author.guild_permissions.administrator:
        set_runtime_data(context.guild.id, 'treasure', arg)
        await context.send("Okay! Treasure set to: " + arg)


@bot.command()
async def setuserchannel(context, arg):
    if context.author.guild_permissions.administrator:
        try:
            channel = await bot.fetch_channel(arg)
            set_runtime_data(context.guild.id, 'userchannel', channel)
            print("New user channel was set!")
            await context.send("New user channel: " + channel.name)
        except:
            traceback.print_exc()
            await context.send("Whoops! Something went wrong while setting a new channel for user messages!")


@bot.command()
async def choose(context, arg):
    if context.author.guild_permissions.administrator:
        print('Choosing demanded!')

        treasure = get_runtime_data(context.guild.id, 'treasure')
        if REQUIRE_TREASURE and (not treasure):
            await context.send("I will not choose! The required treasure is not set! Do this first.")
        else:
            if not arg:
                await context.send("Okay I would choose, but I don't know **how many** to choose. Try again!")
            else:
                if type(reference_new) == discord.message.Message:
                    cached_reference_new = discord.utils.get(bot.cached_messages, id=reference_new.id)
                    reference_reactions = cached_reference_new.reactions
                    for reaction in reference_reactions:
                        print(reaction.emoji)  # get the real msg tho :P
                        print(reaction.message)
                        if reaction.emoji == '👍':
                            thumbsup_users = [user async for user in reaction.users()]
                            thumbsup_users.remove(bot.user)

                            lobby_users_amount = len(thumbsup_users)
                            if lobby_users_amount > 0:
                                print(str(lobby_users_amount) + ' users in lobby: ' + ", ".join(
                                    [user.name for user in thumbsup_users]))

                                try:
                                    arg_int = int(arg)

                                    if arg_int > 0:
                                        chosen = get_chosen_unweighted(thumbsup_users, arg_int)
                                        userchannel = get_runtime_data(context.guild.id, 'userchannel')
                                        await userchannel.send(
                                            "**I choose you:**\n- " + "\n- ".join([user.name for user in chosen]))

                                        for user in chosen:
                                            msg = "**Congrats! You were chosen!**"

                                            if treasure:
                                                msg += '\n**Your treasure:** ' + treasure

                                            await user.send(msg)

                                    else:
                                        print("! Argument out of allowed range: " + arg)
                                        await context.send(
                                            "Hey silly! I cannot choose from " + arg + " user(s). **Try again, please!**")
                                except ValueError:
                                    traceback.print_exc()
                                    print("! Invalid argument - ValueError: " + arg)
                                    await context.send("This is not something I can work with. Try again!")
                            else:
                                await context.send("Whoops! No one was in the lobby! I cannot choose from 0 users!")

                            break
                else:
                    await context.send(
                        "Hey silly! You can't choose if you didn't even start yet! => try the `new` command!")


# Get the config
cfg_main = configparser.ConfigParser()
cfg_main.read('chooserbot.ini')

MY_TOKEN = cfg_main['Auth']['Token']

RESET_TREASURE = cfg_main.getboolean('Global', 'ResetTreasureEachRound')
REQUIRE_TREASURE = cfg_main.getboolean('Global', 'TreasureRequiredForChoosing')

bot.run(MY_TOKEN)

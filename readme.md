# Discord Chooser Bot
Selects a specified amount of people from a pool.
Optionally sends them a message (e.g. a join link). Can be configured to give priority to certain roles (e.g. subscribers, VIPs) => TODO.

## Setup
### Set up the bot itself
Get yourself an app at discord.com/developers.

Then, go to OAuth2 -> URL Generator:
* Scopes: bot
* Bot permissions: Read Messages/View Channels

Copy the generated link and visit it to join the bot to your server.

### Configure the bot
Create a file named `chooserbot.ini` and fill it out
```
[Auth]
Token=<My token from Bot => Token>
```

## Commands
* `$setuserchannel <ChannelID>` - sets the channel where public messages will be posted
* `$new` - starts a new round (users can add themselves to the lobby)
* `$choose <HowMany>` - randomly selects `<HowMany>` users
* `$settreasure "<Treasure>"` - if set, the selected users will receive this "treasure" via DM. Important! Don't forget the quotes "multiple words example"
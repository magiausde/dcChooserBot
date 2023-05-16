# Discord Chooser Bot
Selects a specified amount of people from a pool.
Optionally sends them a message (e.g. a join link). Can be configured to give priority to certain roles (e.g. subscribers, VIPs).

## Setup
### Set up the bot itself
Get yourself an app at discord.com/developers.

Then, go to OAuth2 -> URL Generator:
* Scopes: bot

Copy the generated link and visit it to join the bot to your server.

### Configure the bot
Create a file named `chooserbot.ini` and fill it out.

0 = disable the feature, 1 = enable the feature.
```
[Auth]
Token=<My token from Bot => Token>

[Global]
ResetTreasureEachRound=1
TreasureRequiredForChoosing=1
MultipleBenefits=0

[Logging]
LogLevel=Warning
```

## Commands
_Since the introduction of slash-commands, the Discord-App will guide you through the required parameters._
* `/setuserchannel <ChannelID>` - sets the channel where public messages will be posted
* `/new` - starts a new round (users can add themselves to the lobby)
* `/choose <HowMany>` - randomly selects `<HowMany>` users
* `/settreasure <Treasure>` - if set, the selected users will receive this "treasure" via DM.
* `/setbenefit <RoleID> <NrOfBenefits>` - Sets the amount of additional chances for users of this role. Set to 0 to remove benefits from role.
* `/listbenefits` - Lists the currently configured benefits
* `/setmodrole <RoleID>` - Members of this role will be able to use the bot additionally to server-admins
* `/getmodrole` - Shows you which role is currently set for using the bot additionally to server-admins

## Benefit-feature
Optionally, you can set a benefit for certain roles. This increases the chances of being chosen. Ideal for your VIPs or high-tier supporters (or yourself)...
Inside the `chooserbot.ini` you can configure `MultipleBenefits`. If it is enabled, all benefits will be added up (e.g. if a Tier 2 supporter is also a mod). If the setting is disabled, only the highest benefit a user has will be used.

Let's take a look at a round without benefits: We have three users: A, B (Tier 2), C (VIP).
```
[A, B, C]
```
Each of them has a 1/3 chance of being chosen.

Now, some benefits are applied.
```
/setbenefit [@Tier 2] [1]
$setbenefit [@VIP] [2]
```
A tier 2 supporter has an additional chance and VIPs have two additional chances of being chosen.
```
[A, B, B, C, C, C]
```
Which results in A having a 1/6 chance, B having a 2/6 = 1/3 chance and C has a 3/6 = 1/2 chance of being chosen.
The benefit stays as people get chosen (B in this case):
```
[A, C, C, C]
```
Now C even has a 3/4 chance. But always remember that there is no guarantee of being chosen.

## Example commands
These can be used as a reference to get started. 
```
/setuserchannel #d1-public
/settreasure https://example.com/join?id=j8HAzr3
/new
...
/choose 10
```
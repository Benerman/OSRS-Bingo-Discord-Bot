import discord
from discord.ext import commands, tasks
import requests
import json
import re
import random
import os
import config
from discord import Role

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

ROLES = ["Team 1", "Team 2", "Team 3", "Team 4", "Team 5", "Team 6"]
TEAM_CAPTAIN_ROLES = ["Team 1 Captain", "Team 2 Captain", "Team 3 Captain", "Team 4 Captain", "Team 5 Captain", "Team 6 Captain"]

default_settings_dict = {
    'tiles': {
        "url": "",
        "spreadsheet_id": "",
        "items": {}
    },
    "teams": {
        "Team 1" : {
            "current": 1,
            "prev": None,
            "reroll": True
        },
        "Team 2" : {
            "current": 1,
            "prev": None,
            "reroll": True
        },
        "Team 3" : {
            "current": 1,
            "prev": None,
            "reroll": True
        },
        "Team 4" : {
            "current": 1,
            "prev": None,
            "reroll": True
        },
        "Team 5" : {
            "current": 1,
            "prev": None,
            "reroll": True
        },
        "Team 6" : {
            "current": 1,
            "prev": None,
            "reroll": True
        }
    }
}

roll_channel = 'dice-roll'
mod_channel = 'bot-commands'

thumb = '\N{THUMBS UP SIGN}'
thumbs_down = '\N{THUMBS DOWN SIGN}'

def roll_dice():
    return random.randint(1, 6)

def create_discord_friendly_name(text):
    return text.lower().replace(' ', '-')

def create_settings_json():
    with open('settings.json', 'w') as f:
        json.dump(default_settings_dict, f)
        print('created settings.json file')

def load_settings_json():
    if not os.path.exists('settings.json'):
        print('trying to load settings.json but file does not exist')
        create_settings_json()
    with open('settings.json') as f:
        settings = json.load(f)
        print('loaded settings.json file')
        return settings

def save_settings_json(contents: dict) -> None:
    with open('settings.json', 'w') as f:
        print('saved settings.json file')
        json.dump(contents, f)

def update_settings_json(contents: dict, *, tiles: str = None) -> dict:
    if tiles:
        contents['tiles']['url'] = tiles
        spreadsheet_id = tiles.split('https://docs.google.com/spreadsheets/d/')[-1].split("/")[0]
        contents['tiles']['spreadsheet_id'] = spreadsheet_id
        items = load_sheet(spreadsheet_id)
        contents = format_item_list(contents, items)
        updates = 'Updated tiles "url", "items", and "spreadsheet_id"'
        save_settings_json(contents)
        # print(updates, contents, spreadsheet_id)
    else:
        print(contents['teams'])
        save_settings_json(contents)
        updates = 'Updated Team turn information'
    return updates, contents

def format_item_list(contents, tile_list: list) -> list:
    items = {}
    for i, item in enumerate(tile_list):
        if i == 0:
            # skip header
            continue
        name, desc, img_url, wiki_url = item
        frmt_item = {
            i : {
                "name": name,
                "desc": desc,
                "img_url": img_url,
                "wiki_url": wiki_url,
                "discord_name": f'{i}. {name} - {desc}'
            }
        }
        items.update(frmt_item)
    contents['items'] = items
    return contents


def load_sheet(SAMPLE_SPREADSHEET_ID, RANGE="A1:Z100"):
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('sheets', 'v4', credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=RANGE).execute()
        values = result.get('values', [])

        if not values:
            print('No data found.')
            return

        
        for row in values:
            print(row)
        return values

    except HttpError as err:
        print(err)


async def clear_team_roles(message):
    print(f'{message.guild.roles=}')
    roles = [discord.utils.get(message.guild.roles, name=rl) for rl in ROLES]
    print(roles)
    for member in message.guild.members:
        await member.remove_roles(*roles)
    print('Removed Team Roles from All Members')    
    

async def create_channels(message, data):
    if not data:
        await message.channel.send('Sheet output unable to be processed')
        return
    for i, row in enumerate(data):
        if i == 0:
            continue
        d = dict(zip(data[0], row))
        print(d)
        category = discord.utils.get(message.guild.categories, name=d['Category'])
        if not category:
            category = await message.guild.create_category(d['Category'])
        role = discord.utils.get(message.guild.roles, name=d['Category'])
        print(f"{role=}")
        print(category.channels)
        print([ch.name for ch in category.channels])
        if not discord.utils.get(category.channels, name=create_discord_friendly_name(d['Name'])):
            if d['Type'] == 'Text':
                chan = await message.guild.create_text_channel(name=create_discord_friendly_name(d['Name']), category=category, )
            else:
                chan = await message.guild.create_voice_channel(name=create_discord_friendly_name(d['Name']), category=category)
            # category = discord.utils.get(message.guild.categories, name=d['Category'])
            await chan.set_permissions(role, read_messages=True,
                                                      send_messages=True)
            await chan.edit(sync_permissions=True)
        else:
            print(d['Name'])
            existing_channel = discord.utils.get(category.channels, name=create_discord_friendly_name(d['Name']))
            await existing_channel.purge(reason="Resetting Channels")


def create_tile_embed(tiles: dict, tile_number: str) -> discord.Embed:
    itm = tiles[tile_number]
    multi_wiki_urls = itm['wiki_url'].split(',')
    multi_img_urls = itm['img_url'].split(',')
    # if len(multi_img_urls) > 1:
    img_url = multi_img_urls[0]
    embed = discord.Embed(
        title=itm['name'],
        description=itm['desc'],
        color=0xf7e302,
        url=multi_wiki_urls[0]
    )
    embed.set_image(url=img_url)
    for wiki_url in multi_wiki_urls:
        name = wiki_url.split('/')[-1].replace('_', " ")
        embed.add_field(name=name, value=f"[{name}]({wiki_url})", inline=False)
    return embed


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyClient(discord.Client):
    async def on_ready(self):
        self.settings = load_settings_json()
        self.total_tiles = len(self.settings['items'])
        print('Bot is Ready')
        print('We have logged in as {0.user}'.format(client))

    async def on_message(self, message):
        if message.author == client.user:
            return
        print(f'Message from {message.author}: {message.content}')

        if message.content.startswith('/bingo'):
            await message.edit(suppress=True)
            await message.channel.typing()
            if message.content.startswith('/bingo build'):
                link = message.content.split('/bingo build')[-1]
                spreadsheet_id = link.split('https://docs.google.com/spreadsheets/d/')[-1].split("/")[0]
                output = load_sheet(spreadsheet_id)
                await clear_team_roles(message)
                await create_channels(message, output)
                await message.channel.send(f'Completed')

        if message.content.startswith('/roll'):
            if not message.channel.name == roll_channel:
                await message.channel.send(f'Please use this command in the {roll_channel} channel for your Team')
            else:
                await message.channel.typing()
                roll = roll_dice()
                team_name = message.channel.category.name
                self.settings['teams'][team_name]['prev'] = self.settings['teams'][team_name]['current']
                self.settings['teams'][team_name]['current'] += roll
                if self.settings['teams'][team_name]['current'] > self.total_tiles:
                    # This makes the last tile mandatory
                    self.settings['teams'][team_name]['current'] = self.total_tiles
                elif self.settings['teams'][team_name]['prev'] == self.total_tiles:
                    # Checks if last prev tile was the last tile of the bingo
                    await message.add_reaction("\n{TADA}")
                    await message.reply(f'Congrats {discord.utils.get(message.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(message.guild.roles, name="Bingo Moderator").mention}')
                update_settings_json(self.settings)
                roll_reply = await message.reply(f"Rolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {self.settings['teams'][team_name]['current']} and old tile was: {self.settings['teams'][team_name]['prev']}\n{self.settings['items'][str(self.settings['teams'][team_name]['current'])]['discord_name']}")
                await message.add_reaction(thumb)
                name = create_discord_friendly_name(self.settings['items'][str(self.settings['teams'][team_name]['current'])]['name'])
                author = message.author
                ch = await message.channel.clone(name=name)
                embed = create_tile_embed(tiles=self.settings['items'], tile_number=str(self.settings['teams'][team_name]['current']))
                await ch.send(embed=embed)
                await roll_reply.edit(content=f"{roll_reply.content}\nCreated new channel <#{discord.utils.get(message.guild.channels, name=name).id}> for {discord.utils.get(message.guild.roles, name=team_name).mention}")
                # await ch.send(self.settings['items'][str(self.settings['teams'][team_name]['current'])]['discord_name'])
                

        if message.content.startswith('/reroll'):
            if not message.channel.name == roll_channel:
                await message.channel.send(f'Please use this command in the {roll_channel} channel for your Team')
            else:
                await message.channel.typing()
                team_name = message.channel.category.name
                if self.settings['teams'][team_name]['reroll']:
                    # clear existing channel
                    name = create_discord_friendly_name(self.settings['items'][str(self.settings['teams'][team_name]['current'])]['name'])
                    prev_ch = discord.utils.get(message.guild.channels, name=name)
                    messages = [x async for x in prev_ch.history(limit=2)]
                    if prev_ch and len(messages) == 1:
                        await prev_ch.delete()
                        print(f'Deleted Channel {name} after a successful reroll')
                    elif prev_ch:
                        await message.reply(f'Unable to clean up channel <#{discord.utils.get(message.guild.channels, name=name).id}> pinging {discord.utils.get(message.guild.roles, name="Bingo Moderator").mention}')
                        return
                    roll = roll_dice()
                    self.settings['teams'][team_name]['current'] = self.settings['teams'][team_name]['prev'] + roll
                    self.settings['teams'][team_name]['reroll'] = False
                    update_settings_json(self.settings)
                    roll_reply = await message.reply(f"ReRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {self.settings['teams'][team_name]['current']} and old tile was: {self.settings['teams'][team_name]['prev']}\n{self.settings['items'][str(self.settings['teams'][team_name]['current'])]['discord_name']}")
                    await message.add_reaction(thumb)
                    name = create_discord_friendly_name(self.settings['items'][str(self.settings['teams'][team_name]['current'])]['name'])
                    author = message.author
                    ch = await message.channel.clone(name=name)
                    embed = create_tile_embed(tiles=self.settings['items'], tile_number=str(self.settings['teams'][team_name]['current']))
                    await ch.send(embed=embed)
                    await roll_reply.edit(content=f"{roll_reply.content}\nCreated new channel <#{discord.utils.get(message.guild.channels, name=name).id}> for {discord.utils.get(message.guild.roles, name=team_name).mention}")
                    # await ch.send(self.settings['items'][str(self.settings['teams'][team_name]['current'])]['discord_name'])
                else:
                    await message.reply(f'NO MORE REROLLS MFER!')
                    await message.add_reaction(thumbs_down)

        if message.content.startswith('/assign spectator ') and message.channel.category.name.lower() == 'admin':
            if not message.channel.name == mod_channel:
                await message.channel.send(f'Please use this command in the {mod_channel} channel')
            else:
                await message.channel.typing()
                author = message.author
                current_role = discord.utils.get(author.guild.roles, name="spectator")
                if "@everyone" in message.content:
                    for user in author.guild.members:
                        await user.add_roles(current_role)
                elif len(message.mentions) == 0:
                    await message.channel.send(f'Please add @ each member to add them too team')
                else:
                    for i in range(len(message.mentions)):
                        await message.mentions[i].add_roles(current_role)
                await message.add_reaction(thumb)


        if message.content.startswith('/unassign spectator ') and message.channel.category.name.lower() == 'admin':
            if not message.channel.name == mod_channel:
                await message.channel.send(f'Please use this command in the {mod_channel} channel')
            else:
                await message.channel.typing()
                author = message.author
                current_role = discord.utils.get(author.guild.roles, name="spectator")
                if "@everyone" in message.content:
                    for user in author.guild.members:
                        await user.remove_roles(current_role)
                elif len(message.mentions) == 0:
                    await message.channel.send(f'Please add @ each member to add them too team')
                else:
                    current_role = discord.utils.get(author.guild.roles, name="spectator")
                    for i in range(len(message.mentions)):
                        await message.mentions[i].remove_roles(current_role)
                await message.add_reaction(thumb)
                                                                                                                                                                        
        if message.content.startswith('/assign team ') and message.channel.category.name.lower() == 'admin':
            if not message.channel.name == mod_channel:
                await message.channel.send(f'Please use this command in the {mod_channel} channel')
            else:
                await message.channel.typing()
                team_number = message.content.split('/assign team ')[1][:1]
                author = message.author
                if len(message.mentions) == 0:
                    await message.channel.send(f'Please add @ each member to add them too team')
                else:
                    current_role = discord.utils.get(author.guild.roles, name=f"Team {team_number}")
                    roles = [discord.utils.get(message.guild.roles, name=rl) for rl in ROLES]
                    spectator_role = discord.utils.get(author.guild.roles, name="spectator")
                    roles.append(spectator_role)
                    for i in range(len(message.mentions)):
                        await message.mentions[i].remove_roles(*roles)
                        await message.mentions[i].add_roles(current_role)
                    await message.add_reaction(thumb)

                    
        if message.content.startswith('/assign captain team ') and message.channel.category.name.lower() == 'admin':
            if not message.channel.name == mod_channel:
                await message.channel.send(f'Please use this command in the {mod_channel} channel')
            else:
                await message.channel.typing()
                team_number = message.content.split('/assign captain team ')[1][:1]
                author = message.author
                if len(message.mentions) == 0:
                    await message.channel.send(f'Please add @ member to add Team {team_number} Captain Role')
                else:
                    current_role = discord.utils.get(author.guild.roles, name=f"Team {team_number}")
                    captain_role = discord.utils.get(author.guild.roles, name=f"Team {team_number} Captain")
                    roles = [discord.utils.get(message.guild.roles, name=rl) for rl in ROLES]
                    spectator_role = discord.utils.get(author.guild.roles, name="spectator")
                    roles.append(spectator_role)
                    captain_roles = [discord.utils.get(message.guild.roles, name=rl) for rl in TEAM_CAPTAIN_ROLES]
                    for i in range(len(message.mentions)):
                        await message.mentions[i].remove_roles(*[*roles, *captain_roles])
                        await message.mentions[i].add_roles(*[current_role, captain_role])
                await message.add_reaction(thumb)

        if message.content.startswith('/unassign captain ') and message.channel.category.name.lower() == 'admin':
            if not message.channel.name == mod_channel:
                await message.channel.send(f'Please use this command in the {mod_channel} channel')
            else:
                await message.channel.typing()
                author = message.author
                if len(message.mentions) == 0:
                    await message.channel.send(f'Please add @ member to add Team {team_number} Captain Role')
                else:
                    roles = [discord.utils.get(message.guild.roles, name=rl) for rl in TEAM_CAPTAIN_ROLES]
                    for i in range(len(message.mentions)):
                        await message.mentions[i].remove_roles(*roles)
                    await message.add_reaction(thumb)

                    
        if message.content.startswith('/disband team ') and message.channel.category.name.lower() == 'admin':
            if not message.channel.name == mod_channel:
                await message.channel.send(f'Please use this command in the {mod_channel} channel')
            else:
                await message.channel.typing()
                try:
                    team_number = message.content.split('/disband team ')[1][:1]
                    team_number = int(team_number)
                    author = message.author
                    users_processed = 0
                    for user in author.guild.members:
                        current_role = discord.utils.get(user.roles, name=f"Team {team_number}")
                        if current_role:
                            await user.remove_roles(current_role)
                            users_processed += 1
                    if not users_processed:
                        raise ValueError
                    await message.add_reaction(thumb)
                except ValueError:
                    await message.channel.send(f"We ran into issues disbanding Team {team_number} OR there are no members in that that role")
                    await message.add_reaction(thumbs_down)
                
        if message.content.startswith('/clone'):
            await message.channel.typing()
            mod_role = discord.utils.get(message.guild.roles, name="Bingo Moderator")
            if mod_role in message.author.roles:
                name = message.content.split('/clone ')[-1]
                author = message.author
                ch = await message.channel.clone(name=name)
                await ch.send(f"Channel cloned successfully {author.mention}")
                await message.add_reaction(thumb)
                # roles = [discord.utils.get(message.guild.roles, name=rl) for rl in ROLES]
                # for role in roles:
                # for k, v in message.channel.overwrites.items():
                #     await message.channel.send(f"{message.channel.name}\n{k}\n{v}")
            else:
                await message.channel.send(f"You have insufficient permissions {message.author.mention}")

        if message.content.startswith('/set tiles ') and message.channel.category.name.lower() == 'admin':
            await message.edit(suppress=True)
            await message.channel.typing()
            url = message.content.split('/set tiles ')[-1]
            processed, self.settings = update_settings_json(self.settings, tiles=url)
            await message.reply(f"{processed}")
            embed = discord.Embed(
                title="Tile List",
                color=discord.Color.blue(),
                description='\n'.join([itm['discord_name'] for itm in self.settings['items'].values()])
                )
            await message.reply(embed=embed)
            # post in #tile-list
            tile_list_channel = discord.utils.get(message.guild.channels, name="tile-list")
            await tile_list_channel.send(embed=embed)
        
        if message.content.startswith('/show tiles') and message.channel.category.name.lower() == 'admin':
            await message.channel.typing()
            # tiles = load_sheet(self.settings['tiles']['spreadsheet_id'])
            embed = discord.Embed(
                title="Tile List",
                color=discord.Color.blue(),
                description='\n'.join([itm['discord_name'] for itm in self.settings['items'].values()])
                )
            await message.reply(embed=embed)
            # post in #tile-list

        if message.content.startswith('/set team ') and message.channel.category.name.lower() == 'admin':
            await message.channel.typing()
            try:
                team_number = message.content.split('/set team ')[1][:1]
                team_number = int(team_number)
            except ValueError:
                await message.channel.send(f"We ran into issues deterimining the Team {team_number} OR ran into another error during this process")
                await message.add_reaction(thumbs_down)
                return
            if 'reroll' in message.content:
                if message.content.split('reroll ')[-1] == 'on':
                    if self.settings['teams'][f'Team {team_number}']['reroll']:
                        await message.reply('Reroll is unused for that team.')
                    else:
                        self.settings['teams'][f'Team {team_number}']['reroll'] = True
                        update_settings_json(self.settings)
                        await message.reply('Reroll is reenabled for that team.')
                        await message.add_reaction(thumb)
                elif message.content.split('reroll ')[-1] == 'off':
                    if not self.settings['teams'][f'Team {team_number}']['reroll']:
                        await message.reply('Reroll has already been used for that team.')
                    else:
                        self.settings['teams'][f'Team {team_number}']['reroll'] = False
                        update_settings_json(self.settings)
                        await message.reply('Reroll has been disabled for that team.')
                        await message.add_reaction(thumb)
                else:
                    await message.reply(f'Command "{message.content}" is not recognized. Ensure formatting is correct "/set team <Team #> reroll <on|off>"')
                    await message.add_reaction(thumbs_down)
            elif 'prev tile' in message.content:
                tile = message.content.split('prev tile ')[-1]
                try:
                    tile = int(tile)
                except ValueError:
                    await message.reply(f'Unable to process command "{message.content}". Unable to process tile: {tile}')
                if tile < 1:
                    tile = None
                self.settings['teams'][f'Team {team_number}']['prev'] = tile
                await message.reply(f'Updated prev tile to {tile}')
                update_settings_json(self.settings)
                await message.add_reaction(thumb)
            elif 'tile' in message.content:
                tile = message.content.split('tile ')[-1]
                try:
                    tile = int(tile)
                except ValueError:
                    await message.reply(f'Unable to process command "{message.content}". Unable to process tile: {tile}')
                if tile < 1:
                    tile = 1
                self.settings['teams'][f'Team {team_number}']['current'] = tile
                await message.reply(f'Updated current tile to {tile}')
                update_settings_json(self.settings)
                await message.add_reaction(thumb)
            else:
                await message.reply(f'Command "{message.content}" is not recognized. Ensure formatting is correct.')
                await message.add_reaction(thumbs_down)


client = MyClient(intents=intents)

client.run(config.DISCORD_BOT_TOKEN)


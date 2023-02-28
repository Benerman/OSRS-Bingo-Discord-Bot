import discord
from discord import app_commands
from discord.app_commands.checks import has_role
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


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)



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

def team_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=False,
        manage_permissions=False,
        manage_webhooks=False,
        create_invite=False,
        send_messages=True,
        connect=True
    )

def spectator_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=False,
        manage_permissions=False,
        manage_webhooks=False,
        create_invite=False,
        send_messages=True,
        connect=True
    )

def everyone_overwrites():
    pass


# ========= Bot Commands ================

settings = load_settings_json()
total_tiles = len(settings['items'])

@bot.event
async def on_ready():
    print('Bot is Ready')
    # print('We have logged in as {0.user}'.format(client))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")


@bot.tree.command(name="roll", description=f"Roll a d6 for in the {roll_channel} for your team. Creates new channel for the newly rolled tile.")
async def roll(interaction: discord.Interaction):

    # put a check for has role in here
    team_name = interaction.channel.category.name
    role_name = discord.utils.get(interaction.guild.roles, name=team_name)
    if not role_name in interaction.user.roles or interaction.channel.name != roll_channel:
        await interaction.response.send_message(f"Please ensure you have approriate Team Role and are within your Team's #{roll_channel}")
        return
    else:
        await interaction.channel.typing()
        roll = roll_dice()
        # create function to handle updating settings points

        settings['teams'][team_name]['prev'] = settings['teams'][team_name]['current']
        settings['teams'][team_name]['current'] += roll
        if settings['teams'][team_name]['current'] > total_tiles:
            # This makes the last tile mandatory
            settings['teams'][team_name]['current'] = total_tiles
        elif settings['teams'][team_name]['prev'] == total_tiles:
            # Checks if last prev tile was the last tile of the bingo
            # await message.add_reaction("\n{TADA}")
            await interaction.response.send_message(f'Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}')
        update_settings_json(settings)
        roll_text = f"Rolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{settings['items'][str(settings['teams'][team_name]['current'])]['discord_name']}"
        await interaction.response.send_message(content=roll_text)
        name = create_discord_friendly_name(settings['items'][str(settings['teams'][team_name]['current'])]['name'])
        ch = await interaction.channel.clone(name=name)
        embed = create_tile_embed(tiles=settings['items'], tile_number=str(settings['teams'][team_name]['current']))
        await ch.send(embed=embed)
        # await msg.edit(
        #     content=f"{roll_text}\nCreated new channel <#{discord.utils.get(interaction.guild.channels, name=name).id}> for {discord.utils.get(interaction.guild.roles, name=team_name).mention}",
        #     wait=True
        #     )


@bot.tree.command(name="reroll", description="Reroll a d6 nulling the last roll and rolling from the previous tile.")
async def reroll(interaction: discord.Interaction):
    team_name = interaction.channel.category.name
    role_name = discord.utils.get(interaction.guild.roles, name=team_name)
    print(team_name)
    print(role_name)
    print(interaction.user.roles)
    print(not role_name.name in interaction.user.roles)
    print(interaction.channel.name != roll_channel)
    if not role_name in interaction.user.roles or interaction.channel.name != roll_channel:
        await interaction.response.send_message(f"Please ensure you have approriate Team Role and are within your Team's #{roll_channel}")
        return
    else:
        await interaction.channel.typing()
        team_name = interaction.channel.category.name
        if settings['teams'][team_name]['reroll']:
            # clear existing channel
            name = create_discord_friendly_name(settings['items'][str(settings['teams'][team_name]['current'])]['name'])
            prev_ch = discord.utils.get(interaction.guild.channels, name=name)
            messages = [x async for x in prev_ch.history(limit=2)]
            if prev_ch and len(messages) == 1:
                await prev_ch.delete()
                print(f'Deleted Channel {name} after a successful reroll')
            elif prev_ch:
                await interaction.response.send_message(f'Unable to clean up channel <#{discord.utils.get(interaction.guild.channels, name=name).id}> pinging {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}')
                return
            roll = roll_dice()
            settings['teams'][team_name]['current'] = settings['teams'][team_name]['prev'] + roll
            settings['teams'][team_name]['reroll'] = False
            update_settings_json(settings)
            await interaction.response.send_message(f"ReRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{settings['items'][str(settings['teams'][team_name]['current'])]['discord_name']}")
            name = create_discord_friendly_name(settings['items'][str(settings['teams'][team_name]['current'])]['name'])
            ch = await interaction.channel.clone(name=name)
            embed = create_tile_embed(tiles=settings['items'], tile_number=str(settings['teams'][team_name]['current']))
            await ch.send(embed=embed)
            # await roll_reply.edit(content=f"{roll_reply.content}\nCreated new channel <#{discord.utils.get(interaction.guild.channels, name=name).id}> for {discord.utils.get(interaction.guild.roles, name=team_name).mention}")
        else:
            await interaction.response.send_message(f'NO MORE REROLLS MFER!')

# @has_role("Bingo Moderator")
@bot.tree.command(name="set_tiles", description=f"Sets the Bingo Tiles from a Public Google Sheet doc, processes, and formats them.")
async def set_tiles(interaction: discord.Interaction, sheet_link: str):
    if not interaction.channel.category.name.lower() == 'admin':
        await interaction.response.send_message(f"Use this command in {mod_channel} and ADMIN section")
        return
    # await interaction.response.edit_message(suppress=True)
    await interaction.channel.typing()
    processed, settings = update_settings_json(settings, tiles=sheet_link)
    await interaction.response.send_message(f"{processed}")
    embed = discord.Embed(
        title="Tile List",
        color=discord.Color.blue(),
        description='\n'.join([itm['discord_name'] for itm in settings['items'].values()])
        )
    # await interaction.reply(embed=embed)
    # post in #tile-list
    tile_list_channel = discord.utils.get(interaction.guild.channels, name="tile-list")
    await tile_list_channel.send(embed=embed)



bot.run(config.DISCORD_BOT_TOKEN)
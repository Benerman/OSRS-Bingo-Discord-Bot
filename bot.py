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
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

DICE_SIDES = 6

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

ROLES = ["Team 1", "Team 2", "Team 3", "Team 4", "Team 5", "Team 6"]
TEAM_CAPTAIN_ROLES = ["Team 1 Captain", "Team 2 Captain", "Team 3 Captain", "Team 4 Captain", "Team 5 Captain", "Team 6 Captain"]
DEFAULT_CHANNELS = ["chat", "bingo-card", "dice-roll", "photo-dump", "voice-chat"]

default_settings_dict = {
    'tiles': {
        "url": "",
        "spreadsheet_id": "",
        "items": {}
    },
    "teams": {
        "Team 1" : {
            "current": 0,
            "prev": None,
            "reroll": True,
            "roll_history": []
        },
        "Team 2" : {
            "current": 0,
            "prev": None,
            "reroll": True,
            "roll_history": []
        },
        "Team 3" : {
            "current": 0,
            "prev": None,
            "reroll": True,
            "roll_history": []
        },
        "Team 4" : {
            "current": 0,
            "prev": None,
            "reroll": True,
            "roll_history": []
        },
        "Team 5" : {
            "current": 0,
            "prev": None,
            "reroll": True,
            "roll_history": []
        }
        # },
        # "Team 6" : {
        #     "current": 0,
        #     "prev": None,
        #     "reroll": True,
        #     "roll_history": []
        # }
    }
}

roll_channel = 'dice-roll'
mod_channel = 'bot-commands'

thumb = '\N{THUMBS UP SIGN}'
thumbs_down = '\N{THUMBS DOWN SIGN}'

def roll_dice(num=DICE_SIDES):
    return random.randint(1, num)

def create_discord_friendly_name(text):
    return text.lower().replace(' ', '-').replace("'", "").replace('*','').replace('?', '').replace(',', '')

def create_settings_json():
    with open('settings.json', 'w') as f:
        json.dump(default_settings_dict, f, indent=4)
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
        json.dump(contents, f, indent=4)

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
        # print(contents['teams'])
        save_settings_json(contents)
        updates = 'Updated Team turn information'
    return updates, contents

def format_item_list(contents, tile_list: list) -> list:
    items = {}
    for i, item in enumerate(tile_list):
        if i == 0:
            # skip header
            continue
        tile_num, name, short_desc, desc, sabotage, item_names, diff = item
        frmt_item = {
            i : {
                "tile_num": tile_num,
                "name": name,
                "short_desc": short_desc,
                "desc": desc,
                "sabotage": sabotage,
                "item_names": item_names,
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


async def clear_team_roles(interaction):
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    for member in interaction.guild.members:
        await member.remove_roles(*roles)
    print('Removed Team Roles from All Members')


def create_tile_embed(tiles: dict, tile_number: str) -> discord.Embed:
    itm = tiles[tile_number]
    # multi_wiki_urls = itm['wiki_url'].split(',')
    # multi_img_urls = itm['img_url'].split(',')
    # if len(multi_img_urls) > 1:
    # img_url = multi_img_urls[0]
    embed = discord.Embed(
        title=f"{itm['tile_num']} - {itm['name']} - {itm['short_desc']}",
        description=itm['desc'],
        color=0xf7e302
        # url=multi_wiki_urls[0]
    )
    # embed.set_image(url=img_url)
    # for wiki_url in multi_wiki_urls:
    #     name = wiki_url.split('/')[-1].replace('_', " ")
    #     embed.add_field(name=name, value=f"[{name}]({wiki_url})", inline=False)
    return embed

def team_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=False,
        manage_messages=False,
        manage_permissions=False,
        manage_webhooks=False,
        create_instant_invite=False,
        send_messages=True,
        connect=True
    )

def spectator_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=False,
        manage_messages=False,
        manage_permissions=False,
        manage_webhooks=False,
        create_instant_invite=False,
        send_messages=False,
        connect=True
    )

def bingo_bot_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=True,
        manage_permissions=True,
        manage_webhooks=True,
        send_messages=True,
        send_messages_in_threads=True,
        create_public_threads=True,
        create_private_threads=True,
        embed_links=True,
        attach_files=True,
        add_reactions=True,
        read_message_history=True
    )


def everyone_overwrites():
    return discord.PermissionOverwrite(
        view_channel=False,
        create_instant_invite=False,
        send_messages=False
    )


async def update_team_bingo_card_channel(interaction: discord.Interaction, team_name, roll, settings, reroll=False):
    for ch in interaction.channel.category.channels:
        if ch.name.endswith('bingo-card'):
            await ch.send(f"{'Rerolling ' if reroll else ''}Dice roll: {roll} for team: {team_name}\nNew tile: {settings['teams'][team_name]['current']} << Old tile: {settings['teams'][team_name]['prev']}\nRerolls remaining: {settings['teams'][team_name]['reroll']}")


async def update_reroll_team_bingo_card_channel(interaction: discord.Interaction, team_name, settings, used=True):
    for ch in interaction.guild.channels:
        if ch.name.endswith(f'{create_discord_friendly_name(team_name)}-bingo-card'):
            await ch.send(f"Reroll was {'used' if used else 'awarded'} for team: {team_name}\nRerolls remaining: {settings['teams'][team_name]['reroll']}")

async def update_server_score_board_channel(interaction: discord.Interaction, settings):
    score_card_ch = discord.utils.get(interaction.guild.channels , name="score-board")
    if settings['posts']['score-board']['id']:
        msg_id = int(settings['posts']['score-board']['id'])
    else:
        # ch_id = 1108133466350030858
        async for msg in score_card_ch.history(oldest_first=True):
            print(msg)
            if msg.author == bot.user:
                msg_id = msg.id
                print(f"{msg_id =}")
                msg_webhook = msg.webhook_id
                print(f"{msg_webhook =}")
    try:
        message = await score_card_ch.fetch_message(msg_id)
    except discord.errors.NotFound as e:
        msg = await score_card_ch.send(content=settings['posts']['score-board']['content'])
        msg_id = msg.id
        message = await score_card_ch.fetch_message(msg_id)
    if message.content != settings['posts']['score-board']['content']:
        print("score is out of sync")
    teams_names = [x for x in settings['teams'].keys()]
    teams_scores = [x['current'] for x in settings['teams'].values()]
    teams_rerolls = [x['reroll'] for x in settings['teams'].values()]
    content_text = []
    for i in range(len(teams_names)):
        row = f"{teams_names[i]}: {teams_scores[i]} - Rerolls remain: {teams_rerolls[i]}"
        content_text.append(row)
    settings['posts']['score-board']['id'] = msg_id
    settings['posts']['score-board']['content'] = '\n'.join(content_text)
    update_settings_json(settings)
    await message.edit(content='\n'.join(content_text))

def update_roll_settings(roll, team_name, settings, prev, current, reroll=False):
    if reroll:
        settings['teams'][team_name]['roll_history'].append("reroll")
    settings['teams'][team_name]['roll_history'].append(roll)
    settings['teams'][team_name]['prev'] = prev
    settings['teams'][team_name]['current'] = current
    # roll_info = settings['items'][str(settings['teams'][team_name]['current'])]
    return settings
# , roll_info


def formatted_title(settings, team_name):
    tile_num = settings['teams'][team_name]['current']
    name = settings['items'][str(tile_num)]['name']
    desc = settings['items'][str(tile_num)]['short_desc']
    return f"{tile_num} - {name} - {desc}"

# ========= Bot Commands ================

settings = load_settings_json()
total_tiles = len(settings['items'])

async def team_autocomplete(
    interaction: discord.Interaction,
    current: str
    ) -> List[app_commands.Choice[str]]:
        commands = [
            "Create",
            "Set Team Name",
            "Set Tile",
            "Set Prev Tile",
            "Set Reroll"
            # "Members",
            # "Captain",
            # "Spectators"
        ]
        return [
            app_commands.Choice(name=command, value=command)
            for command in commands if current.lower() in command.lower()
        ]

async def team_names_autocomplete(
    interaction: discord.Interaction,
    current: str
    ) -> List[app_commands.Choice[str]]:
        team_names = settings['teams'].keys()
        return [
            app_commands.Choice(name=team_name, value=team_name)
            for team_name in team_names if current.lower() in team_name.lower()
        ]


@bot.event
async def on_ready():
    print('Bot is Ready')
    # print('We have logged in as {0.user}'.format(client))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")


@bot.tree.command(name="roll", description=f"Roll a d{DICE_SIDES} in your teams {roll_channel} channel. Creates new channel for the newly rolled tile.")
async def roll(interaction: discord.Interaction):

    # put a check for has role in here
    team_name = interaction.channel.category.name
    role_name = discord.utils.get(interaction.guild.roles, name=team_name)
    if not role_name in interaction.user.roles or not roll_channel in interaction.channel.name:
        await interaction.response.send_message(f"Please ensure you have approriate Team Role and are within your Team's #{roll_channel}")
        return
    else:
        await interaction.channel.typing()
        roll = roll_dice()
        # create function to handle updating settings points
        settings = load_settings_json()
        settings = update_roll_settings(
            roll,
            team_name,
            settings,
            prev=settings['teams'][team_name]['current'],
            current=settings['teams'][team_name]['current']+roll
            )
        # TODO
        if settings['teams'][team_name]['prev'] == total_tiles:
            # Checks if last prev tile was the last tile of the bingo
            # await message.add_reaction("\n{TADA}")
            await interaction.response.send_message(f'Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}')
            return
        elif settings['teams'][team_name]['current'] > total_tiles:
            # This makes the last tile mandatory
            settings['teams'][team_name]['current'] = total_tiles
        # roll_info = settings['items'][str(settings['teams'][team_name]['current'])]
        # print(f"{roll_info = }")
        update_settings_json(settings)

        title = formatted_title(settings, team_name)
        await interaction.response.send_message(
        f"Rolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
        )
        name = create_discord_friendly_name(f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}")
        ch = await interaction.channel.clone(name=name)
        embed = create_tile_embed(tiles=settings['items'], tile_number=str(settings['teams'][team_name]['current']))
        await ch.send(embed=embed)

        # Check if Sabotage Tile
        if sabotage := settings['items'][str(settings['teams'][team_name]['current'])]['sabotage']:
            print(sabotage)
            if "-" in sabotage:
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings['teams'][team_name]['current'],
                    current=settings['teams'][team_name]['current']+int(sabotage)
                )
                # message in skipped channel
                await ch.send(f"SABOTAGED: Go back to tile {settings['teams'][team_name]['current']}")
            elif "reroll" in sabotage.lower():

                # Needs to auto reroll
                roll = roll_dice()
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings['teams'][team_name]['current'],
                    current=settings['teams'][team_name]['current']+roll
                )
                # message in skipped channel
                await ch.send(f"SKIPPED: Goto tile {settings['teams'][team_name]['current']}")
            else:
                # message in skipped channel
                await ch.send(f"SABOTAGED: Goto tile {sabotage}")
                # Go to tile
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings['teams'][team_name]['current'],
                    current=int(sabotage)
                )
            title = formatted_title(settings, team_name)
            await interaction.channel.send(f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}")

            name = create_discord_friendly_name(f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}")
            ch = await interaction.channel.clone(name=name)
            embed = create_tile_embed(tiles=settings['items'], tile_number=str(settings['teams'][team_name]['current']))
            await ch.send(embed=embed)
            

        # Add updating the TEAMS bingo card channel
        await update_team_bingo_card_channel(interaction, team_name, roll, settings)
        
        # Add updating the Server's Bingo card Channel
        await update_server_score_board_channel(interaction, settings)
        



@bot.tree.command(name="reroll", description=f"Reroll a d{DICE_SIDES} in your teams {roll_channel} channel, nulling the last roll and rolls from the prev tile.")
async def reroll(interaction: discord.Interaction):
    team_name = interaction.channel.category.name
    role_name = discord.utils.get(interaction.guild.roles, name=team_name)
    if not role_name in interaction.user.roles or not roll_channel in interaction.channel.name:
        await interaction.response.send_message(f"Please ensure you have approriate Team Role and are within your Team's #{roll_channel}")
        return
    else:
        await interaction.channel.typing()
        settings = load_settings_json()
        team_name = interaction.channel.category.name
        if settings['teams'][team_name]['reroll'] > 0:
            # clear existing channel
            name = create_discord_friendly_name(f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}")
            print(f"{name = }")
            prev_ch = discord.utils.get(interaction.guild.channels, name=name)
            messages = [x async for x in prev_ch.history(limit=2)]
            if prev_ch and len(messages) == 1:
                await prev_ch.delete()
                print(f'Deleted Channel {name} after a successful reroll')
            elif prev_ch:
                await interaction.response.send_message(f'Unable to clean up channel <#{discord.utils.get(interaction.guild.channels, name=name).id}> pinging {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}')
                return
            roll = roll_dice()
            settings = update_roll_settings(
                roll,
                team_name,
                settings,
                prev=settings['teams'][team_name]['prev'],
                current=settings['teams'][team_name]['prev']+roll,
                reroll=True
                )
            settings['teams'][team_name]['reroll'] -= 1
            if settings['teams'][team_name]['prev'] == total_tiles:
                # Checks if last prev tile was the last tile of the bingo
                # await message.add_reaction("\n{TADA}")
                await interaction.response.send_message(f'Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}')
                return
            elif settings['teams'][team_name]['current'] > total_tiles:
                # This makes the last tile mandatory
                settings['teams'][team_name]['current'] = total_tiles
            update_settings_json(settings)
            title = formatted_title(settings, team_name)
            await interaction.response.send_message(f"ReRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}")
            
            name = create_discord_friendly_name(f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}")
            ch = await interaction.channel.clone(name=name)
            embed = create_tile_embed(tiles=settings['items'], tile_number=str(settings['teams'][team_name]['current']))
            await ch.send(embed=embed)

            # Check if Sabotage Tile
            if sabotage := settings['items'][str(settings['teams'][team_name]['current'])]['sabotage']:
                print(sabotage)
                if "-" in sabotage:
                    settings = update_roll_settings(
                        roll,
                        team_name,
                        settings,
                        prev=settings['teams'][team_name]['current'],
                        current=settings['teams'][team_name]['current']+int(sabotage)
                    )
                    # message in skipped channel
                    await ch.send(f"SABOTAGED: Go back to tile {settings['teams'][team_name]['current']}")
                elif "reroll" in sabotage.lower():

                    # Needs to auto reroll
                    roll = roll_dice()
                    settings = update_roll_settings(
                        roll,
                        team_name,
                        settings,
                        prev=settings['teams'][team_name]['current'],
                        current=settings['teams'][team_name]['current']+roll
                    )
                    # message in skipped channel
                    await ch.send(f"SKIPPED: Goto tile {settings['teams'][team_name]['current']}")
                else:
                    # message in skipped channel
                    await ch.send(f"SABOTAGED: Goto tile {sabotage}")
                    # Go to tile
                    settings = update_roll_settings(
                        roll,
                        team_name,
                        settings,
                        prev=settings['teams'][team_name]['current'],
                        current=int(sabotage)
                    )
                title = formatted_title(settings, team_name)
                await interaction.channel.send(f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}")

                name = create_discord_friendly_name(f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}")
                ch = await interaction.channel.clone(name=name)
                embed = create_tile_embed(tiles=settings['items'], tile_number=str(settings['teams'][team_name]['current']))
                await ch.send(embed=embed)

            # Add updating the TEAMS bingo card channel
            await update_team_bingo_card_channel(interaction, team_name, roll, settings, reroll=True)
            # Add updating the Server's Bingo card Channel
            await update_server_score_board_channel(interaction, settings)

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
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    processed, settings = update_settings_json(settings, tiles=sheet_link)
    await interaction.followup.send(f"{processed}")
    # embed = discord.Embed(
    #     title="Tile List",
    #     color=discord.Color.blue(),
    #     description='\n'.join([itm['discord_name'] for itm in settings['items'].values()])
    #     )
    # await interaction.reply(embed=embed)
    # post in #tile-list
    # tile_list_channel = discord.utils.get(interaction.guild.channels, name="tile-list")
    # await tile_list_channel.send(embed=embed)

@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role("Bingo Moderator")
@bot.tree.command(name="disband", description=f"Clear Team <#> Role from all players assigned")
async def disband(interaction: discord.Interaction, team_name: str):
    team_names = [x for x in settings['teams'].keys()]
    await interaction.channel.typing()
    if not team_name in team_names:
        await interaction.response.send_message(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
        return
    else:
        team_number = team_names.index(team_name) + 1
        try:
            users_processed = 0
            for user in interaction.guild.members:
                current_role = discord.utils.get(user.roles, name=f"Team {team_number}")
                if current_role:
                    await user.remove_roles(current_role)
                    users_processed += 1
                else:
                    print(f'No Role found | "Team {team_number}" | Team Name: "{team_name}"')
            if not users_processed:
                raise ValueError
            await interaction.response.send_message(f'Disbanded Team: {team_name} Role: "Team {team_number}" removing the role from {users_processed} users')
        except ValueError:
            await interaction.response.send_message(f'We ran into issues disbanding Discord Role: "Team {team_number}" OR there are no members in that that role')

@has_role("Bingo Moderator")
@bot.tree.command(name="spectators", description=f"Assign Spectator Role to Discord Members")
async def spectators(interaction: discord.Interaction,
                    members: str,
                    unassign: bool = False):
    await interaction.channel.typing()
    spectator_role = discord.utils.get(interaction.guild.roles, name="spectator")
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    roles.append(spectator_role)
    members = members.split()
    if members[0] == '@everyone':
        members = interaction.guild.members
        await interaction.response.defer(thinking=True)
        for m in members:
            await m.remove_roles(*roles)
            if not unassign:
                await m.add_roles(spectator_role)
        await interaction.followup.send(f'Role "spectator" {"added" if not unassign else "removed"} to all server members')
    elif len(members) == 0:
        await interaction.response.send_message(f'Please add @ each member to add them too team')
    else:
        await interaction.response.defer(thinking=True)
        for m in members:
            m_id = int(m.replace('<', '').replace('>', '').replace('@', ''))
            mem = await interaction.guild.fetch_member(m_id)
            await mem.remove_roles(*roles)
            if not unassign:
                await mem.add_roles(spectator_role)
        await interaction.followup.send(f'Role "spectator" {"added" if not unassign else "removed"} to {len(members)} members')

    # elif option == "Captain":
    #     if len(interaction.message.mentions) == 0:
    #         await interaction.response.send_message(f'Please add @ member to add Team {team_number} Captain Role')
    #     else:
    #         current_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_number}")
    #         captain_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_number} Captain")
    #         roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    #         spectator_role = discord.utils.get(interaction.guild.roles, name="spectator")
    #         roles.append(spectator_role)
    #         captain_roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in TEAM_CAPTAIN_ROLES]
    #         for i in range(len(interaction.message.mentions)):
    #             await interaction.message.mentions[i].remove_roles(*[*roles, *captain_roles])
    #             await interaction.message.mentions[i].add_roles(*[current_role, captain_role])
    #     await interaction.response.send_message(f'Role "Team {team_number} Captain" added to {len(interaction.message.mentions)} members')


@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role("Bingo Moderator")
@bot.tree.command(name="members", description=f"Assign Team <#> Role to Discord Members")
async def members(interaction: discord.Interaction,
                team_name: str,    
                members: str):
    team_names = [x for x in settings['teams'].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.channel.typing()
    await interaction.response.defer(thinking=True)
    current_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_number}")
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    members = members.split()
    for m in members:
        m_id = int(m.replace('<', '').replace('>', '').replace('@', ''))
        mem = await interaction.guild.fetch_member(m_id)
        await mem.remove_roles(*roles)
        await mem.add_roles(current_role)
    await interaction.followup.send(f'Role "Team {team_number}" added to {len(members)} members')


async def reroll(interaction: discord.Interaction, option: str, team_name: str):
    
    class Reroll(discord.ui.View):
        def __init__(self, *, timeout: Optional[float] = 180):
            super().__init__(timeout=timeout)
        @discord.ui.button(label='Revoke', style=discord.ButtonStyle.danger)
        async def revoke_reroll(self, interaction: discord.Interaction, Button: discord.ui.Button):
            if settings['teams'][team_name]['reroll'] == 0:
                await interaction.response.send_message(content='No Rerolls exist for that team.')
            else:
                settings['teams'][team_name]['reroll'] -= 1
                update_settings_json(settings)
                await interaction.response.send_message('1 Reroll has been removed for that team.')
                # Add updating the TEAMS bingo card channel
                await update_reroll_team_bingo_card_channel(interaction, team_name, settings, used=True)
                # Add updating the Server's Bingo card Channel
                await update_server_score_board_channel(interaction, settings)

        @discord.ui.button(label='Give', style=discord.ButtonStyle.green)
        async def give_reroll(self, interaction: discord.Interaction, Button: discord.ui.Button):
            settings['teams'][team_name]['reroll'] += 1
            update_settings_json(settings)
            await interaction.response.send_message(content='1 Reroll is added to that team.')
            # Add updating the TEAMS bingo card channel
            await update_reroll_team_bingo_card_channel(interaction, team_name, settings, used=False)
            # Add updating the Server's Bingo card Channel
            await update_server_score_board_channel(interaction, settings)

    await interaction.response.send_message('Choose an option for Reroll:', view=Reroll())

# @has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@app_commands.autocomplete(option=team_autocomplete)
@bot.tree.command(name="team", description=f"Configure teams")
async def team(interaction: discord.Interaction,
               option: str,
               team_name: str,
               tile: str = None,
               role: discord.Role = None,
               new_team_name: str = None,
               members: str = None
               ):
    team_names = [x for x in settings['teams'].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.channel.typing()
    if not interaction.channel.category.name.lower() == 'admin':
        await interaction.response.send_message(f"Use this command in {mod_channel} and ADMIN section")
        return
    elif not team_name in team_names:
        await interaction.response.send_message(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
        return
    elif option == "Create":
        everyone_role = discord.utils.get(interaction.guild.roles, name="@everyone")
        spectator_role = discord.utils.get(interaction.guild.roles, name="spectator")
        bingo_bot_role = discord.utils.get(interaction.guild.roles, name="Bingo Bot")
        team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_number}")
        
        cat = await interaction.guild.create_category(name=team_name)

        overwrites_with_spectator = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
            bingo_bot_role: bingo_bot_overwrites(),
            interaction.guild.me: bingo_bot_overwrites(),
            spectator_role: spectator_overwrites(),
            team_role: team_overwrites(),
            everyone_role: everyone_overwrites()
            }
        overwrites_w_out_spectator = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
            bingo_bot_role: bingo_bot_overwrites(),
            interaction.guild.me: bingo_bot_overwrites(),
            team_role: team_overwrites(),
            everyone_role: everyone_overwrites()
            }

        await interaction.response.defer(thinking=True)
        await cat.edit(overwrites=overwrites_with_spectator)
        # Create Default Channels
        # all_channels = []
        for channel in DEFAULT_CHANNELS:
            channel_name = f"team-{team_number}-{channel}"
            if channel_name == f"team-{team_number}-chat":
                overwrites = overwrites_w_out_spectator
            else:
                overwrites = overwrites_with_spectator
            if "voice" in channel_name:
                chan = await interaction.guild.create_voice_channel(name=channel_name, category=cat, overwrites=overwrites)
            else:
                chan = await interaction.guild.create_text_channel(name=channel_name, category=cat, overwrites=overwrites)
                if channel == 'photo-dump':
                    webhook = await chan.create_webhook(name=channel_name)
                    await chan.send(f"Here are instructions for adding Discord Rare Drop Notification to Runelite\n\nDownload the Plugin from Plugin Hub\nCopy this Webhook URL to this channel into the Plugin(Accessed via the settings)")
                    await chan.send(f"{webhook.url}\n")
                    await chan.send(f"Copy in this Tile List to ensure that ALL potential items are captured")
                    list_of_item_names = [x['item_names'] for x in settings['items'].values()]
                    list_of_item_names = [x.replace("*", "\*") for x in list_of_item_names]
                    embed = discord.Embed(
                        description=f"{''.join([x.lower() for x in filter(None, list_of_item_names)])}"
                        )
                    await chan.send(embed=embed)
            # all_channels.append(chan)
        await interaction.followup.send(f'Channels created for "{team_name}"')

    elif option == "Set Team Name":
        # Update Settings
        if not new_team_name:
            await interaction.response.send_message(f'No "new_team_name" provided')
        teams_index = dict(zip(settings['teams'].keys(), range(len(settings['teams'].keys()))))
        team_idx = teams_index[team_name]
        new_teams = {}
        for i, pair in enumerate(settings['teams'].items()):
            k, v = pair
            if i == team_idx:
                new_teams.update({new_team_name: v})
            else:
                new_teams.update({k: v})
        settings['teams'] = new_teams
        save_settings_json(settings)
        # Update Category
        team_cat = discord.utils.get(interaction.guild.categories, name=team_name)
        await team_cat.edit(name=new_team_name)
        await interaction.response.send_message(f'Changed Team "{team_name}" to "{new_team_name}"')
    elif option == "Set Tile":
        try:
            tile = int(tile)
        except ValueError:
            await interaction.response.send_message(f'Unable to process tile "tile": {tile} - Ensure it is a number')
            return
        if tile < 1:
            tile = 1
        settings['teams'][team_name]['current'] = tile
        await interaction.response.send_message(f'Updated tile for Team: {team_name} to {tile}')
        update_settings_json(settings)
    elif option == "Set Prev Tile":
        try:
            tile = int(tile)
        except ValueError:
            await interaction.response.send_message(f'Unable to process prev tile "tile": {tile} - Ensure it is a number')
            return
        if tile < 1:
            tile = None
        settings['teams'][team_name]['prev'] = tile
        await interaction.response.send_message(f'Updated prev tile for Team: {team_name} to {tile}')
        update_settings_json(settings)
    elif option == "Set Reroll":
        await reroll(interaction=interaction, option=option, team_name=team_name)


    # processed, settings = update_settings_json(settings, tiles=sheet_link)
    # await interaction.response.send_message(f"{processed}")
    # embed = discord.Embed(
    #     title="Tile List",
    #     color=discord.Color.blue(),
    #     description='\n'.join([itm['discord_name'] for itm in settings['items'].values()])
    #     )
    # # await interaction.reply(embed=embed)
    # # post in #tile-list
    # tile_list_channel = discord.utils.get(interaction.guild.channels, name="tile-list")
    # await tile_list_channel.send(embed=embed)
    else:
        await interaction.response.send_message(f'Unable to proccess: {interaction.data}\nPlease Try again or contact Administrator.')


@bot.tree.command(name="update_score", description=f"Refresh the Score")
async def update_score(interaction: discord.Interaction):
    settings = load_settings_json()
    await update_server_score_board_channel(interaction=interaction, settings=settings)
    await interaction.response.send_message('Updated!')

bot.run(config.DISCORD_BOT_TOKEN)
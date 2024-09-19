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
import asyncio
import datetime
from discord import Role
from typing import List, Optional
from PIL import Image, ImageDraw

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

DICE_SIDES = 8

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

IMAGE_PATH = os.path.join(os.getcwd(), "images")
print(f"{IMAGE_PATH = }")

ROLES = ["Team 1", "Team 2", "Team 3", "Team 4", "Team 5", "Team 6", "Team 7"]
TEAM_CAPTAIN_ROLES = [
    "Team 1 Captain",
    "Team 2 Captain",
    "Team 3 Captain",
    "Team 4 Captain",
    "Team 5 Captain",
    "Team 6 Captain",
    "Team 7 Captain",
]

DEFAULT_CHANNELS = ["chat", "bingo-card", "drop-spam", "pets", "voice-chat"]
CANDYLAND_DEFAULT_CHANNELS = [
    "chat",
    "bingo-card",
    "dice-roll",
    "photo-dump",
    "voice-chat",
]

default_settings_dict = {
    "bot_mode": {"bot_options": ["candyland", "normal"], "current": "candyland"},
    "tiles": {"url": "", "spreadsheet_id": "", "items": {}},
    "teams": {
        "Team 1": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
        "Team 2": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
        "Team 3": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
        "Team 4": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
        "Team 5": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
        "Team 6": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
        "Team 7": {"current": 0, "prev": None, "reroll": True, "roll_history": []},
    },
}

roll_channel = "dice-roll"
mod_channel = "bot-commands"

thumb = "\N{THUMBS UP SIGN}"
thumbs_down = "\N{THUMBS DOWN SIGN}"


# ======================================= Utility Commands ====================================================


def roll_dice(num=DICE_SIDES):
    """
    Roll a dice with the specified number of sides.

    Args:
        num (int): Number of sides on the dice. Default is 8.

    Returns:
        int: The result of the dice roll.
    """
    return random.randint(1, num)


def create_discord_friendly_name(text):
    """
    Create a Discord-friendly name by converting spaces to dashes and removing special characters.

    Args:
        text (str): The text to convert.

    Returns:
        str: The converted Discord-friendly name.
    """
    return (
        text.lower()
        .replace(" ", "-")
        .replace("'", "")
        .replace("*", "")
        .replace("?", "")
        .replace(",", "")
    )


def create_settings_json():
    """
    Create a settings.json file with default settings.
    """
    with open("settings.json", "w") as f:
        json.dump(default_settings_dict, f, indent=4)
        print("created settings.json file")


def load_settings_json():
    """
    Load the settings from the settings.json file.

    Returns:
        dict: The loaded settings.
    """
    if not os.path.exists("settings.json"):
        print("trying to load settings.json but file does not exist")
        create_settings_json()
    with open("settings.json") as f:
        settings = json.load(f)
        # print('loaded settings.json file')
        return settings


def save_settings_json(contents: dict) -> None:
    """
    Save the settings to the settings.json file.

    Args:
        contents (dict): The settings to save.
    """
    with open("settings.json", "w") as f:
        # print('saved settings.json file')
        json.dump(contents, f, indent=4)


def update_settings_json(
    contents: dict, *, url: str = None, process_sheet: bool = False
) -> (str, dict):
    """
    Update the settings in the settings.json file.

    Args:
        contents (dict): The current settings.
        url (str, optional): The new URL to update. Defaults to None.
        process_sheet (bool, optional): Whether to process the Google Sheet. Defaults to False.

    Returns:
        tuple: A string indicating the updates made and the updated settings.
    """
    if process_sheet and url:
        contents = update_tiles_url(contents, url, process_sheet=True)
        updates = 'Updated tiles "url", "items", and "spreadsheet_id"'
    elif url:
        contents = update_tiles_url(contents, url, process_sheet=False)
        updates = 'Updated "url" and "spreadsheet_id"'
    else:
        # print(contents['teams'])
        save_settings_json(contents)
        updates = "Updated Team turn information"
    return updates, contents


def update_roll_settings(roll, team_name, settings, prev, current, reroll=False):
    """
    Update the roll settings for a team in the bingo bot.

    Args:
        roll (str): The roll to be added to the team's roll history.
        team_name (str): The name of the team.
        settings (dict): The current settings dictionary.
        prev (int): The previous roll value.
        current (int): The current roll value.
        reroll (bool, optional): Indicates if the roll is a reroll. Defaults to False.

    Returns:
        dict: The updated settings dictionary.
    """
    if reroll:
        settings["teams"][team_name]["roll_history"].append("reroll")
    settings["teams"][team_name]["roll_history"].append(roll)
    settings["teams"][team_name]["prev"] = prev
    settings["teams"][team_name]["current"] = current
    return settings


def formatted_title(settings, team_name):
    """
    Formats the title for a specific tile based on the given settings and team name.

    Args:
        settings (dict): The settings dictionary containing information about the tiles.
        team_name (str): The name of the team.

    Returns:
        str: The formatted title for the tile.
    """
    tile_num = settings["teams"][team_name]["current"]
    name = settings["items"][str(tile_num)]["name"]
    desc = settings["items"][str(tile_num)]["short_desc"]
    return f"{tile_num} - {name} - {desc}"


def format_item_list(contents, tile_list: list) -> list:
    """
    Format the item list from the Google Sheet.

    Args:
        contents (dict): The current settings.
        tile_list (list): The list of items from the Google Sheet.

    Returns:
        list: The formatted item list.
    """
    items = {}
    for i, item in enumerate(tile_list):
        if i == 0:
            # skip header
            continue
        if contents["bot_mode"]["current"] == "candyland":
            tile_num, name, short_desc, desc, sabotage, item_names, diff = item
            frmt_item = {
                i: {
                    "tile_num": tile_num,
                    "name": name,
                    "short_desc": short_desc,
                    "desc": desc,
                    "sabotage": sabotage,
                    "item_names": item_names,
                    "discord_name": f"{i}. {name} - {desc}",
                }
            }
        else:
            name, desc = item
            frmt_item = {
                i: {"name": name, "desc": desc, "discord_name": f"{name} - {desc}"}
            }
        items.update(frmt_item)
    contents["items"] = items
    return contents


def load_sheet(SAMPLE_SPREADSHEET_ID, RANGE="A1:Z100"):
    """
    Load the Google Sheet data.

    Args:
        SAMPLE_SPREADSHEET_ID (str): The ID of the Google Sheet.
        RANGE (str, optional): The range of cells to retrieve. Defaults to "A1:Z100".

    Returns:
        list: The values from the Google Sheet.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("sheets", "v4", credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = (
            sheet.values()
            .get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=RANGE)
            .execute()
        )
        values = result.get("values", [])

        if not values:
            print("No data found.")
            return

        for row in values:
            print(row)
        return values

    except HttpError as err:
        print(err)


def update_tiles_url(contents: dict, url: str, *, process_sheet: bool = False) -> dict:
    """
    Update the tiles URL in the settings and optionally process the Google Sheet.

    Args:
        contents (dict): The current settings.
        url (str): The new URL to update.
        process_sheet (bool, optional): Whether to process the Google Sheet. Defaults to False.

    Returns:
        dict: The updated settings.
    """
    contents["tiles"]["url"] = url
    spreadsheet_id = url.split("https://docs.google.com/spreadsheets/d/")[-1].split(
        "/"
    )[0]
    contents["tiles"]["spreadsheet_id"] = spreadsheet_id
    if process_sheet:
        items = load_sheet(spreadsheet_id)
        contents = format_item_list(contents, items)
    save_settings_json(contents)
    # print(updates, contents, spreadsheet_id)
    return contents


def create_tile_embed(tiles: dict, tile_number: str) -> discord.Embed:
    """
    Create a Discord embed for a specific tile.

    Args:
        tiles (dict): The dictionary of tiles.
        tile_number (str): The number of the tile.

    Returns:
        discord.Embed: The created Discord embed.
    """
    itm = tiles[tile_number]
    # multi_wiki_urls = itm['wiki_url'].split(',')
    # multi_img_urls = itm['img_url'].split(',')
    # if len(multi_img_urls) > 1:
    # img_url = multi_img_urls[0]
    embed = discord.Embed(
        title=f"{itm['tile_num']} - {itm['name']} - {itm['short_desc']}",
        description=itm["desc"],
        color=0xF7E302,
        # url=multi_wiki_urls[0]
    )
    # embed.set_image(url=img_url)
    # for wiki_url in multi_wiki_urls:
    #     name = wiki_url.split('/')[-1].replace('_', " ")
    #     embed.add_field(name=name, value=f"[{name}]({wiki_url})", inline=False)
    return embed


def mark_on_image_tile_complete(team_name: str, row: int, column: int) -> None:
    """
    Mark a tile as complete on the team's image.

    Args:
        team_name (str): The name of the team.
        row (int): The row number of the tile.
        column (int): The column number of the tile.
    """
    # Open the image
    settings = load_settings_json()
    image_path = os.path.abspath(settings["teams"][team_name]["image"])
    image_bounds = settings["teams"][team_name]["image_bounds"]
    img = Image.open(image_path)
    x_offset = image_bounds["x_offset"] if image_bounds["x_offset"] else 0
    y_offset = image_bounds["y_offset"] if image_bounds["y_offset"] else 0
    x_right_offset = (
        image_bounds["x_right_offset"] if image_bounds["x_right_offset"] else 0
    )
    y_bottom_offset = (
        image_bounds["y_bottom_offset"] if image_bounds["y_bottom_offset"] else 0
    )
    gutter = image_bounds["gutter"] if image_bounds["gutter"] else 0
    if image_bounds["x"] == 0 and image_bounds["y"] == 0:
        width, height = img.size
        width = width - (x_offset + x_right_offset + (4 * gutter))
        height = height - (y_offset + y_bottom_offset + (4 * gutter))
    else:
        width = image_bounds["x"]
        height = image_bounds["y"]

    line_width = int(width * 0.01 / 2)

    # Calculate the dimensions of each bingo tile
    tile_width = width // 5  # Assuming a 5x5 bingo board
    tile_height = height // 5

    # Adjust the row and column to be zero-indexed
    row -= 1
    column -= 1

    # Calculate the coordinates of the specified bingo tile
    x1 = (column * tile_width) + x_offset + (column * gutter)
    y1 = (row * tile_height) + y_offset + (row * gutter)
    x2 = ((column + 1) * tile_width) + x_offset + (column * gutter)
    y2 = ((row + 1) * tile_height) + y_offset + (row * gutter)

    # Create a drawing object
    draw = ImageDraw.Draw(img)

    # Draw a red square on the specified bingo tile
    draw.rectangle([x1, y1, x2, y2], outline="red", width=line_width)

    # Draw an X on the square
    draw.line([(x1, y1), (x2, y2)], fill="red", width=line_width)
    draw.line([(x1, y2), (x2, y1)], fill="red", width=line_width)

    # Save the modified image
    img_name = f"{team_name}-{row+1}-{column+1}.png"
    new_image_path = os.path.join(os.path.dirname(image_path), img_name)
    img.save(new_image_path)
    settings["teams"][team_name]["image"] = new_image_path
    update_settings_json(settings)
    return settings


async def parse_table_location(location: str):
    if location == "":
        return 0, 0
    col, row = location[0], location[1]
    if col.lower() == "a":
        col = 1
    elif col.lower() == "b":
        col = 2
    elif col.lower() == "c":
        col = 3
    elif col.lower() == "d":
        col = 4
    elif col.lower() == "e":
        col = 5
    else:
        col = 0
    return int(row), int(col)


def generate_team_assignment_text(all_roles, total_teams) -> str:
    """
    Generate a text representation of team assignments based on the given roles and total number of teams.

    Parameters:
    all_roles (list): A list of roles representing the teams.
    total_teams (int): The total number of teams to generate assignments for.

    Returns:
    str: A string representation of team assignments, with each line containing the role name followed by the IDs of the members in that role.
    """
    content = []
    all_roles.sort(key=lambda x: x.name)
    for i, role in enumerate(all_roles):
        print(i, role.name)
        if i >= total_teams:
            continue
        formatted_text = f"# {role.name}:\n{' '.join([f'<@{str(r.id)}>' for r in role.members])}\n"
        content.append(formatted_text)
    content.sort()
    return '\n'.join(content)

# ======================================= Discord Interaction Functions ====================================================


async def get_default_channels(interaction: discord.Interaction):
    """
    Get the default channels based on the current bot mode.

    Args:
        interaction (discord.Interaction): The Discord interaction object.

    Returns:
        list: The list of default channels.
    """
    settings = load_settings_json()
    if settings["bot_mode"]["current"] == "candyland":
        return CANDYLAND_DEFAULT_CHANNELS
    else:
        # using the discord.Interaction object to prompt initial sender for text input
        if settings["items"]:
            discord_safe_names = [
                {"name": name, "description": ""} for name in DEFAULT_CHANNELS
            ]
            discord_safe_names += [
                {
                    "name": create_discord_friendly_name(itm["name"]),
                    "description": itm["desc"],
                }
                for itm in settings["items"].values()
            ]
            return discord_safe_names
        else:
            await interaction.followup.send(
                "Tile information is missing. Please update with /set_tiles <google sheet link>",
                ephemeral=True,
            )
        # process response
        # return respons


async def clear_team_roles(interaction):
    """
    Clear the team roles from all members in the guild.

    Args:
        interaction: The Discord interaction object.
    """
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    for member in interaction.guild.members:
        await member.remove_roles(*roles)
    print("Removed Team Roles from All Members")


async def post_or_update_bingo_card(
    interaction: discord.Interaction,
    settings: dict,
    team_name: str,
    *,
    update: bool = False,
    row: int = None,
    column: int = None,
) -> None:
    """
    Posts or updates a bingo card image for a specific team in a Discord channel.

    Parameters:
        interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
        settings (dict): The settings dictionary containing information about the teams and their bingo cards.
        team_name (str): The name of the team for which the bingo card image should be posted or updated.
        update (bool, optional): Indicates whether the bingo card image should be updated. Defaults to False.
        row (int, optional): The row number of the tile to be marked as complete. Required if update is True. Defaults to None.
        column (int, optional): The column number of the tile to be marked as complete. Required if update is True. Defaults to None.

    Returns:
        None
    """
    for cat in interaction.guild.categories:
        if cat.name == team_name:
            bingo_card_chan = [x for x in cat.channels if x.name == "bingo-card"][0]
            processed = False
            async for message in bingo_card_chan.history(limit=1):
                if message.author == bot.user:
                    if update and row and column:
                        settings = mark_on_image_tile_complete(
                            team_name, row=row, column=column
                        )
                        img = discord.File(settings["teams"][team_name]["image"])
                    else:
                        img = discord.File(settings["teams"][team_name]["image"])
                    await message.edit(attachments=[img])
                    processed = True
                    print(
                        f'{"Updated" if update and row and column else "Posted"} {team_name} Bingo Card Image'
                    )
            else:
                if not processed:
                    print("image didnt exist, posting new image")
                    print(settings["teams"][team_name]["image"])
                    if update and row and column:
                        settings = mark_on_image_tile_complete(
                            team_name, row=row, column=column
                        )
                        img = discord.File(settings["teams"][team_name]["image"])
                    else:
                        img = discord.File(settings["teams"][team_name]["image"])
                    embed = discord.Embed(
                        title=f"{team_name} Bingo Card",
                        color=0xF7E302,
                    )
                    embed.set_image(
                        url=f"attachment://{settings['teams'][team_name]['image']}"
                    )
                    await bingo_card_chan.send(embed=embed, file=img)
                else:
                    print("image was already posted")


async def update_team_bingo_card_channel(
    interaction: discord.Interaction, team_name, roll, settings, reroll=False
):
    """
    Updates the bingo card channel for a specific team with the latest dice roll and tile information.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team whose bingo card channel needs to be updated.
    - roll (int): The dice roll value.
    - settings (dict): The settings dictionary containing the current state of the bingo game.
    - reroll (bool, optional): Indicates whether the dice roll is a reroll. Defaults to False.
    """
    for ch in interaction.channel.category.channels:
        if ch.name.endswith("bingo-card"):
            await ch.send(
                f"{'Rerolling ' if reroll else ''}Dice roll: {roll} for team: {team_name}\nNew tile: {settings['teams'][team_name]['current']} << Old tile: {settings['teams'][team_name]['prev']}\nRerolls remaining: {settings['teams'][team_name]['reroll']}"
            )


async def update_reroll_team_bingo_card_channel(
    interaction: discord.Interaction, team_name, settings, used=True
):
    """
    Updates the team's bingo card channel with the information about the reroll.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team.
    - settings (dict): The settings dictionary containing information about the teams and their rerolls.
    - used (bool, optional): Indicates whether the reroll was used or awarded. Defaults to True.
    """
    for ch in interaction.guild.channels:
        if ch.name.endswith(f"{create_discord_friendly_name(team_name)}-bingo-card"):
            await ch.send(
                f"Reroll was {'used' if used else 'awarded'} for team: {team_name}\nRerolls remaining: {settings['teams'][team_name]['reroll']}"
            )


async def update_server_score_board_channel(interaction: discord.Interaction, settings):
    """
    Updates the score board channel in the server with the current scores and team information.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command interaction.
    - settings (dict): The settings dictionary containing the bot configuration.

    Returns:
    None
    """
    score_card_ch = discord.utils.get(interaction.guild.channels, name="score-board")
    if settings["posts"]["score-board"]["id"]:
        msg_id = int(settings["posts"]["score-board"]["id"])
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
        msg = await score_card_ch.send(
            content=settings["posts"]["score-board"]["content"]
        )
        msg_id = msg.id
        message = await score_card_ch.fetch_message(msg_id)
    if message.content != settings["posts"]["score-board"]["content"]:
        print("score is out of sync")
    total_teams = settings["total_teams"]
    teams_names = [x for x in settings["teams"].keys()]
    teams_scores = [x["current"] for x in settings["teams"].values()]
    teams_rerolls = [x["reroll"] for x in settings["teams"].values()]
    content_text = []
    for i in range(len(teams_names)):
        if i >= total_teams:
            continue
        if settings["bot_mode"]["current"] == "candyland":
            row = f"{teams_names[i]}: {teams_scores[i]} - Rerolls remain: {teams_rerolls[i]}"
        else:
            row = f"{teams_names[i]}: {teams_scores[i]}"
        content_text.append(row)
    settings["posts"]["score-board"]["id"] = msg_id
    settings["posts"]["score-board"]["content"] = "\n".join(content_text)
    update_settings_json(settings)
    await message.edit(content="\n".join(content_text))


async def process_all_spectators(interaction, roles, spectator_role, unassign):
    """
    Process all spectators by removing specified roles from all server members and optionally adding the spectator role.

    Parameters:
    - interaction: The interaction object representing the command interaction.
    - roles: A list of roles to be removed from all server members.
    - spectator_role: The role to be added to all server members as spectators.
    - unassign: A boolean indicating whether to remove the spectator role from all server members.

    Returns:
    None
    """
    # members = interaction.guild.members
    guild_roles = interaction.guild.roles
    for r in guild_roles:
        if r in roles:
            for m in r.members:
                if discord.RateLimited:
                    print("Rate Limited, pausing 10s")
                    await asyncio.sleep(10)
                await m.remove_roles(r)
                if not unassign:
                    await m.add_roles(spectator_role)
    # for m in members:
    #     roles_to_remove = [r for r in m.roles if r in roles]
    #     print()
    #     print(roles_to_remove)
    #     print(roles)
    #     print()
    #     if not roles_to_remove:
    #         continue
    #     if discord.RateLimited:
    #         print('Rate Limited, pausing 10s')
    #         await asyncio.sleep(10)
    #     await m.remove_roles(*roles_to_remove)
    #     if not unassign:
    #         await m.add_roles(spectator_role)
    print("All members have been updated")
    await interaction.followup.send(
        f'Role "spectator" {"added to" if not unassign else "purged from"} all server members'
    )


# ======================================= Discord Roles Functions ====================================================


def team_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=False,
        manage_messages=True,
        read_message_history=True,
        embed_links=True,
        attach_files=True,
        manage_permissions=False,
        speak=True,
        deafen_members=True,
        move_members=True,
        manage_webhooks=False,
        create_instant_invite=False,
        send_messages=True,
        connect=True,
    )


def spectator_overwrites():
    return discord.PermissionOverwrite(
        view_channel=True,
        speak=True,
        manage_channels=False,
        manage_messages=False,
        manage_permissions=False,
        manage_webhooks=False,
        create_instant_invite=False,
        send_messages=False,
        connect=True,
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
        read_message_history=True,
    )


def everyone_overwrites():
    return discord.PermissionOverwrite(
        view_channel=False, create_instant_invite=False, send_messages=False
    )


def general_chat_restrict_overwrites():
    return discord.PermissionOverwrite(
        view_channel=False,
        manage_channels=False,
        manage_messages=False,
        manage_permissions=False,
        manage_webhooks=False,
        send_messages=False,
    )


# ======================================= Discord Autocomplete Functions ====================================================


async def team_names_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """
    Autocompletes team names based on the current input.

    Args:
        interaction (discord.Interaction): The interaction object.
        current (str): The current input string.

    Returns:
        List[app_commands.Choice[str]]: A list of app_commands.Choice objects representing the autocompleted team names.
    """
    settings = load_settings_json()
    team_names = settings["teams"].keys()
    return [
        app_commands.Choice(name=team_name, value=team_name)
        for team_name in team_names
        if current.lower() in team_name.lower()
    ]


async def process_sheet_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """
    Process the sheet autocomplete options.

    Args:
        interaction (discord.Interaction): The interaction object.
        current (str): The current input string.

    Returns:
        List[app_commands.Choice[str]]: The list of autocomplete choices.
    """
    return [
        app_commands.Choice(name="Only store link for later processing", value=False),
        app_commands.Choice(
            name="Retrieve sheet data to generate tile list", value=True
        ),
    ]


# ======================================= Bot Commands ====================================================


@bot.event
async def on_ready():
    print("Bot is Ready")
    # print('We have logged in as {0.user}'.format(client))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# @bot.event
# async def on_guild_role_update(before, after):
#     print(f"Role Updated: {before.name} -> {after.name}")
#     # TODO Implement this so #team-assignments gets updated too


@bot.tree.command(
    name="roll",
    description=f"Roll a d{DICE_SIDES} in your teams {roll_channel} channel. Creates new channel for the newly rolled tile.",
)
async def roll(interaction: discord.Interaction):
    """
    Rolls the dice for a team in the bingo game.
    uses roll_dice() to get a random number between 1 and DICE_SIDES
    Requires the user to have the appropriate team role and be in the correct channel: roll_channel.
    Updates the team's current tile, previous tile, and roll history in the settings.
    Creates a new channel for the newly rolled tile and posts the tile information in the channel.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    None
    """
    settings = load_settings_json()
    await interaction.response.defer(thinking=True)
    # put a check for has role in here
    team_name = interaction.channel.category.name
    role_name = discord.utils.get(interaction.guild.roles, name=team_name)
    if (
        not role_name in interaction.user.roles
        or not roll_channel in interaction.channel.name
    ):
        await interaction.followup.send(
            f"Please ensure you have approriate Team Role and are within your Team's #{roll_channel}"
        )
        return
    else:
        if settings["running"] == False:
            await interaction.followup.send(
                "Rolling is not enabled, either wait till Start time or message @ Bingo Moderator if receiving this message in error."
            )
            return
        roll = roll_dice()
        # create function to handle updating settings points
        settings = load_settings_json()
        settings = update_roll_settings(
            roll,
            team_name,
            settings,
            prev=settings["teams"][team_name]["current"],
            current=settings["teams"][team_name]["current"] + roll,
        )
        # TODO
        total_tiles = len(settings["items"])
        if settings["teams"][team_name]["prev"] == total_tiles:
            # Checks if last prev tile was the last tile of the bingo
            # await message.add_reaction("\n{TADA}")
            await interaction.followup.send(
                f'Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}'
            )
            return
        elif settings["teams"][team_name]["current"] > total_tiles:
            # This makes the last tile mandatory
            settings["teams"][team_name]["current"] = total_tiles
        # roll_info = settings['items'][str(settings['teams'][team_name]['current'])]
        # print(f"{roll_info = }")
        update_settings_json(settings)

        title = formatted_title(settings, team_name)
        await interaction.followup.send(
            f"Rolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
        )
        name = create_discord_friendly_name(
            f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
        )
        ch = await interaction.channel.clone(name=name)
        embed = create_tile_embed(
            tiles=settings["items"],
            tile_number=str(settings["teams"][team_name]["current"]),
        )
        await ch.send(embed=embed)

        # Check if Sabotage Tile
        if sabotage := settings["items"][str(settings["teams"][team_name]["current"])][
            "sabotage"
        ]:
            print(sabotage)
            if "-" in sabotage:
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=settings["teams"][team_name]["current"] + int(sabotage),
                )
                # message in skipped channel
                await ch.send(
                    f"SABOTAGED: Go back to tile {settings['teams'][team_name]['current']}"
                )
            elif "reroll" in sabotage.lower():

                # Needs to auto reroll
                roll = roll_dice()
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=settings["teams"][team_name]["current"] + roll,
                )
                # message in skipped channel
                await ch.send(
                    f"SKIPPED: Goto tile {settings['teams'][team_name]['current']}"
                )
            else:
                # message in skipped channel
                await ch.send(f"SABOTAGED: Goto tile {sabotage}")
                # Go to tile
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=int(sabotage),
                )
            title = formatted_title(settings, team_name)
            await interaction.channel.send(
                f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
            )

            name = create_discord_friendly_name(
                f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
            )
            ch = await interaction.channel.clone(name=name)
            embed = create_tile_embed(
                tiles=settings["items"],
                tile_number=str(settings["teams"][team_name]["current"]),
            )
            await ch.send(embed=embed)

        # Add updating the TEAMS bingo card channel
        await update_team_bingo_card_channel(interaction, team_name, roll, settings)

        # Add updating the Server's Bingo card Channel
        await update_server_score_board_channel(interaction, settings)


@bot.tree.command(
    name="reroll",
    description=f"Reroll a d{DICE_SIDES} in your teams {roll_channel} channel, nulling the last roll and rolls from the prev tile.",
)
async def reroll(interaction: discord.Interaction):
    """
    Rerolls the dice for a team in the bingo game.
    Requires the user to have the appropriate team role and be in the correct channel: roll_channel.
    Uses previous tile and roll to determine the new tile.
    5/2/24 - Currently can reroll the same tile that it is on. This needs to be updated.

    Updates the team's current tile, previous tile, and roll history in the settings.
    Creates a new channel for the newly rolled tile and posts the tile information in the channel.


    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    None
    """
    team_name = interaction.channel.category.name
    role_name = discord.utils.get(interaction.guild.roles, name=team_name)
    await interaction.response.defer(thinking=True)
    if (
        not role_name in interaction.user.roles
        or not roll_channel in interaction.channel.name
    ):
        await interaction.followup.send(
            f"Please ensure you have approriate Team Role and are within your Team's #{roll_channel}"
        )
        return
    else:
        settings = load_settings_json()
        if settings["running"] == False:
            await interaction.followup.send(
                "Rolling is not enabled, either wait till Start time or message @ Bingo Moderator if receiving this message in error."
            )
            return
        settings = load_settings_json()
        team_name = interaction.channel.category.name
        if settings["teams"][team_name]["reroll"] > 0:
            # clear existing channel
            name = create_discord_friendly_name(
                f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
            )
            print(f"{name = }")
            # prev_ch = discord.utils.get(interaction.channel.category.channels, name=name)
            # messages = [x async for x in prev_ch.history(limit=2)]
            # if prev_ch and len(messages) == 1:
            #     await prev_ch.delete()
            #     print(f'Deleted Channel {name} after a successful reroll')
            # elif prev_ch:
            #     await interaction.followup.send(f'Unable to clean up channel <#{discord.utils.get(interaction.guild.channels, name=name).id}> pinging {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}')
            # return #TODO re-enable this line
            roll = roll_dice()
            settings = update_roll_settings(
                roll,
                team_name,
                settings,
                prev=settings["teams"][team_name]["prev"],
                current=settings["teams"][team_name]["prev"] + roll,
                reroll=True,
            )
            settings["teams"][team_name]["reroll"] -= 1
            total_tiles = len(settings["items"])
            if settings["teams"][team_name]["prev"] == total_tiles:
                # Checks if last prev tile was the last tile of the bingo
                # await message.add_reaction("\n{TADA}")
                await interaction.followup.send(
                    f'Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}'
                )
                return
            elif settings["teams"][team_name]["current"] > total_tiles:
                # This makes the last tile mandatory
                settings["teams"][team_name]["current"] = total_tiles
            update_settings_json(settings)
            title = formatted_title(settings, team_name)
            await interaction.followup.send(
                f"ReRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
            )

            name = create_discord_friendly_name(
                f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
            )
            ch = await interaction.channel.clone(name=name)
            embed = create_tile_embed(
                tiles=settings["items"],
                tile_number=str(settings["teams"][team_name]["current"]),
            )
            await ch.send(embed=embed)

            # Check if Sabotage Tile
            if sabotage := settings["items"][
                str(settings["teams"][team_name]["current"])
            ]["sabotage"]:
                print(sabotage)
                if "-" in sabotage:
                    settings = update_roll_settings(
                        roll,
                        team_name,
                        settings,
                        prev=settings["teams"][team_name]["current"],
                        current=settings["teams"][team_name]["current"] + int(sabotage),
                    )
                    # message in skipped channel
                    await ch.send(
                        f"SABOTAGED: Go back to tile {settings['teams'][team_name]['current']}"
                    )
                elif "reroll" in sabotage.lower():

                    # Needs to auto reroll
                    roll = roll_dice()
                    settings = update_roll_settings(
                        roll,
                        team_name,
                        settings,
                        prev=settings["teams"][team_name]["current"],
                        current=settings["teams"][team_name]["current"] + roll,
                    )
                    # message in skipped channel
                    await ch.send(
                        f"SKIPPED: Goto tile {settings['teams'][team_name]['current']}"
                    )
                else:
                    # message in skipped channel
                    await ch.send(f"SABOTAGED: Goto tile {sabotage}")
                    # Go to tile
                    settings = update_roll_settings(
                        roll,
                        team_name,
                        settings,
                        prev=settings["teams"][team_name]["current"],
                        current=int(sabotage),
                    )
                title = formatted_title(settings, team_name)
                await interaction.channel.send(
                    f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
                )

                name = create_discord_friendly_name(
                    f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
                )
                ch = await interaction.channel.clone(name=name)
                embed = create_tile_embed(
                    tiles=settings["items"],
                    tile_number=str(settings["teams"][team_name]["current"]),
                )
                await ch.send(embed=embed)

            # Add updating the TEAMS bingo card channel
            await update_team_bingo_card_channel(
                interaction, team_name, roll, settings, reroll=True
            )
            # Add updating the Server's Bingo card Channel
            await update_server_score_board_channel(interaction, settings)

            # await roll_reply.edit(content=f"{roll_reply.content}\nCreated new channel <#{discord.utils.get(interaction.guild.channels, name=name).id}> for {discord.utils.get(interaction.guild.roles, name=team_name).mention}")
        else:
            await interaction.followup.send(f"NO MORE REROLLS MFER!")


@has_role("Bingo Moderator")
@bot.tree.command(
    name="upload_tiles",
    description=f"Sets the Bingo Tiles from a Public Google Sheet doc, processes, and formats them.",
)
async def set_tiles(
    interaction: discord.Interaction, sheet_link: str, process_sheet: bool = True
):
    """
    Sets the tiles for the bingo game using a PUBLIC Google Sheet.
    Provide the FULL URL link to the Google Sheets document containing the tile data.
    settings['items'] will get updated with the new tile URL.
    If process_sheet is True, the sheet will be processed and the settings will be updated.

    Example of Normal Bingo Template is:
    https://docs.google.com/spreadsheets/d/1zkhEsUOME7lRTQ8m5n3puieyKJsG3fcqiiTonQQwWoA/edit?usp=sharing

    Example of Candyland Bingo Template is:
    https://docs.google.com/spreadsheets/d/1-S-m4r3JCMdzbc-AfBCaUDPQO08SQWC0vjcwO44kHBg/edit?usp=sharing

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's command.
    - sheet_link (str): The FULL URL link to the Google Sheets document containing the tile data.
    - process_sheet (bool, optional): Whether to process the sheet and update the settings. Defaults to True.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
<<<<<<< HEAD
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.followup.send(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
=======
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
    # await interaction.response.edit_message(suppress=True)
    settings = load_settings_json()
    processed, settings = update_settings_json(
        settings, url=sheet_link, process_sheet=process_sheet
    )
    await interaction.followup.send(f"{processed}")


@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role("Bingo Moderator")
@bot.tree.command(
    name="clear_team_role", description=f"Clear Team <#> Role from all players assigned"
)
async def clear_team_role(interaction: discord.Interaction, team_name: str):
    """
    Disbands a team by removing the corresponding role from all members in the guild.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command invocation.
    - team_name (str): The name of the team to disband.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    await interaction.response.defer(thinking=True)
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
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
            if not users_processed:
                raise ValueError
            await interaction.followup.send(
                f'Disbanded Team: {team_name} Role: "Team {team_number}" removing the role from {users_processed} users'
            )
        except ValueError:
            await interaction.followup.send(
                f'We ran into issues disbanding Discord Role: "Team {team_number}" OR there are no members in that that role'
            )


@has_role("Bingo Moderator")
@bot.tree.command(
    name="spectators",
    description=f"Assign Spectator Role and clear existing roles to Discord Members",
)
async def spectators(
    interaction: discord.Interaction, members: str, unassign: bool = False
):
    """
    Assigns or unassigns the "spectator" role to the specified members.
    Use of @everyone will assign/unassign the role to all members in the server.
    Specify the unassign parameter to remove or add the role. The default is to add the role(Unassign = False).
    members: @user1 @user2 @user3

    Parameters:
    - interaction: The discord.Interaction object representing the interaction with the bot.
    - members: A string containing the mentions of the members to assign/unassign the role to.
    - unassign: A boolean indicating whether to unassign the role (default: False).

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    spectator_role = discord.utils.get(interaction.guild.roles, name="spectator")
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    roles.append(spectator_role)
    members = members.split()
    if members[0] == "@everyone" and unassign:
        process_all_spectators(interaction, roles, spectator_role, unassign)
    elif len(members) == 0:
        await interaction.followup.send(
            f"Please add @ each member to add them too team"
        )
    else:
        for m in members:
            m_id = int(m.replace("<", "").replace(">", "").replace("@", ""))
            mem = await interaction.guild.fetch_member(m_id)
            await mem.remove_roles(*roles)
            if not unassign:
                await mem.add_roles(spectator_role)
        await interaction.followup.send(
            f'Role "spectator" {"added" if not unassign else "removed"} to {len(members)} members'
        )


@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role("Bingo Moderator")
@bot.tree.command(
    name="add_team_role", description=f"Assign Team <#> Role to Discord Members"
)
async def add_team_role(interaction: discord.Interaction, team_name: str, members: str):
    """
    Adds a team role to the specified members.
    Specify team name and @ the users to add the role to.
    members: @user1 @user2 @user3

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command invocation.
    - team_name (str): The name of the team to add the role for.
    - members (str): A string containing the mentions of the members to add the role to.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    current_role = discord.utils.get(
        interaction.guild.roles, name=f"Team {team_number}"
    )
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    members = members.split()
    for m in members:
        m_id = int(m.replace("<", "").replace(">", "").replace("@", ""))
        mem = await interaction.guild.fetch_member(m_id)
        await mem.remove_roles(*roles)
        await mem.add_roles(current_role)
<<<<<<< HEAD
    await interaction.followup.send(
        f'Role "Team {team_number}" added to {len(members)} members'
    )
=======
    await process_team_assignment_updates(interaction)
    await interaction.followup.send(f'Role "Team {team_number}" added to {len(members)} members')
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475


async def configure_reroll(interaction: discord.Interaction, team_name: str):
    """
    Configures the reroll functionality for a team.
    Requires the user to grant or revoke a reroll for the team by responding to the bot's message

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team.

    Returns:
    None
    """

    class Reroll(discord.ui.View):
        def __init__(self, *, timeout: Optional[float] = 180):
            super().__init__(timeout=timeout)

        @discord.ui.button(label="Revoke", style=discord.ButtonStyle.danger)
        async def revoke_reroll(
            self, interaction: discord.Interaction, Button: discord.ui.Button
        ):
            """
            Revokes a reroll for the team.

            Parameters:
            - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            - Button (discord.ui.Button): The button that triggered the interaction.

            Returns:
            None
            """
            settings = load_settings_json()
            if settings["teams"][team_name]["reroll"] == 0:
                await interaction.followup.send(
                    content="No Rerolls exist for that team."
                )
            else:
                settings["teams"][team_name]["reroll"] -= 1
                update_settings_json(settings)
                await interaction.response.edit_message(
                    content=f"1 Reroll has been removed for that team.\n{team_name}: {settings['teams'][team_name]['reroll']} Reroll(s) remain",
                    view=self,
                )
                # Add updating the TEAMS bingo card channel
                await update_reroll_team_bingo_card_channel(
                    interaction, team_name, settings, used=True
                )
                # Add updating the Server's Bingo card Channel
                await update_server_score_board_channel(interaction, settings)

        @discord.ui.button(label="Give", style=discord.ButtonStyle.green)
        async def give_reroll(
            self, interaction: discord.Interaction, Button: discord.ui.Button
        ):
            """
            Gives a reroll to the team.

            Parameters:
            - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            - Button (discord.ui.Button): The button that triggered the interaction.

            Returns:
            None
            """
            settings = load_settings_json()
            settings["teams"][team_name]["reroll"] += 1
            update_settings_json(settings)
            await interaction.response.edit_message(
                content=f"1 Reroll is added to that team.\n{team_name}: {settings['teams'][team_name]['reroll']} Reroll(s) remain",
                view=self,
            )
            # Add updating the TEAMS bingo card channel
            await update_reroll_team_bingo_card_channel(
                interaction, team_name, settings, used=False
            )
            # Add updating the Server's Bingo card Channel
            await update_server_score_board_channel(interaction, settings)

    await interaction.response.send_message(
        "Choose an option for Reroll:", view=Reroll()
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="delete_team",
    description=f"Delete all channels for a team and the team category.",
)
async def delete_team(interaction: discord.Interaction, team_name: str):
    """
    Deletes all channels associated with a team.
    Prompts for user's confirmation on bot's response before deleting the channels.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team whose channels are to be deleted.
    """

    class DeleteConfirmation(discord.ui.View):
        """
        A confirmation view for deleting team channels.

        Args:
            team_name (str): The name of the team.
            timeout (Optional[float]): The timeout duration in seconds. Defaults to 180.
        """

        def __init__(self, team_name: str, *, timeout: Optional[float] = 180):
            self.team_name = team_name
            super().__init__(timeout=timeout)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
        async def abort_delete(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            """
            Disables all child buttons except the clicked button, disables the clicked button itself,
            stops the view, and edits the interaction response with a cancellation message.

            Parameters:
            - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            - button (discord.ui.Button): The button that triggered the abort_delete function.

            Returns:
            - None
            """
            for child in self.children:
                if child == button:
                    continue
                else:
                    child.disabled = True
            button.disabled = True
            self.stop()
            await interaction.response.edit_message(
                embed=discord.Embed(description='Cancelled "Delete Channels" command'),
                view=self,
            )

        @discord.ui.button(
            label="Delete All Team Channels", style=discord.ButtonStyle.green
        )
        async def delete_team_channels(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            """
            Deletes the channels associated with a team.

            Parameters:
            - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            - button (discord.ui.Button): The button that triggered the deletion.

            Returns:
            None
            """
            for child in self.children:
                if child == button:
                    continue
                else:
                    child.disabled = True
            button.disabled = True
            settings = load_settings_json()
            team_names = [x for x in settings["teams"].keys()]
            team_number = team_names.index(self.team_name) + 1
<<<<<<< HEAD
            if not interaction.channel.category.name.lower() == "admin":
                await interaction.response.send_message(
                    f"Use this command in {mod_channel} and ADMIN section"
                )
                return
            elif not self.team_name in team_names:
                await interaction.message.edit(
                    embed=discord.Embed(
                        description=f"Team Name: {self.team_name} is not found in {team_names}\nPlease Try again"
                    ),
                    view=self,
                )
=======
            if not self.team_name in team_names:
                await interaction.message.edit(embed=discord.Embed(description=f"Team Name: {self.team_name} is not found in {team_names}\nPlease Try again"), view=self)
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
                return
            print("Deleting...")
            await interaction.message.edit(
                embed=discord.Embed(
                    description=f"Attempting to Delete {self.team_name}'s channels."
                ),
                view=self,
            )
            num_deleted = 0
            cats = interaction.guild.categories
            print([c.name for c in cats])
            for cat in cats:
                if cat.name.lower() == self.team_name.lower():
                    await interaction.message.edit(
                        embed=discord.Embed(
                            description=f"Found {len(cat.channels)} channels. Deleting...."
                        ),
                        view=self,
                    )
                    for ch in cat.channels:
                        print(ch)
                        num_deleted += 1
                        await ch.delete()
                    await cat.delete()
                    if num_deleted > 0:
                        await interaction.message.edit(
                            embed=discord.Embed(
                                description=f"Deleted {self.team_name}'s channels. {num_deleted} channel(s) deleted."
                            ),
                            view=None,
                        )
                else:
                    print(
                        f"Skipping {cat.name}\t{self.team_name}\t{cat.name.lower() == self.team_name.lower()}"
                    )
            else:
                if num_deleted == 0:
                    await interaction.message.edit(
                        embed=discord.Embed(
                            description=f"{self.team_name}: No ({num_deleted}) Channels Deleted"
                        ),
                        view=None,
                    )
            print(f"Deleted {num_deleted} Channels")
            self.stop()

    await interaction.response.send_message(
        embed=discord.Embed(description=f'Confirm Deletion of Team "{team_name}":'),
        view=DeleteConfirmation(team_name=team_name),
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(name="change_team_name", description=f"Change team name.")
async def change_team_name(
    interaction: discord.Interaction, team_name: str, new_team_name: str
):
    """
    Changes the name of a team in the bot settings and updates the corresponding category name.
    Requires the Team Name to be the same as in the settings, will fail if it isn't.
    If fails, change the team name(Category) manually and try running category command again.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command invocation.
    - team_name (str): The current name of the team to be changed.
    - new_team_name (str): The new name for the team.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
<<<<<<< HEAD
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.followup.send(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
    elif not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
=======
    if not team_name in team_names:
        await interaction.followup.send(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
        return
    # Update Settings
    if not new_team_name:
        await interaction.followup.send(
            f'No "new_team_name" provided, Please try again'
        )
    teams_index = dict(
        zip(settings["teams"].keys(), range(len(settings["teams"].keys())))
    )
    team_idx = teams_index[team_name]
    new_teams = {}
    for i, pair in enumerate(settings["teams"].items()):
        k, v = pair
        if i == team_idx:
            new_teams.update({new_team_name: v})
        else:
            new_teams.update({k: v})
    settings["teams"] = new_teams
    # Update Category
    team_cat = discord.utils.get(interaction.guild.categories, name=team_name)
    if not team_cat:
        await interaction.followup.send(f'No Category found for "{team_name}"')
        return
    await team_cat.edit(name=new_team_name)
    save_settings_json(settings)
    await interaction.followup.send(f'Changed Team "{team_name}" to "{new_team_name}"')


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
<<<<<<< HEAD
@bot.tree.command(
    name="update_tiles_channels",
    description=f"Update the bingo tiles for a team. Useful for post start updates.",
)
=======
@bot.tree.command(name="update_tiles_channels", description=f"Updates channel tiles DESCRIPTION AND Initial Message for a team. Doesn't update channel name.")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
async def update_tiles_channels(interaction: discord.Interaction, team_name: str):
    """
    Updates the channels' tiles for a specific team.
    Edits existing message in the channel and updates channel description.
    Used if there are changes to the tiles after the game has started.
    Updates only team specified.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command invocation.
    - team_name (str): The name of the team.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings['teams'].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    not_implemented = False
    # not_implemented = True
    if not_implemented:
        await interaction.followup.send(f"command not implemented yet.")

        """========================== NOT IMPLEMENTED ============================="""

        return
<<<<<<< HEAD
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.followup.send(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
    elif not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
=======
    if not team_name in team_names:
        await interaction.followup.send(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
        return
    cats = interaction.guild.categories
    print([c.name for c in cats])
    channels = await get_default_channels(interaction)
    updated_num = 0
    for cat in cats:
        if cat.name.lower() == team_name.lower():
            print('team cat found', cat.name)
            for ch in cat.channels:
                # look for first message in channel and update it
                if ch.type == discord.ChannelType.text and ch.name in [
                    x["name"] for x in channels
                ]:
                    channel_details = [x for x in channels if x["name"] == ch.name][0]
                    async for message in ch.history(limit=1):
                        if message.author == bot.user:
                            if channel_details["description"] != message.content:
                                if channel_details["description"] != "":
                                    await ch.edit(topic=channel_details["description"])
                                    await message.edit(
                                        content=f"{channel_details['description']}"
                                    )
                                    updated_num += 1
    await interaction.followup.send(
        f"Updated {team_name}'s channels Tiles. {updated_num} channel(s) tiles updated."
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="create_team_channels",
    description=f"Update the bingo tiles for a team. Useful for post start updates.",
)
async def create_team_channels(interaction: discord.Interaction, team_name: str):
    """
    Creates team-specific channels in a Discord server.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's command interaction.
    - team_name (str): The name of the team for which channels will be created.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
<<<<<<< HEAD
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.followup.send(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
    elif not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
=======
    if not team_name in team_names:
        await interaction.followup.send(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
        return
    everyone_role = discord.utils.get(interaction.guild.roles, name="@everyone")
    spectator_role = discord.utils.get(interaction.guild.roles, name="spectator")
    bingo_bot_role = discord.utils.get(interaction.guild.roles, name="Bingo Bot")
    team_role = discord.utils.get(interaction.guild.roles, name=f"Team {team_number}")
    cat = await interaction.guild.create_category(name=team_name)
    overwrites_with_spectator = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            read_messages=False, connect=False
        ),
        bingo_bot_role: bingo_bot_overwrites(),
        interaction.guild.me: bingo_bot_overwrites(),
        spectator_role: spectator_overwrites(),
        team_role: team_overwrites(),
        everyone_role: everyone_overwrites(),
    }
    overwrites_w_out_spectator = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            read_messages=False, connect=False
        ),
        bingo_bot_role: bingo_bot_overwrites(),
        interaction.guild.me: bingo_bot_overwrites(),
        team_role: team_overwrites(),
        everyone_role: everyone_overwrites(),
    }
    await cat.edit(overwrites=overwrites_with_spectator)
    # Create Default Channels
    # all_channels = []
    channels = await get_default_channels(interaction)
    for channel in channels:
        settings = load_settings_json()
        if settings["bot_mode"]["current"] == "candyland":
            channel_name = f"team-{team_number}-{channel}"
            if channel_name == f"team-{team_number}-chat":
                overwrites = overwrites_w_out_spectator
            else:
                overwrites = overwrites_with_spectator
        else:
            channel_name = channel["name"]
            if channel_name == "chat":
                # TODO update this
                # raise Exception("This is not implemented yet, update proper perms")
                channel_name = f"{team_number}-general-{channel_name}"
                overwrites = overwrites_w_out_spectator
            else:
                # raise Exception("This is not implemented yet, update proper perms")
                overwrites = overwrites_with_spectator
        if "voice" in channel_name:
            channel_name = f"{team_number}-{channel_name}"
            chan = await interaction.guild.create_voice_channel(
                name=channel_name, category=cat, overwrites=overwrites
            )
        else:
            chan = await interaction.guild.create_text_channel(
                name=channel_name,
                topic=channel["description"],
                category=cat,
                overwrites=overwrites,
            )
            if channel["description"]:
                await chan.send(f"{channel['description']}")
            if channel_name == "photo-dump" or channel_name == "drop-spam":
                webhook = await chan.create_webhook(name=channel_name)
                message_1 = await chan.send(
                    f"Here are instructions for adding Discord Rare Drop Notification to Runelite\n\nDownload the Plugin from Plugin Hub\nCopy this Webhook URL to this channel into the Plugin(Accessed via the settings)"
                )
                message_2 = await chan.send(f"```{webhook.url}```")
                await message_1.pin()
                await message_2.pin()
                if settings["bot_mode"]["current"] == "candyland":
                    await chan.send(
                        f"Copy in this Tile List to ensure that ALL potential items are captured"
                    )
                    list_of_item_names = [
                        x["item_names"] for x in settings["items"].values()
                    ]
                    list_of_item_names = [
                        x.replace("*", "\*") for x in list_of_item_names
                    ]
                    embed = discord.Embed(
                        description=f"{''.join([x.lower() for x in filter(None, list_of_item_names)])}"
                    )
                    await chan.send(embed=embed)
        # all_channels.append(chan)
    await interaction.followup.send(f'Channels created for "{team_name}"')


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(name="set_tile", description=f"Set the tile/score manually.")
async def set_tile(interaction: discord.Interaction, team_name: str, tile: int):
    """
    Sets the current tile for a given team in the OSRS Bingo Discord Bot.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's command.
    - team_name (str): The name of the team for which to set the tile.
    - tile (int): The tile number to set for the team.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
<<<<<<< HEAD
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.followup.send(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
    elif not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
=======
    if not team_name in team_names:
        await interaction.followup.send(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
        return
    try:
        tile = int(tile)
    except ValueError:
        await interaction.followup.send(
            f'Unable to process tile "tile": {tile} - Ensure it is a number'
        )
        return
    if tile < 0:
        tile = 1
    settings["teams"][team_name]["current"] = tile
    await interaction.followup.send(f"Updated tile for Team: {team_name} to {tile}")
    update_settings_json(settings)


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="set_previous_tile",
    description=f"Set the previous tile/score manually. Primarily used for candyland version bingo.",
)
async def set_previous_tile(
    interaction: discord.Interaction, team_name: str, tile: int
):
    """
    Sets the previous tile for a given team in the settings.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command invocation.
    - team_name (str): The name of the team.
    - tile (int): The number of the previous tile.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
<<<<<<< HEAD
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.followup.send(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
    elif not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
=======
    if not team_name in team_names:
        await interaction.followup.send(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
        return
    try:
        tile = int(tile)
    except ValueError:
        await interaction.followup.send(
            f'Unable to process prev tile "tile": {tile} - Ensure it is a number'
        )
        return
    if tile < 0:
        tile = None
    settings["teams"][team_name]["prev"] = tile
    await interaction.followup.send(
        f"Updated prev tile for Team: {team_name} to {tile}"
    )
    update_settings_json(settings)


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="configure_team_reroll",
    description=f"Set reroll option for a team. This is used to give or take away rerolls.",
)
async def configure_team_reroll(interaction: discord.Interaction, team_name: str):
    """
    Sets the reroll configuration for a specific team.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's command.
    - team_name (str): The name of the team to set the reroll configuration for.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
<<<<<<< HEAD
    if not interaction.channel.category.name.lower() == "admin":
        await interaction.response.send_message(
            f"Use this command in {mod_channel} and ADMIN section"
        )
        return
    elif not team_name in team_names:
        await interaction.response.send_message(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
=======
    if not team_name in team_names:
        await interaction.response.send_message(f"Team Name: {team_name} is not found in {team_names}\nPlease Try again")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
        return
    await configure_reroll(interaction=interaction, team_name=team_name)


@has_role("Bingo Moderator")
@bot.tree.command(name="update_score", description=f"Refresh the Score")
async def update_score(interaction: discord.Interaction):
    """
    Updates the score and sends a message to the user.
    Uses the stored settings to get the proper channel and message ID, looks it up if it doesn't exist.

    Parameters:
    - interaction: The discord interaction object.

    Returns: None
    """
    settings = load_settings_json()
    await update_server_score_board_channel(interaction=interaction, settings=settings)
    await interaction.response.send_message("Updated!")


@has_role("Bingo Moderator")
@bot.tree.command(
    name="post_tiles", description=f"Post all the tiles to #tile-list channel"
)
async def post_tiles(interaction: discord.Interaction):
    """
    Posts the tiles to the tile-list channel in the guild.
    Uses the settings.json file to get the tiles(settings['items']).

    Parameters:
    - interaction: The discord.Interaction object representing the user interaction.

    Returns: None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    tile_list_ch = discord.utils.get(interaction.guild.channels, name="tile-list")
    item_list = []
    for tile in settings["items"].values():
        if settings["bot_mode"]["current"] == "candyland":
            num = tile["tile_num"]
            name = tile["name"]
            # tile['short_desc']
            desc = tile["desc"]
            item_list.append(f"## {num} - {name}\n{desc}")
        else:
            name = tile["name"]
            # tile['short_desc']
            desc = tile["desc"]
            item_list.append(f"## {name}\n{desc}")
<<<<<<< HEAD
<<<<<<< HEAD

    if len("\n".join(item_list)) > 4096:
        await tile_list_ch.send(
            content="All Tiles\n\n".join(item_list[: len(item_list) // 2])
        )
        await tile_list_ch.send(content="".join(item_list[len(item_list) // 2 :]))
    else:
        await tile_list_ch.send(content="All Tiles\n\n".join(item_list))
    await interaction.followup.send(
        f"Posted {len(settings['items'])} tiles to channel {tile_list_ch.mention}"
    )

=======
    i = 0
    async for m in tile_list_ch.history(oldest_first=True):
        if m.author == bot.user and i == 0:
            await m.edit(content='\n\n'.join(item_list[:len(item_list)//2]))
        if m.author == bot.user and i == 1:
            await m.edit(content='\n\n'.join(item_list[len(item_list)//2:]))
            break
        i += 1
    else:
=======
            
    if len('\n'.join(item_list)) > 4096:
>>>>>>> parent of 2f4c097 (fixed /post_tiles)
        await tile_list_ch.send(content='All Tiles\n\n'.join(item_list[:len(item_list)//2]))
        await tile_list_ch.send(content=''.join(item_list[len(item_list)//2:]))
    else:
        await tile_list_ch.send(content='All Tiles\n\n'.join(item_list))
    await interaction.followup.send(f"Posted {len(settings['items'])} tiles to channel {tile_list_ch.mention}")
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475

async def toggle_roll_choice(interaction: discord.Interaction):
    """
    Toggles the rolling functionality for the bot based on user interaction with bot response.
    User has option to disable rolling or enable rolling by clicking button on bot's response.

    Args:
        interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
        None
    """

    class ToggleRolling(discord.ui.View):
        """
        A custom UI view for toggling the rolling feature.

        This view provides buttons to enable or disable the rolling feature.
        """

        def __init__(self, *, timeout: Optional[float] = 180):
            super().__init__(timeout=timeout)

        @discord.ui.button(label="Disable Rolling", style=discord.ButtonStyle.danger)
        async def disable_rolling(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            """
            Disables the rolling functionality of the bot.

            Parameters:
            - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            - button (discord.ui.Button): The button that triggered the disable_rolling function.

            Returns:
            - None
            """
            settings = load_settings_json()
            settings["running"] = False
            save_settings_json(settings)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Rolling is {'ENABLED' if settings['running'] == True else 'DISABLED'}",
                view=self,
            )

        @discord.ui.button(label="Enable Rolling", style=discord.ButtonStyle.green)
        async def enable_rolling(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            """
            Enables rolling and updates the settings accordingly.

            Args:
                interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
                button (discord.ui.Button): The button that triggered the enable_rolling function.

            Returns:
                None
            """
            settings = load_settings_json()
            settings["running"] = True
            save_settings_json(settings)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Rolling is {'ENABLED' if settings['running'] == True else 'DISABLED'}",
                view=self,
            )

    settings = load_settings_json()
    await interaction.response.send_message(
        f"Rolling is {'ENABLED' if settings['running'] == True else 'DISABLED'}",
        view=ToggleRolling(),
    )


@has_role("Bingo Moderator")
@bot.tree.command(
    name="toggle_rolling",
    description=f"Enable or Disable the ability to roll dice. If enabled, it disables. Run again to enable.",
)
async def toggle_rolling(interaction: discord.Interaction):
    """
    Toggles the rolling of a choice for the given interaction.

    Parameters:
    - interaction: The discord.Interaction object representing the user interaction.

    Returns:
    - None
    """
    await toggle_roll_choice(interaction)


@has_role("Bingo Moderator")
@bot.tree.command(
    name="check_roll_enabled",
    description=f"Checks if the rolling is Disabled or Enabled. Does not update/change anything.",
)
async def check_roll_enabled(interaction: discord.Interaction):
    """
    Checks if rolling is enabled and sends a response indicating the current status.

    Parameters:
    interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    await interaction.followup.send(
        f"Rolling is currently: {'ENABLED' if settings['running'] == True else 'DISABLED'}"
    )


@has_role("Bingo Moderator")
@bot.tree.command(
    name="tile_completed", description=f"Marks a channel's tile as completed(Normal)"
)
async def tile_completed(interaction: discord.Interaction):
    """
    Updates the tile completion status and score in the settings and scoreboard channel.
    NOT IMPLEMENTED YET

    Parameters:
    interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    # Check tile is completed.
    # Update settings or however this is tracked.
    # Update score in settings
    # Update score in scoreboard channel
    await interaction.followup.send(
        f"Tile is: {'COMPLETED' if settings['running'] == True else 'CHANGED TO INCOMPLETE'}\nScore will be updated accordingly"
    )


@has_role("Bingo Moderator")
@bot.tree.command(
    name="version", description=f"Change the Bot's Bingo Version or view current."
)
async def version(
    interaction: discord.Interaction,
    bingo_version: bool = False,
    candyland: bool = False,
):
    """
    Updates the bot version based on the provided parameters and sends a response with the updated version.

    Parameters:
    - interaction: The Discord interaction object.
    - bingo_version: A boolean indicating whether to set the bot version to "normal" (True) or not (False).
    - candyland: A boolean indicating whether to set the bot version to "candyland" (True) or not (False).
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    # TODO Update this to change the settings
    if bingo_version:
        settings["bot_mode"]["current"] = "normal"
    elif candyland:
        settings["bot_mode"]["current"] = "candyland"
    save_settings_json(settings)

    await interaction.followup.send(
        f"Bingo Bot Version is: '{settings['bot_mode']['current']}'"
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="mark_tile_completed",
    description=f"Mark a tile as completed on the bingo board, Column A-E. Row 1-5. 'A1' for example.",
)
async def mark_tile_completed(
    interaction: discord.Interaction, team_name: str, location: str
):
    """
    Marks a tile as completed for a specific team and updates the Bingo Card.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team.
    - location (str): The location of the tile in the Bingo Card.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    row, col = await parse_table_location(location)
    if row == 0 or col == 0:
        update = False
    else:
        update = True
        settings["teams"][team_name]["tiles_completed"].append([row, col])
    update_settings_json(settings)
    await post_or_update_bingo_card(
        interaction, settings, team_name, update=update, row=row, column=col
    )
    await interaction.followup.send(
        f"Team: {team_name}'s tile has been marked as completed and updated in the Bingo Card Channel"
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="post_bingo_card",
    description=f"Post the saved bingo card to '#bingo-card' channel.",
)
async def post_bingo_card(
    interaction: discord.Interaction,
    for_all_teams: bool = False,
    team_name: Optional[str] = None,
):
    """
    Posts a bingo card image in the corresponding team's Bingo Card Channel.

    Parameters:
    - interaction: The Discord interaction object.
    - for_all_teams: A boolean indicating whether to post the bingo card for all teams or not. Default is False.
    - team_name: The name of the team for which to post the bingo card. Default is None.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    update = False
    i = 0
    if for_all_teams or team_name == None:
        for i in range(len(team_names)):
            if i >= settings["total_teams"]:
                continue
            else:
                await post_or_update_bingo_card(
                    interaction, settings, team_names[i], update=update, row=0, column=0
                )
    else:
        await post_or_update_bingo_card(
            interaction, settings, team_name, update=update, row=0, column=0
        )
    await interaction.followup.send(
        f"Posted Bingo Card image in {team_name if team_name else ', '.join([team_names[x] for x in range(settings['total_teams'])])}'s Bingo Card Channel"
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(
    name="default_bingo_card",
    description=f"Post the default bingo card to '#bingo-card' channel. From /upload_board_image.",
)
async def default_bingo_card(interaction: discord.Interaction, team_name: str):
    """
    Posts the default bingo card image in the specified team's Bingo Card Channel.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    update = False
    settings["teams"][team_name]["image"] = os.path.join(
        IMAGE_PATH, "bingo_card_image.png"
    )
    update_settings_json(settings)
    await post_or_update_bingo_card(
        interaction, settings, team_name, update=update, row=0, column=0
    )
    await interaction.followup.send(
        f"Posted Bingo Card image in {team_name}'s Bingo Card Channel"
    )


@has_role("Bingo Moderator")
@bot.tree.command(
    name="upload_board_image",
    description=f"Attach and upload image as the default Bingo Card Image. Overwrites all teams existing images.",
)
async def upload_board_image(
    interaction: discord.Interaction, file: discord.Attachment
):
    """
    Uploads a board image and updates the default Bingo Card Image for all teams.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - file (discord.Attachment): The image file to be uploaded.

    Returns:
    None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    await interaction.response.defer(thinking=True)
    if not file:
        await interaction.followup.send(
            f"Please attach an image to set as the default Bingo Card Image"
        )
        return
    else:
        # download attachment
        bingo_image_path = os.path.join(IMAGE_PATH, "bingo_card_image.png")
        with open(bingo_image_path, "wb") as f:
            await file.save(f)
        # update all settings['teams'][team_name]['image']
        for team_name in team_names:
            settings["teams"][team_name]["image"] = bingo_image_path
        update_settings_json(settings)
        await interaction.followup.send(f"Default Bingo Card Image has been updated")
        update_settings_json(settings)


@has_role("Bingo Moderator")
@bot.tree.command(
    name="set_image_bounds",
    description=f"Set the bounds for the bingo card to be auto marked as completed by bot.",
)
async def set_image_bounds(
    interaction: discord.Interaction,
    x: int,
    y: int,
    x_left_offset: int,
    x_right_offset: int,
    y_top_offset: int,
    y_bottom_offset: int,
    gutter: int,
):
    """
    Sets the image bounds for each team in the settings.

    Parameters:
    - interaction: The discord interaction object.
    - x: The x-coordinate of the image.
    - y: The y-coordinate of the image.
    - x_left_offset: The left offset of the image.
    - x_right_offset: The right offset of the image.
    - y_top_offset: The top offset of the image.
    - y_bottom_offset: The bottom offset of the image.
    - gutter: The gutter size of the image.

    Returns:
    - None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    await interaction.response.defer(thinking=True)
    if (
        x_left_offset == ""
        or y_top_offset == ""
        or x_right_offset == ""
        or y_bottom_offset == ""
        or x == ""
        or y == ""
        or gutter == ""
    ):
        await interaction.followup.send(f"Please provide all the required values")
        return
    else:
        # update all settings['teams'][team_name]['image']
        for team_name in team_names:
            settings["teams"][team_name]["image_bounds"] = {
                "x_offset": x_left_offset,
                "y_offset": y_top_offset,
                "x_right_offset": x_right_offset,
                "y_bottom_offset": y_bottom_offset,
                "x": x,
                "y": y,
                "gutter": gutter,
            }
        update_settings_json(settings)
        await interaction.followup.send(f"Image bounds for each team have been updated")
        update_settings_json(settings)


@has_role("Bingo Moderator")
@bot.tree.command(
    name="sync", description=f"Sync the command tree with the current settings."
)
async def sync(interaction: discord.Interaction):
    """
    Synchronizes the command tree with the bot.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's command interaction.

    Returns:
    None
    """
    print("sync command")
    await interaction.response.defer(thinking=True)
    await bot.tree.sync()
    await interaction.followup.send("Command tree synced.")


@has_role("Bingo Moderator")
@bot.tree.command(
    name="close_server",
    description=f"Remove all roles from non-admin or bingo moderator roles.",
)
async def close_server(interaction: discord.Interaction):
    """
    Closes the server by deferring the interaction response, processing all spectators, and sending a follow-up message.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    - None
    """
    await interaction.response.defer(thinking=True)
    spectator_role = discord.utils.get(interaction.guild.roles, name="spectator")
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    roles.append(spectator_role)
    # roles.append(rules_accepted_role)
    await process_all_spectators(interaction, roles, spectator_role, unassign=True)
    start_here_channel = discord.utils.get(
        interaction.guild.channels, name="start-here"
    )
    rules_accepted_role = discord.utils.get(
        interaction.guild.roles, name="Rules Accepted"
    )
    await start_here_channel.set_permissions(rules_accepted_role, view_channel=False)
    await interaction.followup.send("Server has been closed.")


@has_role("Bingo Moderator")
@bot.tree.command(
    name="update_total_teams", description=f"Update the number of active teams."
)
async def update_total_teams(interaction: discord.Interaction, total_teams: int):
    """
    Updates the number of active teams in the settings and sends a response message.

    Parameters:
    interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    total_teams (int): The new number of active teams.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    if total_teams < 1:
        await interaction.followup.send(
            f"Number of active teams must be greater than 0"
        )
        return
    settings["total_teams"] = total_teams
    update_settings_json(settings)
    await interaction.followup.send(
        f"Number of active teams has been updated to {total_teams}"
    )


@has_role("Bingo Moderator")
@bot.tree.command(
    name="reset_bingo_settings", description=f"Reset persistent bingo settings."
)
async def reset_bingo_settings(interaction: discord.Interaction):
    """
    Resets the bingo settings for all teams.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    - None
    """

    class ConfirmReset(discord.ui.View):
        def __init__(self, *, timeout: Optional[float] = 180):
            super().__init__(timeout=timeout)

        @discord.ui.button(label="Don't Reset", style=discord.ButtonStyle.danger)
        async def abort_reset(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Aborted Reseting of Settings.\nNothing was modified",
                view=self,
            )

        @discord.ui.button(label="Enable Rolling", style=discord.ButtonStyle.green)
        async def reset_settings(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            settings = load_settings_json()
            old_settings = load_settings_json()
            team_names = [x for x in settings["teams"].keys()]
            # set total_teams to 7
            settings["total_teams"] = 7
            for team_name in team_names:
                # set completed tiles to empty list
                settings["teams"][team_name]["tiles_completed"] = []
                # set current tile to 0
                settings["teams"][team_name]["current"] = 0
                # set prev tile to 0
                settings["teams"][team_name]["prev"] = 0
                # set rerolls to 0
                settings["teams"][team_name]["reroll"] = 0
                # set roll_history to empty list
                settings["teams"][team_name]["roll_history"] = []
                # set image to default
                settings["teams"][team_name]["image"] = os.path.join(
                    IMAGE_PATH, "bingo_card_image.png"
                )
                # set image bounds to default
                settings["teams"][team_name]["image_bounds"] = {
                    "x_offset": 0,
                    "y_offset": 0,
                    "x_right_offset": 0,
                    "y_bottom_offset": 0,
                    "x": 0,
                    "y": 0,
                    "gutter": 0,
                }
                # set tiles_completed to empty list
<<<<<<< HEAD
                settings["teams"][team_name]["tiles_completed"] = []

=======
                settings['teams'][team_name]['tiles_completed'] = []
            # delete images in IMAGE_PATH that arent default_bingo_card_image.png
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
            update_settings_json(settings)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Reset Bingo Settings.\nPrevious Settings:\n{json.dumps(old_settings, indent=4)}",
                view=self,
            )

<<<<<<< HEAD
    settings = load_settings_json()
    await interaction.response.send_message(
        f"RESET ALL BINGO SETTINGS is ?????????????", view=ConfirmReset()
    )


# create a command that posts image to channel "bingo-card" at 8pm EST every day until disabled. command should accept 'date_started', 'date_ended', 'time', 'message', and list of 'image_urls'
@has_role("Bingo Moderator")
@bot.slash_command(description="Post a daily bingo card to the channel 'bingo-card'.")
async def daily_board_post(
    date_started: datetime.date,
    date_ended: datetime.date,
    time: datetime.time,
    message: str,
    image_urls: List[str],
    interaction: discord.Interaction,
    disable: bool = False,
):
    # create a new daily board post task that posts the image to the channel every day at 8pm EST
    # and sends a message to the channel with the date, time, and message
    # and a list of image urls that can be used to create the bingo card
    # task should be disabled after 1 day of not running
    if disable:
        # cancel task
        await interaction.response.edit_message(
            content="Daily Bingo Board Posting Disabled.", view=None
        )
        return

    # update each channels Bingo Board to each settings['teams'][TEAM_NAME][IMAGE]
    # also update the tiles_completed to be an empty list


if __name__ == "__main__":
    # import inspect
    # import sys
    # # get all docstrings and generate documentation for discord.py
    # with open('discord_commands.txt', 'w') as f:
    #     for name, obj in inspect.getmembers(sys.modules[__name__]):
    #         if inspect.isfunction(obj):
    #             if obj.__doc__:
    #                 f.write(f"{obj.__name__}: {obj.__doc__}\n")
    print("About to log in with bot")
=======
async def process_team_assignment_updates(interaction: discord.Interaction):
    settings = load_settings_json()
    total_teams = settings['total_teams']
    all_roles = []
    for role in interaction.guild.roles:
        if role.name in ROLES:
            all_roles.append(role)
    print(f"{all_roles = }")
    
    team_assignment_channel = discord.utils.get(interaction.guild.channels, name="team-assignments")

    if not team_assignment_channel:
        await interaction.followup.send('No Team Assignment Channel found')
        return
    else:
        async for m in team_assignment_channel.history(oldest_first=True):
            if m.author == bot.user:
                content = generate_team_assignment_text(all_roles, total_teams)
                await m.edit(content=content)
                break
        else:
            content = generate_team_assignment_text(all_roles, total_teams)
            await team_assignment_channel.send(content=content, silent=True)
    await interaction.followup.send('Updated Team Assignment Channel')

@has_role("Bingo Moderator")
@bot.tree.command(name="update_team_assignment", description=f"Update #team-assignment channel with proper roles.")
async def update_team_assignment(interaction: discord.Interaction):
    """
    Updates the team assignment channel to display the members currently assigned to the role.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    - None
    """
    await interaction.response.defer(thinking=True)
    await process_team_assignment_updates(interaction)

if __name__ == '__main__':
    print('About to log in with bot')
>>>>>>> 2f4c097f2b640fe6718b9d3ee0df72e1fda2c475
    bot.run(config.DISCORD_BOT_TOKEN)

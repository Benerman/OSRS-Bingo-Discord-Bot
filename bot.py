import discord
from discord import app_commands
from discord.app_commands.checks import has_role
from discord.ext import commands, tasks
import requests
import json
import re
import random
import os
import datetime
import math
import config
import asyncio
from discord import Role
from typing import List, Optional
from PIL import Image, ImageDraw

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

DICE_SIDES = 6

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

IMAGE_PATH = os.path.join(os.getcwd(), "images")
IMAGE_TEMPLATE_PATH = os.path.join(os.getcwd(), "template_images")

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

CNL_DEFAULT_CHANNELS = [
    "chat",
    "bingo-card",
    "dice-roll",
    "photo-dump",
    "voice-chat",
]


CNL_SHORTCUTS = (
    # Score > New Score
    # Ladders
    (1, 38),
    (4, 14),
    (9, 31),
    (21, 42),
    (28, 84),
    (51, 67),
    (71, 91),
    (80, 100),
    # Chutes
    (98, 79),
    (95, 75),
    (93, 73),
    (87, 24),
    (64, 60),
    (62, 19),
    (54, 34),
    (17, 7)
)

IGNORED_CATEGORIES = [
    "welcome",
    "admin",
    "bot",
    "archived",
    "general"
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

dice_emoji = ":game_die:"
green_square = ":green_square:"

# ======================================= Utility Commands ====================================================


def roll_dice(num=DICE_SIDES):
    """
    Roll a dice with the specified number of sides.

    Args:
        num (int): Number of sides on the dice. Default is 6.

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

def chunk_text(text, chunk_size=3996, split_line=False):
    """Splits text into chunks of a specified size."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

def chunk_item_list_text(text_list, chunk_size=3896):
    output = []
    while True:
        chunk = ""
        for item in text_list:
            if len(f"{chunk}\n{item}\n") > chunk_size:
                output.append(chunk)
                chunk = f"{item}\n"
            else:
                chunk = f"{chunk}{item}\n"
        break
    output.append(chunk)
    return output

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

    desc = settings["items"][str(tile_num)].get("short_desc")
    if not desc:
        desc = settings["items"][str(tile_num)]["desc"]
        return f"{tile_num} - {name}"
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
        if contents["bot_mode"]["current"] == "candyland" or contents["bot_mode"]["current"] == "chutes and ladders":
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


def load_sheet(SAMPLE_SPREADSHEET_ID, RANGE="A1:Z1000"):
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
            print("updated token")
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
        title=f"{itm['tile_num']} - {itm['name']}{f' - {itm['short_desc']}' if itm['short_desc'] else ''}",
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
    image_bounds = settings["image_bounds"]
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
        # print(i, role.name)
        if i >= total_teams:
            continue
        formatted_text = f"# {role.name}:\n{' '.join([f'<@{str(r.id)}>' for r in role.members])}\n"
        content.append(formatted_text)
    content.sort()
    return '\n'.join(content)

def calculate_shortcut(score):
    idx = [x[1] for x in CNL_SHORTCUTS if x[0] == score]
    if idx:
        return idx[0]

def calculate_row_and_column(score):
    # breakpoint()
    row = math.floor((score-1) / 10)
    actual_row = 10 - row
    column = score % 10
    if column == 0:
        column = 10
    row_even = True if row % 2 == 1 else False
    if row_even:
        actual_column = 11 - column
    else:
        actual_column = column
    return actual_row, actual_column

    
def calculate_location_x_and_y(score):
    settings = load_settings_json()
    board_bounds = settings['board_bounds']
    tile_size = board_bounds['tile_size']
    row, column = calculate_row_and_column(score)
    if column > 1:
        column_multiplier = column - 1
    else:
        column_multiplier = 0
    width_gutter = column_multiplier * board_bounds['gutter']
    width_tile_spacing = column_multiplier * tile_size
    width = board_bounds['x_offset'] + width_gutter + width_tile_spacing
    row_multiplier = 0
    if row > 1:
        row_multiplier = row - 1
    else:
        row_multiplier = 0
    height_gutter = row_multiplier * board_bounds['gutter']
    height_tile_spacing = row_multiplier * tile_size
    height = board_bounds['y_offset'] + height_gutter + height_tile_spacing
    return width, height


async def mark_team_icons_on_board(interaction: discord.Interaction) -> str:
    settings = load_settings_json()
    if settings['bot_mode']['current'] != "chutes and ladders":
        await interaction.followup.send("Error: Bot mode is set to something other than 'chutes and ladders'")
        return 
    image_path_src = os.path.abspath(settings['board_template'])
    board_bounds = settings["board_bounds"]
    img_board = Image.open(image_path_src)
    tile_count = board_bounds['tile_count']
    tile_size = board_bounds['tile_size']
    x_offset = board_bounds["x_offset"] if board_bounds["x_offset"] else 0
    y_offset = board_bounds["y_offset"] if board_bounds["y_offset"] else 0
    x_right_offset = (
        board_bounds["x_right_offset"] if board_bounds["x_right_offset"] else 0
    )
    y_bottom_offset = (
        board_bounds["y_bottom_offset"] if board_bounds["y_bottom_offset"] else 0
    )
    gutter = board_bounds["gutter"] if board_bounds["gutter"] else 0
    if board_bounds["x"] == 0 and board_bounds["y"] == 0:
        width, height = img_board.size
        width = width - (x_offset + x_right_offset + (4 * gutter))
        height = height - (y_offset + y_bottom_offset + (4 * gutter))
    else:
        width = board_bounds["x"]
        height = board_bounds["y"]
    # add team_icon starting at highest team number to 1
    icon_path = os.path.dirname(os.path.abspath(settings['board_template']))
    icon_team_files = [x for x in os.listdir(icon_path) if "CNL_Team" in x]
    icon_team_files.sort()
    icon_team_files.reverse()
    icon_team_files = [os.path.join(icon_path, x) for x in icon_team_files]
    team_names = [x for x in settings['teams'].keys()]
    team_names.reverse()
    team_scores = [(x,settings['teams'][x]['current']) for x in settings['teams']]
    team_scores.reverse()
    all_scores = [x[1] for x in team_scores]
    dupe_scores_processed = 0
    for i in range(len(team_names)):
        team_name = team_names[i]
        score = team_scores[i][1]
        if score == 0:
            # do not draw on board
            # print(f'skipping {team_name} due to score: 0')
            continue
        # check if score exists for other teams
        shared_tile = False if all_scores.count(score) == 1 else True
        number_of_tiles = all_scores.count(score)
        # open image
        img_team = Image.open(icon_team_files[i])
        team_x, team_y = img_team.size
        img_team = img_team.resize((math.floor(team_x * 0.75), math.floor(team_y * 0.75)))
        x, y = calculate_location_x_and_y(score)
        offset_width = tile_size - img_team.size[0]
        if shared_tile:
            offset_multiplier = number_of_tiles - dupe_scores_processed - 1
            new_x = x + (board_bounds['team_icon_x_offset'] + offset_multiplier * (math.floor(offset_width / number_of_tiles)))
            dupe_scores_processed += 1
        else:
            new_x = x + board_bounds['team_icon_x_offset']
        new_y = y + board_bounds['team_icon_y_offset']
        img_board.paste(img_team, (new_x, new_y), img_team)

    if all_scores.count(100) >= 1:
        # winners!
        confetti_img = Image.open(os.path.join(os.path.dirname(image_path_src), "confetti.png"))
        img_board.paste(confetti_img, (0,0), confetti_img)
    img_name = f"CNL-{datetime.datetime.now()}.png"
    # check if "generated" folder exists
    if not os.path.exists(os.path.join(os.path.dirname(image_path_src), "generated")):
        os.mkdir(os.path.join(os.path.dirname(image_path_src), "generated"))
    new_image_path = os.path.join(os.path.dirname(image_path_src), "generated", img_name)
    img_board.save(new_image_path)
    settings["board_latest"] = new_image_path
    update_settings_json(settings)
    return new_image_path


async def purge_images(type: str) -> str:
    settings = load_settings_json()
    if type == "chutes and ladders":
        folder_path = os.path.join(os.path.dirname(os.path.abspath(settings['board_template'])), "generated")
        old_image_files = [x for x in os.listdir(folder_path) if "CNL-" in x]
        for file in old_image_files:
            os.remove(os.path.join(folder_path, file))
        return f"Removed {len(old_image_files)} image files."
    else:
        return f"Bot mode is not supported. Current Mode: {settings['bot_mode']['current']}"

async def send_or_update_tiles_channel(tile_list_ch, settings):
    item_list = []
    for tile in settings["items"].values():
        if settings["bot_mode"]["current"] == "candyland" or settings["bot_mode"]["current"] == "chutes and ladders":
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
    edited = False
    chunked_list = chunk_item_list_text(item_list)
    i = 0
    async for m in tile_list_ch.history(oldest_first=True):
        if m.author == bot.user and i == 0:
            edited = True
            embed = discord.Embed(description=f'# All Tiles\n\n{chunked_list[i]}')
            await m.edit(embed=embed)
        elif m.author == bot.user:
            embed = discord.Embed(description=f"{chunked_list[i]}")
            await m.edit(embed=embed)
        i += 1
    if edited:
        if len(chunked_list) > i:
            # send remaining messages needed
            for x in range(i, len(chunked_list)):
                embed = discord.Embed(description=f"{chunked_list[x]}")
                await tile_list_ch.send(embed=embed)
    else:
        for i in range(len(chunked_list)):
            if i == 0:
                embed = discord.Embed(description=f'# All Tiles\n\n{chunked_list[i]}')
                await tile_list_ch.send(embed=embed)
            else:
                embed = discord.Embed(description=f"{chunked_list[i]}")
                await tile_list_ch.send(embed=embed)

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
    elif settings['bot_mode']['current'] == "chutes and ladders":
        return CNL_DEFAULT_CHANNELS
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
                    # print(settings["teams"][team_name]["image"])
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
            # print(msg)
            if msg.author == bot.user:
                msg_id = msg.id
                msg_webhook = msg.webhook_id
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
    content_text = []
    for i in range(len(teams_names)):
        if i >= total_teams:
            continue
        if settings["bot_mode"]["current"] == "candyland":
            row = f"{teams_names[i]}: {teams_scores[i]} - Rerolls remain: {teams_rerolls[i]}"
            teams_rerolls = [x["reroll"] for x in settings["teams"].values()]
        else:
            row = f"{teams_names[i]}: {teams_scores[i]}"
        content_text.append(row)
    score_text = "\n".join(content_text)
    # process things for Chutes and ladders
    settings["posts"]["score-board"]["id"] = msg_id
    settings["posts"]["score-board"]["content"] = score_text
    update_settings_json(settings)
    
    if settings["bot_mode"]["current"] == "chutes and ladders":
        img_path = await mark_team_icons_on_board(interaction=interaction)
        if img_path:
            img = discord.File(img_path)
            await message.edit(content=score_text, attachments=[img])
    else:
        await message.edit(content=score_text, attachments=[])



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
    await interaction.followup.send(f'Starting the update for Role "spectator" {"added to" if not unassign else "purged from"}\nThis will take a while(1-5 mins). Standby for update...')
    for r in guild_roles:
        if r in roles:
            for m in r.members:
                if discord.RateLimited:
                    print("Rate Limited, pausing 5s")
                    await asyncio.sleep(5)
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

async def change_team_names_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """
    Autocompletes team names based on the current input.
    For Changing Team Name, it lists all categoires for bingo discord too

    Args:
        interaction (discord.Interaction): The interaction object.
        current (str): The current input string.

    Returns:
        List[app_commands.Choice[str]]: A list of app_commands.Choice objects representing the autocompleted team names.
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    all_categories = [c.name for c in interaction.guild.categories if not c.name.lower() in IGNORED_CATEGORIES]
    all_options = team_names + [x for x in all_categories if x not in team_names]
    return [
        app_commands.Choice(name=team_name, value=team_name)
        for team_name in all_options
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


@bot.tree.command(name="roll",
    description=f"Roll a d{DICE_SIDES} in your teams {roll_channel} channel. Creates new channel for the newly rolled tile.")
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
    score_altered = None
    # check which bot mode
    if settings['bot_mode']['current'] == "chutes and ladders":
        # check for shortcuts
        current = settings["teams"][team_name]["current"]
        score = calculate_shortcut(current)
        if score:
            if score > current:
                score_altered = "ladder-"
            else:
                score_altered = "rats-"
            settings["teams"][team_name]["current"] = score

    # Check win condition 

    
    total_tiles = len(settings["items"])
    if settings["teams"][team_name]["prev"] == total_tiles:
        # Checks if last prev tile was the last tile of the bingo
        # await message.add_reaction("\n{TADA}")
        await interaction.followup.send(
            f'# Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention}\nyou have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}'
        )
        return
    elif settings["teams"][team_name]["current"] > total_tiles:
        if settings['bot_mode']['current'] == 'candyland':
            # This makes the last tile mandatory
            settings["teams"][team_name]["current"] = total_tiles
            # roll_info = settings['items'][str(settings['teams'][team_name]['current'])]
            # print(f"{roll_info = }")
        else:
            # bounce back CNL Tile 98 + 6 > 98 + 2 = 100 -4 = 96 > Tile 96
            score_altered = "bounce back-"
            new_score = 2 * settings['board_bounds']['tile_count'] - settings["teams"][team_name]["current"]
            settings["teams"][team_name]["current"] = new_score

    update_settings_json(settings)

    name = create_discord_friendly_name(
        f"{settings['teams'][team_name]['current']}-{score_altered if score_altered else ''}{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
    )
    await interaction.followup.send(
        f"## {dice_emoji} Team: {team_name} rolled:  {dice_emoji}  __**{roll}**__\
        \n## Congrats, your new tile is:  {green_square}  __**{settings['teams'][team_name]['current']}**__\
        \nYour previous tile was: {settings['teams'][team_name]['prev']}\
        \n# {name.replace('-', ' ').title()}"
        # f"Rolling Dice:\n# {roll}\nfor team: {team_name}\nCongrats, your new tile is:\n# {settings['teams'][team_name]['current']} and from previous tile was:\n# {settings['teams'][team_name]['prev']}\n{title}"
    )
    ch = await interaction.channel.clone(name=name)
    embed = create_tile_embed(
        tiles=settings["items"],
        tile_number=str(settings["teams"][team_name]["current"]),
    )
    await ch.send(embed=embed)

    # Check if Sabotage Tile
    if sabotage := settings["items"][str(settings["teams"][team_name]["current"])]["sabotage"] and settings['bot_mode'] == 'candyland':
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
        name = create_discord_friendly_name(
            f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
        )
        await interaction.channel.send(
            f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {team_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{name}"
        )

        ch = await interaction.channel.clone(name=name)
        embed = create_tile_embed(
            tiles=settings["items"],
            tile_number=str(settings["teams"][team_name]["current"]),
        )
        await ch.send(embed=embed)

    if settings['bot_mode']['current'] == 'candyland':
        # Add updating the TEAMS bingo card channel
        await update_team_bingo_card_channel(interaction, team_name, roll, settings)

    # Add updating the Server's Bingo card Channel
    await update_server_score_board_channel(interaction, settings)


@bot.tree.command(name="reroll",
    description=f"Reroll a d{DICE_SIDES} in your teams {roll_channel} channel, nulling the last roll and rolls from the prev tile.",)
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
        if settings["running"] == False or settings['rerolling'] == False:
            await interaction.followup.send(
                "Rolling/Rerolling is not enabled, either wait till Start time or message @ Bingo Moderator if receiving this message in error."
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
            if sabotage := settings["items"][str(settings["teams"][team_name]["current"])]["sabotage"]:
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
@bot.tree.command(name="upload_tiles",
    description=f"Sets the Bingo Tiles from a Public Google Sheet doc, processes, and formats them.")
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
    # if not interaction.channel.category.name.lower() == "admin":
    #     await interaction.followup.send(
    #         f"Use this command in {mod_channel} and ADMIN section"
    #     )
    #     return
    # await interaction.response.edit_message(suppress=True)
    settings = load_settings_json()
    try:
        processed, settings = update_settings_json(
            settings,
            url=sheet_link,
            process_sheet=process_sheet
        )
        await interaction.followup.send(f"{processed}")
    except RefreshError:
        os.remove('token.json')
        await interaction.followup.send("Error processing or accessing google sheet. Check link sharing perms.")


@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role("Bingo Moderator")
@bot.tree.command(name="clear_team_role",
    description=f"Clear Team <#> Role from all players assigned")
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
@bot.tree.command(name="spectators",
    description=f"Assign Spectator Role and clear existing roles to Discord Members")
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
@bot.tree.command(name="add_team_role",
    description=f"Assign Team <#> Role to Discord Members")
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
    await process_team_assignment_updates(interaction)
    await interaction.followup.send(f'Role "Team {team_number}" added to {len(members)} members')


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
@bot.tree.command(name="delete_team",
    description=f"Delete all channels for a team and the team category.")
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
            # if not interaction.channel.category.name.lower() == "admin":
            #     await interaction.response.send_message(
            #         f"Use this command in {mod_channel} and ADMIN section"
            #     )
            #     return
            if not self.team_name in team_names:
                await interaction.message.edit(
                    embed=discord.Embed(
                        description=f"Team Name: {self.team_name} is not found in {team_names}\nPlease Try again"
                    ),
                    view=self,
                )
            if not self.team_name in team_names:
                await interaction.message.edit(
                    embed=discord.Embed(
                        description=f"Team Name: {self.team_name} is not found in {team_names}\nPlease Try again"
                    ),
                    view=self,
                )
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
            # print([c.name for c in cats])
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
@app_commands.autocomplete(team_name=change_team_names_autocomplete)
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
    # team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    # if not interaction.channel.category.name.lower() == "admin":
    #     await interaction.followup.send(
    #         f"Use this command in {mod_channel} and ADMIN section"
    #     )
    #     return
    if not new_team_name:
        await interaction.followup.send(f'No "new_team_name" provided, Please try again')
        return
    team_cat = discord.utils.get(interaction.guild.categories, name=team_name)
    if not team_cat:
        await interaction.followup.send(f'No Category found for "{team_name}"')
        return
    elif not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
        return
    # Update Settings
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
@bot.tree.command(name="update_tiles_channels", description=f"Updates channel tiles DESCRIPTION AND Initial Message for a team. Doesn't update channel name.")
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
    # tile_list_ch = discord.utils.get(interaction.guild.channels, name="tile-list")

    # await send_or_update_tiles_channel(tile_list_ch, settings)

    team_names = [x for x in settings['teams'].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    not_implemented = False
    # not_implemented = True
    if not_implemented:
        await interaction.followup.send(f"command not implemented yet.")

        """========================== NOT IMPLEMENTED ============================="""

        return
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
    await interaction.response.defer(thinking=True)
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
        return
    cats = interaction.guild.categories
    # print([c.name for c in cats])
    channels = await get_default_channels(interaction)
    updated_num = 0
    for cat in cats:
        if cat.name.lower() == team_name.lower():
            # print('team cat found', cat.name)
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


async def create_discord_text_channel(
    interaction: discord.Interaction,
    channel_name: str,
    description: str, 
    cat: discord.CategoryChannel, 
    overwrites: discord.PermissionOverwrite
):
    chan = await interaction.guild.create_text_channel(
        name=channel_name,
        topic=description,
        category=cat,
        overwrites=overwrites,
    )
    if "dice-roll" in channel_name:
        # find carl-bot and remove from dice roll
        # carl_bot_member = discord.utils.get(interaction.guild.members, id="235148962103951360")
        # print(carl_bot_member.name)
        # await chan.set_permissions(carl_bot_member, read_messages=False, manage_messages=False)
        pass
    if description:
        await chan.send(f"{description}")
    if "photo-dump" in channel_name or "drop-spam" in channel_name:
        webhook = await chan.create_webhook(name=channel_name)
        message_1 = await chan.send(
            f"Here are instructions for adding Discord Rare Drop Notification to Runelite\
                \n\nDownload the Plugin from Plugin Hub\nCopy this Webhook URL to this channel\
                    into the Plugin(Accessed via the settings)"
        )
        message_2 = await chan.send(f"```{webhook.url}```")
        await message_1.pin()
        await message_2.pin()
        
        #TODO maybe implement the whitelisting of the items?
        # if settings["bot_mode"]["current"] == "candyland":
        #     await chan.send(
        #         f"Copy in this Tile List to ensure that ALL potential items are captured"
        #     )
        #     list_of_item_names = [
        #         x["item_names"] for x in settings["items"].values()
        #     ]
        #     list_of_item_names = [
        #         x.replace("*", "\*") for x in list_of_item_names
        #     ]
        #     embed = discord.Embed(
        #         description=f"{''.join([x.lower() for x in filter(None, list_of_item_names)])}"
        #     )
        #     await chan.send(embed=embed)


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(name="create_team_channels",
    description=f"Update the bingo tiles for a team. Useful for post start updates.")
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
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
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
        if settings["bot_mode"]["current"] == "candyland" or settings["bot_mode"]["current"] == "chutes and ladders":
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
            #TODO update this to be relevant, doesnt work for candyland and CNL
            description = ""
            await create_discord_text_channel(interaction, channel_name, description, cat, overwrites)
        
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
    # if not interaction.channel.category.name.lower() == "admin":
    #     await interaction.followup.send(
    #         f"Use this command in {mod_channel} and ADMIN section"
    #     )
    #     return
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
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
@bot.tree.command(name="set_previous_tile",
    description=f"Set the previous tile/score manually. Primarily used for candyland version bingo.")
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
    # if not interaction.channel.category.name.lower() == "admin":
    #     await interaction.followup.send(
    #         f"Use this command in {mod_channel} and ADMIN section"
    #     )
    #     return
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
    if not team_name in team_names:
        await interaction.followup.send(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
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
@bot.tree.command(name="configure_team_reroll",
    description=f"Set reroll option for a team. This is used to give or take away rerolls.")
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
    # if not interaction.channel.category.name.lower() == "admin":
    #     await interaction.response.send_message(
    #         f"Use this command in {mod_channel} and ADMIN section"
    #     )
    #     return
    # elif not team_name in team_names:
    #     await interaction.response.send_message(
    #         f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
    #     )
    if not team_name in team_names:
        await interaction.response.send_message(
            f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
        )
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
@bot.tree.command(name="post_tiles", description=f"Post all the tiles to #tile-list channel")
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

    await send_or_update_tiles_channel(tile_list_ch, settings)
    await interaction.followup.send(f"Posted {len(settings['items'])} tiles to channel {tile_list_ch.mention}")

async def toggle_roll_choice(interaction: discord.Interaction, reroll=False):
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

        @discord.ui.button(label="Disable Rerolling", style=discord.ButtonStyle.danger)
        async def disable_rerolling(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            """
            Disables the rerolling functionality of the bot.

            Parameters:
            - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
            - button (discord.ui.Button): The button that triggered the disable_rolling function.

            Returns:
            - None
            """
            settings = load_settings_json()
            settings["rerolling"] = False
            save_settings_json(settings)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Rerolling is {'ENABLED' if settings['rerolling'] == True else 'DISABLED'}",
                view=self,
            )

        @discord.ui.button(label="Enable Rerolling", style=discord.ButtonStyle.green)
        async def enable_rerolling(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            """
            Enables rerolling and updates the settings accordingly.

            Args:
                interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
                button (discord.ui.Button): The button that triggered the enable_rolling function.

            Returns:
                None
            """
            settings = load_settings_json()
            settings["rerolling"] = True
            save_settings_json(settings)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Rerolling is {'ENABLED' if settings['rerolling'] == True else 'DISABLED'}",
                view=self,
            )

    settings = load_settings_json()
    await interaction.response.send_message(
        f"Rolling is {'ENABLED' if settings['running'] == True else 'DISABLED'}\n\
            Rerolling is {'ENABLED' if settings['rerolling'] == True else 'DISABLED'}",
        view=ToggleRolling(),
    )


@has_role("Bingo Moderator")
@bot.tree.command(name="toggle_rolling",
    description=f"Enable or Disable the ability to roll and reroll dice. Interact with response to update the satings.")
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
@bot.tree.command(name="check_roll_enabled",
    description=f"Checks if the rolling and rerolling is Disabled or Enabled. Does not update/change anything.")
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
        f"Rolling is currently: {'ENABLED' if settings['running'] == True else 'DISABLED'}\n\
            Rerolling is {'ENABLED' if settings['rerolling'] == True else 'DISABLED'}"
    )


@has_role("Bingo Moderator")
@bot.tree.command(name="tile_completed", description=f"Marks a channel's tile as completed(Normal)")
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
    if not settings['running']:
        await interaction.response.send(f'Bingo is not currently running. No action has occurred. ')
        return
    if settings['bot_mode']['current'] in ['candyland', 'chutes and ladders']:
        await interaction.response.send(f'This has not been implemented... No action has occurred')
        return
    else:
        # normal bingo mode
        # some way to track which tile is being marked completed and where to mark is required.
        pass
    # Update settings or however this is tracked.
    
    # Update score in settings
    # Update score in scoreboard channel
    # Make a channel for Unverified completed Tiles for moderators. requires two dif moderators to react

    await interaction.followup.send(
        f"Tile is marked: COMPLETED\nScore will be updated accordingly"
    )


@has_role("Bingo Moderator")
@bot.tree.command(name="version", description=f"Change the Bot's Bingo Version or view current.")
async def version(
    interaction: discord.Interaction,
    bingo_version: bool = False,
    candyland: bool = False,
    chutes_and_ladders: bool = False,
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
    elif chutes_and_ladders:
        settings["bot_mode"]["current"] = "chutes and ladders"
    save_settings_json(settings)
    await interaction.followup.send(
        f"Bingo Bot Version is: '{settings['bot_mode']['current']}'"
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(name="mark_specific_tile_completed",
    description=f"Mark a tile as completed on the bingo board, Column A-E. Row 1-5. 'A1' for example.")
async def mark_specific_tile_completed(interaction: discord.Interaction, team_name: str, location: str):
    """
    Marks a tile as completed for a specific team and updates the Bingo Card.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - team_name (str): The name of the team.
    - location (str): The location of the tile in the Bingo Card.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    if settings['bot_mode']['current'] != "normal":
        await interaction.followup.send(f"This command only works when Bot is in mode 'normal'. Current Mode: {settings['bot_mode']['current']}")
        return
    team_names = [x for x in settings["teams"].keys()]
    team_number = team_names.index(team_name) + 1
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
@bot.tree.command(name="post_bingo_card",
    description=f"Post the saved bingo card to '#bingo-card' channel.")
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
    if settings['bot_mode']['current'] == "normal":
        await interaction.followup.send(f"Not in a bingo mode that requires this. Current Mode: {settings['bot_mode']['current']}")
        return
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
@bot.tree.command(name="default_bingo_card",
    description=f"Post the default bingo card to '#bingo-card' channel. From /upload_board_image.")
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
    # settings["teams"][team_name]["image"] = os.path.join(
    #     IMAGE_PATH, "bingo_card_image.png"
    # )
    # update_settings_json(settings)
    await post_or_update_bingo_card(
        interaction, settings, team_name, update=update, row=0, column=0
    )
    await interaction.followup.send(
        f"Posted Bingo Card image in {team_name}'s Bingo Card Channel"
    )


@has_role("Bingo Moderator")
@bot.tree.command(name="upload_board_image",
    description=f"Attach and upload image as the default Bingo Card Image. Overwrites all teams existing images.")
async def upload_board_image(interaction: discord.Interaction, file: discord.Attachment):
    """
    Uploads a board image and updates the default Bingo Card Image for all teams.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
    - file (discord.Attachment): The image file to be uploaded.

    Returns:
    None
    """
    settings = load_settings_json()
    await interaction.response.defer(thinking=True)
    if not file:
        await interaction.followup.send(
            f"Please attach an image to set as the default Bingo Card Image"
        )
        return
    else:
        team_names = [x for x in settings["teams"].keys()]
        # check game style
        if settings["bot_mode"]["current"] == "chutes and ladders":
            image_path = os.path.join(IMAGE_TEMPLATE_PATH, "bingo_card_image.png")
            settings["board_template"] = image_path
        else:
            image_path = os.path.join(IMAGE_PATH, "bingo_card_image.png")
            for team_name in team_names:
                settings["teams"][team_name]["image"] = image_path

        # download attachment
        with open(image_path, "wb") as f:
            await file.save(f)
        # update all settings['teams'][team_name]['image']
        update_settings_json(settings)
        await interaction.followup.send(f"Default Bingo Card Image has been updated")


@has_role("Bingo Moderator")
@bot.tree.command(name="set_image_bounds",
    description=f"Set the bounds for the bingo card to be auto marked as completed by bot.",)
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
            settings["image_bounds"] = {
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
@bot.tree.command(name="set_board_bounds",
    description=f"Set the bounds for the Chutes and Ladder style bingo card to be auto marked as completed by bot.",)
async def set_board_bounds(
    interaction: discord.Interaction,
    tile_count: int,
    tile_size: int,
    team_icon_x_offset: int,
    team_icon_y_offset: int,
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
    - tile_count: Number of tiles on the board.
    - tile_size: Size of square tile.
    - team_icon_x_offset: adjusting the icon's offset from horizontal, left edge of tile
    - team_icon_y_offset: adjusting the icon's offset from vertical, top edge of tile
    - x: The x-coordinate of the image.
    - y: The y-coordinate of the image.
    - x_left_offset: The left offset of the image.
    - x_right_offset: The right offset of the image.
    - y_top_offset: The top offset of the image.
    - y_bottom_offset: The bottom offset of the image.
    - gutter: The gutter size between tiles.

    Returns:
    - None
    """
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
    await interaction.response.defer(thinking=True)
    if (
        tile_count == ""
        or tile_size == ""
        or team_icon_x_offset == ""
        or team_icon_y_offset == ""
        or x_left_offset == ""
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
            settings["board_bounds"] = {
                "tile_count": tile_count,
                "tile_size": tile_size,
                "team_icon_x_offset": team_icon_x_offset,
                "team_icon_y_offset": team_icon_y_offset,
                "x_offset": x_left_offset,
                "y_offset": y_top_offset,
                "x_right_offset": x_right_offset,
                "y_bottom_offset": y_bottom_offset,
                "x": x,
                "y": y,
                "gutter": gutter,
            }
        update_settings_json(settings)
        await interaction.followup.send(f"Board bounds for each team have been updated")
        update_settings_json(settings)



@has_role("Bingo Moderator")
@bot.tree.command(name="sync", description=f"Sync the command tree with the current settings.")
async def sync(interaction: discord.Interaction):
    """
    Synchronizes the command tree with the bot.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the user's command interaction.

    Returns:
    None
    """
    await interaction.response.defer(thinking=False)
    await bot.tree.sync()
    print("sync command")
    await interaction.followup.send("Command tree synced.")


@has_role("Bingo Moderator")
@bot.tree.command(name="close_server",
    description=f"Remove all roles from non-admin or bingo moderator roles.",)
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
@bot.tree.command(name="update_total_teams", description=f"Update the number of active teams.")
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
@bot.tree.command(name="reset_bingo_settings", description=f"Reset persistent bingo settings.")
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
            self, interaction: discord.Interaction,
            button: discord.ui.Button
        ):
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Aborted Reseting of Settings.\nNothing was modified",
                view=self,
            )

        @discord.ui.button(label="Reset", style=discord.ButtonStyle.green)
        async def reset_settings(
            self, interaction: discord.Interaction,
            button: discord.ui.Button
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
                # # set image bounds to default
                # settings["image_bounds"] = {
                #     "x_offset": 0,
                #     "y_offset": 0,
                #     "x_right_offset": 0,
                #     "y_bottom_offset": 0,
                #     "x": 0,
                #     "y": 0,
                #     "gutter": 0,
                # }
                # set tiles_completed to empty list
                settings["teams"][team_name]["tiles_completed"] = []

            # delete images in IMAGE_PATH that arent default_bingo_card_image.png
            update_settings_json(settings)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"# Reset Bingo Settings.", #\nPrevious Settings:\n{json.dumps(old_settings, indent=4)}",
                view=self,
            )
    await interaction.response.send_message(
        embed=discord.Embed(description=f'Confirm Reset of all Teams scores and settings:'),
        view=ConfirmReset(),
    )

async def process_team_assignment_updates(interaction: discord.Interaction):
    settings = load_settings_json()
    total_teams = settings['total_teams']
    all_roles = []
    for role in interaction.guild.roles:
        if role.name in ROLES:
            all_roles.append(role)
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
            await team_assignment_channel.send(content=content) #, silent=True)
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

@has_role("Bingo Moderator")
@bot.tree.command(name="purge_chutes_and_ladders_images", description=f"Clears out the old images from chutes and ladders game mode board.")
async def purge_chutes_and_ladders_images(interaction: discord.Interaction):

    await interaction.response.defer(thinking=True)
    status = await purge_images(type="chutes and ladders")
    await interaction.followup.send(status)





if __name__ == '__main__':
    print('About to log in with bot')
    bot.run(config.DISCORD_BOT_TOKEN)

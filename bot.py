import discord
from discord import app_commands
from discord.app_commands.checks import has_role
from discord.ext import commands, tasks
import json
import re
import random
import os
import datetime
import math
import config
import asyncio
import tempfile
import errno
import logging
import contextlib
import aiohttp
from discord import Role
from typing import List, Optional
from PIL import Image, ImageDraw
import csv
from io import StringIO

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

DICE_SIDES = 6

IMAGE_PATH = os.path.join(os.getcwd(), "images")
IMAGE_TEMPLATE_PATH = os.path.join(os.getcwd(), "template_images")

ALLOWED_IMAGE_DIRS = [IMAGE_PATH, IMAGE_TEMPLATE_PATH]


def validate_image_path(path: str) -> str:
    """Resolve an image path and ensure it stays within allowed directories."""
    resolved = os.path.realpath(path)
    if not any(resolved.startswith(os.path.realpath(d)) for d in ALLOWED_IMAGE_DIRS):
        raise ValueError(f"Image path escapes allowed directories: {path}")
    return resolved

logger.info(f"{IMAGE_PATH = }")

# Async lock for settings.json read/write to prevent race conditions
_settings_lock = asyncio.Lock()

MODERATOR_ROLE = "Bingo Moderator"

MAX_TEAMS = 7

ROLES = [f"Team {i}" for i in range(1, MAX_TEAMS + 1)]
TEAM_CAPTAIN_ROLES = [f"Team {i} Captain" for i in range(1, MAX_TEAMS + 1)]

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
    "bot_mode": {"bot_options": ["candyland", "normal", "chutes and ladders"], "current": "candyland"},
    "tiles": {"url": "", "spreadsheet_id": "", "items": {}},
    "running": True,
    "rerolling": False,
    "total_teams": MAX_TEAMS,
    "teams": {
        f"Team {i}": {"display_name": "", "current": 0, "prev": None, "reroll": True, "roll_history": [], "tiles_completed": []}
        for i in range(1, MAX_TEAMS + 1)
    },
    "image_bounds": {
        "x_offset": 0, "y_offset": 0, "x_right_offset": 0,
        "y_bottom_offset": 0, "x": 0, "y": 0, "gutter": 0,
    },
    "board_bounds": {
        "tile_count": 100, "tile_size": 100, "team_icon_x_offset": 0,
        "team_icon_y_offset": 0, "x_offset": 0, "y_offset": 0,
        "x_right_offset": 0, "y_bottom_offset": 0, "x": 0, "y": 0, "gutter": 0,
    },
    "board_template": "",
    "board_latest": "",
    "items": {},
    "posts": {"score-board": {"id": None, "content": ""}},
    "brief_teams_channels": False,
    "scoring": {
        "default_tile_points": 1,
        "line_bonus": 0,
        "blackout_bonus": 0,
        "approvals_required": 1,
    },
    "submissions": {"next_id": 1, "items": {}},
}

# Defaults for settings.json files created before scoring existed.
DEFAULT_SCORING = dict(default_settings_dict["scoring"])

# Normal mode bingo cards are a 5x5 grid.
BOARD_SIZE = 5

# Team score changes kept per team for /score history and /score undo.
SCORE_LOG_LIMIT = 200

# Submissions are reviewed in #submissions, or in #bot-commands if that doesn't exist.
SUBMISSIONS_CHANNEL = "submissions"

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


def validate_team_name(team_name: str, settings: dict) -> Optional[str]:
    """Return an error message if team_name is invalid, or None if valid."""
    team_names = list(settings["teams"].keys())
    if team_name not in team_names:
        return f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
    return None


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
        logger.info("created settings.json file")


def load_settings_json():
    """
    Load the settings from the settings.json file.

    Returns:
        dict: The loaded settings.
    """
    if not os.path.exists("settings.json"):
        logger.warning("trying to load settings.json but file does not exist")
        create_settings_json()
    try:
        with open("settings.json") as f:
            settings = json.load(f)
            return settings
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load settings.json: {e}")
        raise


def save_settings_json(contents: dict) -> None:
    """
    Save the settings to the settings.json file.
    Uses atomic write (temp file + rename) to prevent corruption on crash.
    Falls back to an in-place write when settings.json is a Docker single-file
    bind mount, where rename onto the mount point fails with EBUSY/EXDEV.

    Args:
        contents (dict): The settings to save.
    """
    data = json.dumps(contents, indent=4)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=".")
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, "settings.json")
            tmp_path = None
            return
        except OSError as e:
            if e.errno not in (errno.EBUSY, errno.EXDEV):
                raise
        # Bind-mounted file: rewrite contents in place instead of renaming.
        with open("settings.json", "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        logger.error(f"Failed to save settings.json: {e}")
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _reset_all_settings() -> dict:
    """
    Reset every team's progress in settings.json to defaults.

    Returns:
        dict: Team key -> display name it had before the reset, for teams
        that had a custom display name.
    """
    settings = load_settings_json()
    settings["total_teams"] = MAX_TEAMS
    renamed = {}
    for team_key, team in settings["teams"].items():
        if team.get("display_name") and team["display_name"] != team_key:
            renamed[team_key] = team["display_name"]
        team["display_name"] = ""
        team["tiles_completed"] = []
        team["current"] = 0
        team["prev"] = 0
        team["reroll"] = 0
        team["roll_history"] = []
        team["score_log"] = []
        team["image"] = os.path.join(IMAGE_PATH, "bingo_card_image.png")
    # Drop the last game's submissions. next_id is kept so old review
    # messages' buttons can't match a new submission.
    submissions = settings.setdefault("submissions", {"next_id": 1, "items": {}})
    submissions["items"] = {}
    save_settings_json(settings)
    return renamed


def get_team_display_name(settings: dict, team_key: str) -> str:
    """
    Get the display name for a team. Returns display_name if set, otherwise the team key.

    Args:
        settings (dict): The current settings.
        team_key (str): The internal team key (e.g., "Team 1").

    Returns:
        str: The display name or the team key.
    """
    team = settings["teams"].get(team_key, {})
    return team.get("display_name") or team_key


def get_team_key_by_display_name(settings: dict, display_name: str) -> Optional[str]:
    """
    Look up the internal team key from a display name or category name.
    Falls back to matching team keys directly if no display_name matches.

    Args:
        settings (dict): The current settings.
        display_name (str): The display name or category name to look up.

    Returns:
        str or None: The internal team key, or None if not found.
    """
    for key, team_data in settings["teams"].items():
        if team_data.get("display_name") and team_data["display_name"] == display_name:
            return key
    # Fallback: check if display_name matches a team key directly
    if display_name in settings["teams"]:
        return display_name
    return None


@contextlib.asynccontextmanager
async def edit_settings():
    """
    Load settings.json under the settings lock and save it when the block exits.
    Use this whenever there is an `await` between loading and saving settings,
    so a concurrent command (e.g. another team's /roll) can't be overwritten.
    If the block raises, nothing is saved.
    """
    async with _settings_lock:
        settings = load_settings_json()
        yield settings
        save_settings_json(settings)


def find_category(guild: discord.Guild, name: str) -> Optional[discord.CategoryChannel]:
    """Find a category by name, ignoring case."""
    name = name.lower()
    return discord.utils.find(lambda c: c.name.lower() == name, guild.categories)


def find_team_category(
    guild: discord.Guild, settings: dict, team_key: str
) -> Optional[discord.CategoryChannel]:
    """
    Find a team's category. Categories are named after the team's display name
    once one is set (/change_team_name), otherwise after the team key.
    """
    display = get_team_display_name(settings, team_key)
    cat = find_category(guild, display)
    if cat is None and display != team_key:
        cat = find_category(guild, team_key)
    return cat


MENTION_RE = re.compile(r"^<@!?(\d+)>$")


def parse_member_ids(text: str) -> (List[int], List[str]):
    """
    Parse user mentions (<@id> or <@!id>) or raw user IDs from a string.

    Returns:
        tuple: (member IDs, tokens that could not be parsed)
    """
    ids, invalid = [], []
    for token in text.split():
        match = MENTION_RE.match(token)
        if match:
            ids.append(int(match.group(1)))
        elif token.isdigit():
            ids.append(int(token))
        else:
            invalid.append(token)
    return ids, invalid


class ModeratorView(discord.ui.View):
    """A view whose buttons only Bingo Moderators can use."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_moderator(interaction.user):
            return True
        await interaction.response.send_message(
            f"Only a {MODERATOR_ROLE} can use these buttons.", ephemeral=True
        )
        return False


def update_settings_json(contents: dict) -> dict:
    """
    Save the settings to the settings.json file.

    Args:
        contents (dict): The current settings.

    Returns:
        dict: The saved settings.
    """
    save_settings_json(contents)
    return contents


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
    item = settings.get("items", {}).get(str(tile_num))
    if not item:
        return f"{tile_num} - Unknown Tile"
    name = item.get("name", "Unknown")

    desc = item.get("short_desc")
    if not desc:
        desc = item.get("desc", "")
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
    board_mode = contents["bot_mode"]["current"] in ("candyland", "chutes and ladders")
    # Board modes use 7 columns. Normal mode uses name, desc and an optional
    # points column. Extra columns are ignored and missing ones are treated as empty.
    num_columns = 7 if board_mode else 3
    tile_index = 0
    for row_index, row in enumerate(tile_list):
        if row_index == 0:
            # skip header
            continue
        if not any(cell.strip() for cell in row):
            # skip blank rows so they don't count as tiles
            continue
        tile_index += 1
        row = (list(row) + [""] * num_columns)[:num_columns]
        if board_mode:
            tile_num, name, short_desc, desc, sabotage, item_names, diff = row
            items[tile_index] = {
                "tile_num": tile_num,
                "name": name,
                "short_desc": short_desc,
                "desc": desc,
                "sabotage": sabotage,
                "item_names": item_names,
                "discord_name": f"{tile_index}. {name} - {desc}",
            }
        else:
            name, desc, points = row
            items[tile_index] = {"name": name, "desc": desc, "discord_name": f"{name} - {desc}"}
            if points.strip():
                items[tile_index]["points"] = points.strip()
    contents["items"] = items
    return contents


class SheetLoadError(Exception):
    """Raised when the Google Sheet can't be downloaded as CSV."""


SPREADSHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
SHEET_GID_RE = re.compile(r"[#&?]gid=(\d+)")


def parse_sheet_url(url: str) -> (Optional[str], str):
    """
    Get the spreadsheet ID and sheet tab ID (gid) from a Google Sheets URL.

    Returns:
        tuple: (spreadsheet ID or None if the URL isn't a Google Sheet, gid)
    """
    id_match = SPREADSHEET_ID_RE.search(url)
    gid_match = SHEET_GID_RE.search(url)
    return (id_match.group(1) if id_match else None), (gid_match.group(1) if gid_match else "0")


async def load_sheet(spreadsheet_id: str, gid: str = "0") -> list:
    """
    Load public Google Sheet data without authentication using CSV export.

    Args:
        spreadsheet_id (str): The ID of the Google Sheet.
        gid (str, optional): The sheet tab ID. Defaults to the first tab.

    Returns:
        list: The rows from the Google Sheet.

    Raises:
        SheetLoadError: If the sheet can't be downloaded or isn't public.
    """
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                text = await response.text()
                content_type = response.headers.get("Content-Type", "")
                if response.status != 200 or "text/csv" not in content_type:
                    # Private sheets redirect to a Google sign-in page.
                    logger.error(f"Failed to fetch sheet: {response.status} {content_type}")
                    raise SheetLoadError(
                        f"Google returned {response.status} ({content_type or 'no content type'}). "
                        "Check the sheet is shared as 'Anyone with the link'."
                    )
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise SheetLoadError(f"Could not reach Google Sheets: {e}") from e
    return list(csv.reader(StringIO(text)))


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
    title = f"{itm.get('tile_num') or tile_number} - {itm.get('name', '')}"
    if itm.get("short_desc"):
        title += f" - {itm['short_desc']}"
    embed = discord.Embed(
        title=title[:256],  # Discord's embed title limit
        description=itm.get("desc", ""),
        color=0xF7E302,
    )
    return embed


def _tile_mark_box(img_size, image_bounds: dict, row: int, column: int) -> (list, int):
    """
    Get the pixel box for a 5x5 bingo tile and the line width to mark it with.

    Args:
        img_size (tuple): The (width, height) of the card image.
        image_bounds (dict): settings["image_bounds"] from /set_image_bounds.
        row (int): The 1-indexed row of the tile.
        column (int): The 1-indexed column of the tile.

    Returns:
        tuple: ([x1, y1, x2, y2], line width)
    """
    x_offset = image_bounds.get("x_offset") or 0
    y_offset = image_bounds.get("y_offset") or 0
    x_right_offset = image_bounds.get("x_right_offset") or 0
    y_bottom_offset = image_bounds.get("y_bottom_offset") or 0
    gutter = image_bounds.get("gutter") or 0
    if not image_bounds.get("x") and not image_bounds.get("y"):
        width, height = img_size
        width = width - (x_offset + x_right_offset + ((BOARD_SIZE - 1) * gutter))
        height = height - (y_offset + y_bottom_offset + ((BOARD_SIZE - 1) * gutter))
    else:
        width = image_bounds["x"]
        height = image_bounds["y"]

    line_width = max(1, int(width * 0.01 / 2))
    tile_width = width // BOARD_SIZE
    tile_height = height // BOARD_SIZE

    # Zero-indexed row and column
    row -= 1
    column -= 1
    x1 = (column * tile_width) + x_offset + (column * gutter)
    y1 = (row * tile_height) + y_offset + (row * gutter)
    x2 = ((column + 1) * tile_width) + x_offset + (column * gutter)
    y2 = ((row + 1) * tile_height) + y_offset + (row * gutter)
    return [x1, y1, x2, y2], line_width


def render_team_card(settings: dict, team_name: str) -> str:
    """
    Draw a team's bingo card from the default card image (/upload_board_image)
    with a red X on every tile in settings["teams"][team]["tiles_completed"].
    Redrawing from scratch each time means unmarking a tile removes its X.
    Updates settings["teams"][team]["image"]; the caller saves settings.

    Args:
        settings (dict): The current settings.
        team_name (str): The team key.

    Returns:
        str: The path of the rendered card image.
    """
    base_path = os.path.join(IMAGE_PATH, "bingo_card_image.png")
    if not os.path.exists(base_path):
        base_path = os.path.join(IMAGE_TEMPLATE_PATH, "bingo_card_image.png")
    base_path = validate_image_path(base_path)
    with Image.open(base_path) as base:
        img = base.convert("RGBA")
    draw = ImageDraw.Draw(img)
    for row, column in settings["teams"][team_name].get("tiles_completed", []):
        box, line_width = _tile_mark_box(img.size, settings.get("image_bounds", {}), row, column)
        x1, y1, x2, y2 = box
        draw.rectangle(box, outline="red", width=line_width)
        draw.line([(x1, y1), (x2, y2)], fill="red", width=line_width)
        draw.line([(x1, y2), (x2, y1)], fill="red", width=line_width)
    os.makedirs(IMAGE_PATH, exist_ok=True)
    new_image_path = os.path.join(IMAGE_PATH, f"{create_discord_friendly_name(team_name)}-card.png")
    img.save(new_image_path)
    settings["teams"][team_name]["image"] = new_image_path
    return new_image_path


# ======================================= Scoring ====================================================


def is_board_mode(settings: dict) -> bool:
    """True for the modes where a team's score is its tile on the board."""
    return settings["bot_mode"]["current"] in ("candyland", "chutes and ladders")


def get_scoring(settings: dict) -> dict:
    """The scoring settings, filled in with defaults for older settings.json files."""
    return {**DEFAULT_SCORING, **settings.get("scoring", {})}


def location_label(row: int, column: int) -> str:
    """Turn a 1-indexed (row, column) into an Excel-style label such as "A1"."""
    return f"{'ABCDE'[column - 1]}{row}"


def tile_key_for_location(row: int, column: int) -> str:
    """
    The settings["items"] key for a 5x5 board location. Tiles are read from
    the sheet left to right, top to bottom: A1-E1 are tiles 1-5, A2 is tile 6.
    """
    return str((row - 1) * BOARD_SIZE + column)


def location_for_tile_key(key) -> Optional[tuple]:
    """The (row, column) of a tile number on the 5x5 board, or None if it is off the board."""
    index = int(key)
    if not 1 <= index <= BOARD_SIZE * BOARD_SIZE:
        return None
    return (index - 1) // BOARD_SIZE + 1, (index - 1) % BOARD_SIZE + 1


def tile_points(settings: dict, item: Optional[dict]) -> int:
    """A tile's points from the sheet's points column, or the default."""
    default = get_scoring(settings)["default_tile_points"]
    try:
        return int(str((item or {}).get("points", "")).strip())
    except ValueError:
        return default


def describe_location(settings: dict, row: int, column: int) -> str:
    """Label for a normal mode tile, e.g. "A1 Zulrah"."""
    item = settings.get("items", {}).get(tile_key_for_location(row, column))
    label = location_label(row, column)
    return f"{label} {item['name']}" if item and item.get("name") else label


def completed_lines(tiles) -> int:
    """Count the completed rows, columns and diagonals on a 5x5 board."""
    done = {tuple(t) for t in tiles}
    span = range(1, BOARD_SIZE + 1)
    lines = [[(r, c) for c in span] for r in span]
    lines += [[(r, c) for r in span] for c in span]
    lines.append([(i, i) for i in span])
    lines.append([(i, BOARD_SIZE + 1 - i) for i in span])
    return sum(all(cell in done for cell in line) for line in lines)


def is_blackout(tiles) -> bool:
    """True when every tile on the 5x5 board is completed."""
    return len({tuple(t) for t in tiles}) >= BOARD_SIZE * BOARD_SIZE


def clamp_score(settings: dict, value: int) -> int:
    """Keep a score at 0 or more, and on the board in board modes."""
    value = max(0, value)
    if is_board_mode(settings) and settings.get("items"):
        value = min(value, len(settings["items"]))
    return value


def apply_score_change(
    settings: dict,
    team_name: str,
    *,
    delta: int = 0,
    set_to: Optional[int] = None,
    reason: str = "",
    by: str = "",
    kind: str = "manual",
    tile=None,
    unmark: bool = False,
    group: Optional[int] = None,
) -> dict:
    """
    Change a team's score and add an entry to its score log.
    Call inside edit_settings() so the change is saved.

    Args:
        settings (dict): The current settings, changed in place.
        team_name (str): The team key.
        delta (int): Points to add (negative to remove). Ignored if set_to is given.
        set_to (int, optional): Set the score to this value instead.
        reason (str): Why the score changed, shown in history and announcements.
        by (str): Who made the change.
        kind (str): "manual", "set", "tile", "bonus" or "undo".
        tile: The [row, column] of the tile for "tile" entries.
        unmark (bool): For "tile" entries, True if the tile was unmarked.
        group (int, optional): Entry ID of the first change in the same action,
            so /score undo reverts the whole action. Defaults to this entry.

    Returns:
        dict: The new score log entry.
    """
    team = settings["teams"][team_name]
    before = team.get("current") or 0
    after = clamp_score(settings, set_to if set_to is not None else before + delta)
    team["score_seq"] = team.get("score_seq", 0) + 1
    entry = {
        "id": team["score_seq"],
        "group": group if group is not None else team["score_seq"],
        "kind": kind,
        "delta": after - before,
        "before": before,
        "after": after,
        "reason": reason,
        "by": by,
        "at": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
    }
    if tile is not None:
        entry["tile"] = list(tile)
        entry["unmark"] = unmark
    team["current"] = after
    log = team.setdefault("score_log", [])
    log.append(entry)
    del log[:-SCORE_LOG_LIMIT]
    return entry


def _bonus_changes(settings, team_name, old_tiles, new_tiles, *, by, group) -> list:
    """Score log entries for rows/columns/diagonals and blackout gained or lost."""
    scoring = get_scoring(settings)
    entries = []
    line_change = completed_lines(new_tiles) - completed_lines(old_tiles)
    if line_change and scoring["line_bonus"]:
        entries.append(apply_score_change(
            settings, team_name,
            delta=line_change * scoring["line_bonus"],
            reason=f"{abs(line_change)} line(s) {'completed' if line_change > 0 else 'broken'}",
            by=by, kind="bonus", group=group,
        ))
    blackout_change = int(is_blackout(new_tiles)) - int(is_blackout(old_tiles))
    if blackout_change and scoring["blackout_bonus"]:
        entries.append(apply_score_change(
            settings, team_name,
            delta=blackout_change * scoring["blackout_bonus"],
            reason="Blackout" if blackout_change > 0 else "Blackout lost",
            by=by, kind="bonus", group=group,
        ))
    return entries


def complete_tile(settings: dict, team_name: str, row: int, column: int, *, by: str, reason: str = "") -> Optional[list]:
    """
    Mark a normal mode tile completed and award its points and any line or
    blackout bonus. Call inside edit_settings().

    Returns:
        list or None: The score log entries, or None if it was already completed.
    """
    tiles = settings["teams"][team_name].setdefault("tiles_completed", [])
    if [row, column] in tiles:
        return None
    old_tiles = [list(t) for t in tiles]
    tiles.append([row, column])
    item = settings.get("items", {}).get(tile_key_for_location(row, column))
    label = describe_location(settings, row, column)
    entry = apply_score_change(
        settings, team_name,
        delta=tile_points(settings, item),
        reason=f"{label}{f' ({reason})' if reason else ''}",
        by=by, kind="tile", tile=[row, column],
    )
    return [entry] + _bonus_changes(settings, team_name, old_tiles, tiles, by=by, group=entry["id"])


def uncomplete_tile(settings: dict, team_name: str, row: int, column: int, *, by: str) -> Optional[list]:
    """
    Unmark a normal mode tile and take back the points it gave, including any
    line or blackout bonus it was part of. Call inside edit_settings().

    Returns:
        list or None: The score log entries, or None if it wasn't completed.
    """
    tiles = settings["teams"][team_name].setdefault("tiles_completed", [])
    if [row, column] not in tiles:
        return None
    old_tiles = [list(t) for t in tiles]
    tiles.remove([row, column])
    item = settings.get("items", {}).get(tile_key_for_location(row, column))
    entry = apply_score_change(
        settings, team_name,
        delta=-tile_points(settings, item),
        reason=f"Unmarked {describe_location(settings, row, column)}",
        by=by, kind="tile", tile=[row, column], unmark=True,
    )
    return [entry] + _bonus_changes(settings, team_name, old_tiles, tiles, by=by, group=entry["id"])


def undo_last_score_change(settings: dict, team_name: str, *, by: str) -> (list, list):
    """
    Revert the team's most recent score action that hasn't been undone,
    including all of its entries (e.g. a tile and its line bonus). Undoing a
    tile mark unmarks it, and undoing an unmark marks it again.
    Call inside edit_settings().

    Returns:
        tuple: (the entries that were undone, the new undo entries). Both are
        empty if there is nothing to undo.
    """
    log = settings["teams"][team_name].get("score_log", [])
    candidates = [e for e in log if e["kind"] != "undo" and not e.get("undone")]
    if not candidates:
        return [], []
    group = candidates[-1]["group"]
    undone = [e for e in candidates if e["group"] == group]
    tiles = settings["teams"][team_name].setdefault("tiles_completed", [])
    new_entries = []
    undo_group = None
    for e in reversed(undone):
        e["undone"] = True
        if e["kind"] == "tile" and e.get("tile"):
            if e.get("unmark"):
                if e["tile"] not in tiles:
                    tiles.append(e["tile"])
            elif e["tile"] in tiles:
                tiles.remove(e["tile"])
        undo_entry = apply_score_change(
            settings, team_name,
            delta=-e["delta"],
            reason=f"Undo #{e['id']}: {e['reason']}",
            by=by, kind="undo", group=undo_group,
        )
        undo_group = undo_group or undo_entry["id"]
        new_entries.append(undo_entry)
    return undone, new_entries


def format_score_entries(settings: dict, team_name: str, entries: list) -> str:
    """One line per score change, e.g. "+3 A1 Zulrah (by Mod) -> 12"."""
    lines = []
    for e in entries:
        sign = "+" if e["delta"] >= 0 else ""
        lines.append(f"{sign}{e['delta']} {e['reason']} (by {e['by']}) -> {e['after']}")
    return f"**{get_team_display_name(settings, team_name)}** score update:\n" + "\n".join(lines)


def ordinal(n: int) -> str:
    """1 -> "1st", 2 -> "2nd", 11 -> "11th"."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def rank_teams(scores: list) -> list:
    """
    Rank (team_key, score) pairs highest first. Tied teams share a place and
    the next place is skipped (1, 1, 3).

    Returns:
        list: (place, team_key, score) tuples.
    """
    ordered = sorted(scores, key=lambda s: -s[1])
    ranked = []
    for i, (key, score) in enumerate(ordered):
        place = ranked[-1][0] if ranked and ranked[-1][2] == score else i + 1
        ranked.append((place, key, score))
    return ranked


TABLE_LOCATION_RE = re.compile(r"^\s*([A-Ea-e])\s*([1-5])\s*$")


def parse_table_location(location: str) -> Optional[tuple]:
    """
    Parse an Excel-style 5x5 board location such as "A1" or "e5".
    Columns are A-E, rows are 1-5.

    Returns:
        tuple: (row, column), both 1-indexed, or None if the location is invalid.
    """
    match = TABLE_LOCATION_RE.match(location or "")
    if not match:
        return None
    col = "abcde".index(match.group(1).lower()) + 1
    row = int(match.group(2))
    return row, col


def generate_team_assignment_text(all_roles, total_teams, settings=None) -> str:
    """
    Generate a text representation of team assignments based on the given roles and total number of teams.

    Parameters:
    all_roles (list): A list of roles representing the teams.
    total_teams (int): The total number of teams to generate assignments for.
    settings (dict, optional): Settings dict to look up display names.

    Returns:
    str: A string representation of team assignments, with each line containing the role name followed by the IDs of the members in that role.
    """
    content = []
    all_roles.sort(key=lambda x: x.name)
    for i, role in enumerate(all_roles):
        if i >= total_teams:
            continue
        display = role.name
        if settings:
            display = get_team_display_name(settings, role.name)
        formatted_text = f"# {display}:\n{' '.join([f'<@{str(r.id)}>' for r in role.members])}\n"
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
    image_path_src = validate_image_path(settings['board_template'])
    if not os.path.exists(image_path_src):
        image_path_src = os.path.join(IMAGE_TEMPLATE_PATH, "bingo_card_image.png")
        settings['board_template'] = image_path_src
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
    icon_path = os.path.dirname(image_path_src)
    icon_team_files = [x for x in os.listdir(icon_path) if "CNL_Team" in x]
    icon_team_files.sort()
    icon_team_files.reverse()
    icon_team_files = [os.path.join(icon_path, x) for x in icon_team_files]
    team_names = [x for x in settings['teams'].keys()]
    team_names.reverse()
    team_scores = [(x,settings['teams'][x]['current']) for x in settings['teams']]
    team_scores.reverse()
    all_scores = [x[1] for x in team_scores]
    # How many icons have already been placed on each shared tile
    dupe_scores_processed = {}
    for i in range(len(team_names)):
        team_name = team_names[i]
        score = team_scores[i][1]
        if score == 0:
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
            placed = dupe_scores_processed.get(score, 0)
            offset_multiplier = number_of_tiles - placed - 1
            new_x = x + (board_bounds['team_icon_x_offset'] + offset_multiplier * (math.floor(offset_width / number_of_tiles)))
            dupe_scores_processed[score] = placed + 1
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
        folder_path = os.path.join(os.path.dirname(validate_image_path(settings['board_template'])), "generated")
        old_image_files = [x for x in os.listdir(folder_path) if "CNL-" in x]
        for file in old_image_files:
            os.remove(os.path.join(folder_path, file))
        return f"Removed {len(old_image_files)} image files."
    else:
        return f"Bot mode is not supported. Current Mode: {settings['bot_mode']['current']}"

async def send_or_update_tiles_channel(tile_list_ch, settings):
    item_list = []
    board_mode = settings["bot_mode"]["current"] in ("candyland", "chutes and ladders")
    for tile in settings["items"].values():
        name = tile.get("name", "")
        desc = tile.get("desc", "")
        if board_mode:
            item_list.append(f"## {tile.get('tile_num', '')} - {name}\n{desc}")
        else:
            item_list.append(f"## {name}\n{desc}")
    chunked_list = chunk_item_list_text(item_list)
    # The bot's earlier tile list messages, oldest first. Only the bot's own
    # messages are counted so other messages in the channel don't shift the order.
    bot_messages = [
        m async for m in tile_list_ch.history(limit=None, oldest_first=True)
        if m.author == bot.user
    ]
    for i, chunk in enumerate(chunked_list):
        description = f"# All Tiles\n\n{chunk}" if i == 0 else chunk
        embed = discord.Embed(description=description)
        if i < len(bot_messages):
            await bot_messages[i].edit(content=None, embed=embed)
        else:
            await tile_list_ch.send(embed=embed)
    # Remove leftover messages from an earlier, longer tile list.
    for m in bot_messages[len(chunked_list):]:
        await m.delete()

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
            if settings["brief_teams_channels"]:
                return discord_safe_names
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


async def clear_team_roles(interaction):
    """
    Clear the team roles from all members in the guild.

    Args:
        interaction: The Discord interaction object.
    """
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    for member in interaction.guild.members:
        await member.remove_roles(*roles)
    logger.info("Removed Team Roles from All Members")

async def post_or_update_bingo_card(
    interaction: discord.Interaction,
    settings: dict,
    team_name: str,
) -> Optional[str]:
    """
    Posts or updates a bingo card image for a specific team in a Discord channel.
    Uses the team's current card image; call render_team_card() first to
    redraw it after tiles change.

    Parameters:
        interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.
        settings (dict): The settings dictionary containing information about the teams and their bingo cards.
        team_name (str): The name of the team for which the bingo card image should be posted or updated.

    Returns:
        str or None: An error message if the card couldn't be posted, otherwise None.
    """
    cat = find_team_category(interaction.guild, settings, team_name)
    if cat is None:
        return f'No category found for "{get_team_display_name(settings, team_name)}".'
    # Normal mode names the channel "bingo-card"; board modes use "team-<n>-bingo-card".
    bingo_card_chan = discord.utils.find(
        lambda ch: ch.name.endswith("bingo-card"), cat.text_channels
    )
    if bingo_card_chan is None:
        return f'No bingo-card channel found in "{cat.name}".'

    image_path = settings["teams"][team_name].get("image") or os.path.join(IMAGE_PATH, "bingo_card_image.png")
    if not os.path.exists(image_path):
        return f'No bingo card image found for "{get_team_display_name(settings, team_name)}". Use /upload_board_image first.'
    # A fixed attachment name so the embed's attachment:// link always matches.
    filename = "bingo_card.png"
    img = discord.File(image_path, filename=filename)
    embed = discord.Embed(
        title=f"{get_team_display_name(settings, team_name)} Bingo Card",
        color=0xF7E302,
    )
    embed.set_image(url=f"attachment://{filename}")

    # Edit the bot's latest card post if there is one, otherwise post a new one.
    async for message in bingo_card_chan.history(limit=50):
        if message.author == bot.user and message.embeds and message.embeds[0].title and message.embeds[0].title.endswith("Bingo Card"):
            await message.edit(embed=embed, attachments=[img])
            logger.info(f"Updated {team_name} Bingo Card Image")
            return None
    await bingo_card_chan.send(embed=embed, file=img)
    logger.info(f"Posted {team_name} Bingo Card Image")
    return None

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


def build_score_text(settings: dict) -> str:
    """
    Build the #score-board message text from the current settings: teams
    ranked highest first, with how far each is behind the leader.
    """
    total_teams = settings.get("total_teams", len(settings["teams"]))
    team_keys = list(settings["teams"].keys())[:total_teams]
    if not team_keys:
        return ""
    mode = settings["bot_mode"]["current"]
    ranked = rank_teams([(key, settings["teams"][key].get("current") or 0) for key in team_keys])
    leader_score = ranked[0][2]
    board_tiles = len(settings.get("items", {}))
    if mode == "chutes and ladders":
        board_tiles = settings.get("board_bounds", {}).get("tile_count") or board_tiles

    lines = ["## Scoreboard"]
    for place, key, score in ranked:
        team = settings["teams"][key]
        name = get_team_display_name(settings, key)
        if is_board_mode(settings):
            row = f"**{ordinal(place)}** {name} - Tile **{score}**"
            if board_tiles:
                row += f"/{board_tiles}"
            if mode == "candyland":
                row += f" | Rerolls: {team.get('reroll', 0)}"
        else:
            row = f"**{ordinal(place)}** {name} - **{score}** pts"
            row += f" | {len(team.get('tiles_completed', []))}/{BOARD_SIZE * BOARD_SIZE} tiles"
        if score < leader_score:
            row += f" | {leader_score - score} behind"
        lines.append(row)
    lines.append(f"-# Updated <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:R>")
    return "\n".join(lines)


def find_team_text_channel(
    guild: discord.Guild, settings: dict, team_name: str, suffix: str
) -> Optional[discord.TextChannel]:
    """Find a text channel in the team's category whose name ends with suffix, e.g. "chat"."""
    cat = find_team_category(guild, settings, team_name)
    if cat is None:
        return None
    return discord.utils.find(lambda ch: ch.name.endswith(suffix), cat.text_channels)


async def announce_to_team(guild: discord.Guild, settings: dict, team_name: str, text: str) -> None:
    """Post a message in the team's chat channel, if it has one."""
    channel = find_team_text_channel(guild, settings, team_name, "chat")
    if channel is None:
        logger.info(f"No chat channel for {team_name}; skipped announcement")
        return
    try:
        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as e:
        logger.error(f"Failed to announce to {team_name}: {e}")


async def publish_score_change(
    interaction: discord.Interaction, team_name: str, entries: list, *, card_changed: bool = False
) -> list:
    """
    After a score change: refresh the team's bingo card (if tiles changed),
    the #score-board, and tell the team in its chat channel.

    Returns:
        list: Problems to report to the moderator, if any.
    """
    settings = load_settings_json()
    problems = []
    if card_changed:
        error = await post_or_update_bingo_card(interaction, settings, team_name)
        if error:
            problems.append(f"Bingo card not updated: {error}")
    error = await update_server_score_board_channel(interaction)
    if error:
        problems.append(f"Scoreboard not updated: {error}")
    if entries:
        await announce_to_team(interaction.guild, settings, team_name, format_score_entries(settings, team_name, entries))
    return problems


async def update_server_score_board_channel(interaction: discord.Interaction) -> Optional[str]:
    """
    Updates the score board channel in the server with the current scores and team information.
    Always reads the latest settings.json so it never saves a stale copy over
    another team's roll.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command interaction.

    Returns:
    str or None: An error message if the score board couldn't be updated, otherwise None.
    """
    score_card_ch = discord.utils.get(interaction.guild.text_channels, name="score-board")
    if score_card_ch is None:
        logger.warning("No #score-board channel found")
        return "No #score-board channel found."

    settings = load_settings_json()
    score_text = build_score_text(settings) or "No scores yet."
    msg_id = settings.get("posts", {}).get("score-board", {}).get("id")

    # Find the score board message: the stored ID first, then the bot's latest
    # message in the channel, otherwise post a new one.
    message = None
    if msg_id:
        try:
            message = await score_card_ch.fetch_message(int(msg_id))
        except discord.NotFound:
            message = None
    if message is None:
        async for msg in score_card_ch.history(limit=50):
            if msg.author == bot.user:
                message = msg
                break
    if message is None:
        message = await score_card_ch.send(content=score_text)

    attachments = []
    if settings["bot_mode"]["current"] == "chutes and ladders":
        img_path = await mark_team_icons_on_board(interaction=interaction)
        if img_path:
            attachments = [discord.File(img_path)]
    await message.edit(content=score_text, attachments=attachments)

    async with edit_settings() as latest:
        score_board = latest.setdefault("posts", {}).setdefault("score-board", {})
        score_board["id"] = message.id
        score_board["content"] = score_text
    return None



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
    # discord.py waits out Discord's rate limits itself, so no manual sleeps here.
    for r in guild_roles:
        if r in roles:
            for m in list(r.members):
                await m.remove_roles(r)
                if not unassign:
                    await m.add_roles(spectator_role)
    logger.info("All members have been updated")
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

# Discord rejects an autocomplete reply with more than 25 choices, or names
# and values longer than 100 characters, and then shows no options at all.
MAX_AUTOCOMPLETE_CHOICES = 25


def autocomplete_choice(name: str, value: str) -> app_commands.Choice[str]:
    """A choice trimmed to Discord's 100 character limit."""
    return app_commands.Choice(name=name[:100], value=value[:100])


async def team_names_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """
    Autocompletes team names based on the current input.
    Shows display_name if set, but passes team key as value.

    Args:
        interaction (discord.Interaction): The interaction object.
        current (str): The current input string.

    Returns:
        List[app_commands.Choice[str]]: A list of app_commands.Choice objects representing the autocompleted team names.
    """
    settings = load_settings_json()
    choices = []
    for team_key in settings["teams"]:
        display = get_team_display_name(settings, team_key)
        if current.lower() in display.lower() or current.lower() in team_key.lower():
            choices.append(autocomplete_choice(display, team_key))
    return choices[:MAX_AUTOCOMPLETE_CHOICES]

async def change_team_names_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """
    Autocompletes team names based on the current input.
    Shows display_name if set, plus non-ignored Discord categories.

    Args:
        interaction (discord.Interaction): The interaction object.
        current (str): The current input string.

    Returns:
        List[app_commands.Choice[str]]: A list of app_commands.Choice objects representing the autocompleted team names.
    """
    settings = load_settings_json()
    options = []
    seen = set()
    for team_key in settings["teams"]:
        display = get_team_display_name(settings, team_key)
        if current.lower() in display.lower() or current.lower() in team_key.lower():
            options.append(autocomplete_choice(display, team_key))
            seen.add(display)
            seen.add(team_key)
    all_categories = [c.name for c in interaction.guild.categories if c.name.lower() not in IGNORED_CATEGORIES]
    for cat_name in all_categories:
        if cat_name not in seen and current.lower() in cat_name.lower():
            options.append(autocomplete_choice(cat_name, cat_name))
    # Teams come first, so they are kept when there are too many categories.
    return options[:MAX_AUTOCOMPLETE_CHOICES]

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
    logger.info("Bot is Ready")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global error handler for application commands."""
    logger.exception("Command error", exc_info=error)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
    except discord.errors.HTTPException:
        pass


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
    await interaction.response.defer(thinking=True)
    async with _settings_lock:
        settings = load_settings_json()
        # Resolve team from category display name
        category_name = interaction.channel.category.name
        team_name = get_team_key_by_display_name(settings, category_name)
        if not team_name:
            await interaction.followup.send(
                f"Could not find a team matching category \"{category_name}\""
            )
            return
        display_name = get_team_display_name(settings, team_name)
        role_name = discord.utils.get(interaction.guild.roles, name=team_name)
        if (
            role_name not in interaction.user.roles
            or roll_channel not in interaction.channel.name
        ):
            await interaction.followup.send(
                f"Please ensure you have appropriate Team Role and are within your Team's #{roll_channel}"
            )
            return

        if not settings["running"]:
            await interaction.followup.send(
                "Rolling is not enabled, either wait till Start time or message @ Bingo Moderator if receiving this message in error."
            )
            return

        roll = roll_dice()
        settings = update_roll_settings(
            roll,
            team_name,
            settings,
            prev=settings["teams"][team_name]["current"],
            current=settings["teams"][team_name]["current"] + roll,
        )
        score_altered = ""

        # Check win condition
        total_tiles = len(settings["items"])
        if settings["teams"][team_name]["prev"] == total_tiles:
            await interaction.followup.send(
                f'# Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention}\nyou have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}'
            )
            return
        elif settings["teams"][team_name]["current"] > total_tiles:
            if settings['bot_mode']['current'] == 'candyland':
                # This makes the last tile mandatory
                settings["teams"][team_name]["current"] = total_tiles
            else:
                # bounce back CNL Tile 98 + 6 > 98 + 2 = 100 -4 = 96 > Tile 96
                score_altered = "bounce back-"
                new_score = 2 * settings['board_bounds']['tile_count'] - settings["teams"][team_name]["current"]
                settings["teams"][team_name]["current"] = new_score

        # Chutes and ladders shortcuts. Checked after the bounce back so a team
        # that bounces onto a chute or ladder still takes it.
        if settings['bot_mode']['current'] == "chutes and ladders":
            current = settings["teams"][team_name]["current"]
            score = calculate_shortcut(current)
            if score:
                score_altered += "ladder-" if score > current else "rats-"
                settings["teams"][team_name]["current"] = score

        update_settings_json(settings)

    name = create_discord_friendly_name(
        f"{settings['teams'][team_name]['current']}-{score_altered if score_altered else ''}{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
    )
    ch = await interaction.channel.clone(name=name)
    embed = create_tile_embed(
        tiles=settings["items"],
        tile_number=str(settings["teams"][team_name]["current"]),
    )
    await ch.send(embed=embed)
    await interaction.followup.send(
        f"## {dice_emoji} Team: {display_name} rolled:  {dice_emoji}  __**{roll}**__\
        \n## Congrats, your new tile is:  {green_square}  __**{settings['teams'][team_name]['current']}**__  {ch.mention}\
        \nYour previous tile was: {settings['teams'][team_name]['prev']}"
    )

    # Check if Sabotage Tile
    if settings['bot_mode']['current'] == 'candyland' and (sabotage := settings["items"][str(settings["teams"][team_name]["current"])].get("sabotage")):
        logger.info(f"Sabotage tile triggered: {sabotage}")
        async with _settings_lock:
            settings = load_settings_json()
            if "-" in sabotage:
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=settings["teams"][team_name]["current"] + int(sabotage),
                )
                await ch.send(
                    f"SABOTAGED: Go back to tile {settings['teams'][team_name]['current']}"
                )
            elif "reroll" in sabotage.lower():
                roll = roll_dice()
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=settings["teams"][team_name]["current"] + roll,
                )
                await ch.send(
                    f"SKIPPED: Goto tile {settings['teams'][team_name]['current']}"
                )
            else:
                await ch.send(f"SABOTAGED: Goto tile {sabotage}")
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=int(sabotage),
                )
            update_settings_json(settings)

        name = create_discord_friendly_name(
            f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
        )
        await interaction.channel.send(
            f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {display_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{name}"
        )

        ch = await interaction.channel.clone(name=name)
        embed = create_tile_embed(
            tiles=settings["items"],
            tile_number=str(settings["teams"][team_name]["current"]),
        )
        await ch.send(embed=embed)

    if settings['bot_mode']['current'] == 'candyland':
        await update_team_bingo_card_channel(interaction, team_name, roll, settings)

    await update_server_score_board_channel(interaction)


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
    await interaction.response.defer(thinking=True)
    async with _settings_lock:
        settings = load_settings_json()
        category_name = interaction.channel.category.name
        team_name = get_team_key_by_display_name(settings, category_name)
        if not team_name:
            await interaction.followup.send(
                f"Could not find a team matching category \"{category_name}\""
            )
            return
        display_name = get_team_display_name(settings, team_name)
        role_name = discord.utils.get(interaction.guild.roles, name=team_name)
        if (
            role_name not in interaction.user.roles
            or roll_channel not in interaction.channel.name
        ):
            await interaction.followup.send(
                f"Please ensure you have appropriate Team Role and are within your Team's #{roll_channel}"
            )
            return
        if not settings["running"] or not settings['rerolling']:
            await interaction.followup.send(
                "Rolling/Rerolling is not enabled, either wait till Start time or message @ Bingo Moderator if receiving this message in error."
            )
            return
        if not settings["teams"][team_name]["reroll"] > 0:
            await interaction.followup.send(f"NO MORE REROLLS MFER!")
            return
        name = create_discord_friendly_name(
            f"{settings['teams'][team_name]['current']}-{settings['items'][str(settings['teams'][team_name]['current'])]['name']}"
        )
        logger.info(f"Reroll for {team_name}: prev channel {name}")
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
            await interaction.followup.send(
                f'Congrats {discord.utils.get(interaction.guild.roles, name=team_name).mention} you have finished all your tiles! {discord.utils.get(interaction.guild.roles, name="Bingo Moderator").mention}'
            )
            return
        elif settings["teams"][team_name]["current"] > total_tiles:
            settings["teams"][team_name]["current"] = total_tiles
        update_settings_json(settings)

    title = formatted_title(settings, team_name)
    await interaction.followup.send(
        f"ReRolling Dice: {roll} for team: {display_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
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
    if sabotage := settings["items"][str(settings["teams"][team_name]["current"])].get("sabotage"):
        logger.info(f"Sabotage tile on reroll: {sabotage}")
        async with _settings_lock:
            settings = load_settings_json()
            if "-" in sabotage:
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=settings["teams"][team_name]["current"] + int(sabotage),
                )
                await ch.send(
                    f"SABOTAGED: Go back to tile {settings['teams'][team_name]['current']}"
                )
            elif "reroll" in sabotage.lower():
                roll = roll_dice()
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=settings["teams"][team_name]["current"] + roll,
                )
                await ch.send(
                    f"SKIPPED: Goto tile {settings['teams'][team_name]['current']}"
                )
            else:
                await ch.send(f"SABOTAGED: Goto tile {sabotage}")
                settings = update_roll_settings(
                    roll,
                    team_name,
                    settings,
                    prev=settings["teams"][team_name]["current"],
                    current=int(sabotage),
                )
            update_settings_json(settings)

        title = formatted_title(settings, team_name)
        await interaction.channel.send(
            f"\n{'SABOTAGED' if sabotage != 'reroll' else 'SKIPPED'}:\nRolling Dice: {roll} for team: {display_name}\nCongrats, your new tile is: {settings['teams'][team_name]['current']} and old tile was: {settings['teams'][team_name]['prev']}\n{title}"
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

    await update_team_bingo_card_channel(
        interaction, team_name, roll, settings, reroll=True
    )
    await update_server_score_board_channel(interaction)


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
    spreadsheet_id, gid = parse_sheet_url(sheet_link)
    if not spreadsheet_id:
        await interaction.followup.send(
            "That doesn't look like a Google Sheets link. Use the full URL, e.g. https://docs.google.com/spreadsheets/d/<id>/edit"
        )
        return
    rows = None
    if process_sheet:
        try:
            rows = await load_sheet(spreadsheet_id, gid)
        except SheetLoadError as e:
            await interaction.followup.send(f"Could not load the Google Sheet. Tiles were not changed.\n{e}")
            return
    async with edit_settings() as settings:
        settings["tiles"]["url"] = sheet_link
        settings["tiles"]["spreadsheet_id"] = spreadsheet_id
        if rows is not None:
            format_item_list(settings, rows)
        tile_count = len(settings["items"])
    if rows is None:
        await interaction.followup.send('Updated tiles "url" and "spreadsheet_id". Tiles were not processed.')
    else:
        await interaction.followup.send(
            f'Updated tiles "url", "items", and "spreadsheet_id". Loaded {tile_count} tile(s).'
        )


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
    await interaction.response.defer(thinking=True)
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    else:
        team_names = list(settings["teams"].keys())
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
    if spectator_role is None:
        await interaction.followup.send('No "spectator" role found in this server.')
        return
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    roles = [r for r in roles if r is not None]
    roles.append(spectator_role)
    if members.split()[:1] == ["@everyone"]:
        await process_all_spectators(interaction, roles, spectator_role, unassign)
        return
    member_ids, invalid = parse_member_ids(members)
    if not member_ids:
        await interaction.followup.send("Please @ each member to update.")
        return
    updated = 0
    for m_id in member_ids:
        try:
            mem = await interaction.guild.fetch_member(m_id)
        except discord.NotFound:
            invalid.append(f"<@{m_id}>")
            continue
        await mem.remove_roles(*roles)
        if not unassign:
            await mem.add_roles(spectator_role)
        updated += 1
    message = f'Role "spectator" {"added to" if not unassign else "removed from"} {updated} member(s)'
    if invalid:
        message += f"\nSkipped (not a member mention): {' '.join(invalid)}"
    await interaction.followup.send(message)


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
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    team_names = list(settings["teams"].keys())
    team_number = team_names.index(team_name) + 1
    current_role = discord.utils.get(
        interaction.guild.roles, name=f"Team {team_number}"
    )
    if current_role is None:
        await interaction.followup.send(f'No "Team {team_number}" role found in this server.')
        return
    roles = [discord.utils.get(interaction.guild.roles, name=rl) for rl in ROLES]
    roles = [r for r in roles if r is not None]
    member_ids, invalid = parse_member_ids(members)
    if not member_ids:
        await interaction.followup.send("Please @ each member to add to the team.")
        return
    added = 0
    for m_id in member_ids:
        try:
            mem = await interaction.guild.fetch_member(m_id)
        except discord.NotFound:
            invalid.append(f"<@{m_id}>")
            continue
        await mem.remove_roles(*roles)
        await mem.add_roles(current_role)
        added += 1
    await process_team_assignment_updates(interaction)
    message = f'Role "Team {team_number}" added to {added} member(s)'
    if invalid:
        message += f"\nSkipped (not a member mention): {' '.join(invalid)}"
    await interaction.followup.send(message)


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

    class Reroll(ModeratorView):
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
            if settings["teams"][team_name]["reroll"] <= 0:
                await interaction.response.send_message(
                    content="No Rerolls exist for that team.", ephemeral=True
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
                await update_server_score_board_channel(interaction)

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
            await update_server_score_board_channel(interaction)

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

    class DeleteConfirmation(ModeratorView):
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
            self.stop()
            await interaction.response.edit_message(
                embed=discord.Embed(
                    description=f'Delete of "{self.team_name}" cancelled by {interaction.user.display_name}. Nothing was modified.'
                ),
                view=None,
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
            self.stop()
            settings = load_settings_json()
            error = validate_team_name(self.team_name, settings)
            if error:
                await interaction.response.edit_message(
                    embed=discord.Embed(description=error), view=None
                )
                return
            # The category is named after the display name when one is set.
            display = get_team_display_name(settings, self.team_name)
            # Respond now; deleting channels can take longer than Discord's 3s limit.
            await interaction.response.edit_message(
                embed=discord.Embed(description=f'Deleting "{display}" channels...'),
                view=None,
            )
            num_deleted = 0
            cat = find_team_category(interaction.guild, settings, self.team_name)
            if cat is not None:
                for ch in cat.channels:
                    logger.info(f"Deleting channel: {ch}")
                    await ch.delete()
                    num_deleted += 1
                await cat.delete()
            logger.info(f"Deleted {num_deleted} Channels")

            # Reset the team's display name so it goes back to its team key.
            async with _settings_lock:
                settings = load_settings_json()
                settings["teams"][self.team_name]["display_name"] = ""
                save_settings_json(settings)

            if cat is None:
                result = f'No category named "{display}" found. No channels deleted.'
            else:
                result = f'Deleted "{display}" category and {num_deleted} channel(s).'
            if display != self.team_name:
                result += f'\nTeam name reset to "{self.team_name}".'
            await interaction.edit_original_response(
                embed=discord.Embed(description=result)
            )

    await interaction.response.send_message(
        embed=discord.Embed(description=f'Confirm Deletion of Team "{team_name}":'),
        view=DeleteConfirmation(team_name=team_name),
    )


@has_role("Bingo Moderator")
@app_commands.autocomplete(team_name=change_team_names_autocomplete)
@bot.tree.command(name="change_team_name", description=f"Change team display name and category.")
async def change_team_name(
    interaction: discord.Interaction, team_name: str, new_team_name: str
):
    """
    Changes the display name of a team and updates the corresponding Discord category.
    The internal team key (e.g., "Team 1") remains unchanged for stability.
    The display_name is used in scoreboards, messages, and as the Discord category name.

    Parameters:
    - interaction (discord.Interaction): The interaction object representing the command invocation.
    - team_name (str): The current team key or display name.
    - new_team_name (str): The new display name for the team.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    if not new_team_name:
        await interaction.followup.send(f'No "new_team_name" provided, Please try again')
        return
    async with _settings_lock:
        settings = load_settings_json()
        # Resolve the internal team key from the provided name (could be key or display_name)
        team_key = get_team_key_by_display_name(settings, team_name)
        if not team_key:
            team_names = list(settings["teams"].keys())
            await interaction.followup.send(
                f"Team Name: {team_name} is not found in {team_names}\nPlease Try again"
            )
            return
        old_display = get_team_display_name(settings, team_key)
        # Find the category by the current display name
        team_cat = discord.utils.get(interaction.guild.categories, name=old_display)
        if not team_cat:
            await interaction.followup.send(f'No Category found for "{old_display}"')
            return
        # Update display_name in settings (internal key stays the same)
        settings["teams"][team_key]["display_name"] = new_team_name
        save_settings_json(settings)
    # Update the Discord category name
    await team_cat.edit(name=new_team_name)
    await interaction.followup.send(
        f'Changed Team "{old_display}" ({team_key}) display name to "{new_team_name}"'
    )


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
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    if settings["bot_mode"]["current"] != "normal":
        await interaction.followup.send(
            f"This command only works when Bot is in mode 'normal'. Current Mode: {settings['bot_mode']['current']}"
        )
        return
    channels = await get_default_channels(interaction)
    if not channels:
        # get_default_channels already told the user the tiles are missing
        return
    display = get_team_display_name(settings, team_name)
    cat = find_team_category(interaction.guild, settings, team_name)
    if cat is None:
        await interaction.followup.send(f'No category found for "{display}".')
        return
    channel_details_by_name = {x["name"]: x for x in channels}
    updated_num = 0
    for ch in cat.text_channels:
        channel_details = channel_details_by_name.get(ch.name)
        if not channel_details or not channel_details["description"]:
            continue
        # The tile description is the first message the bot posted in the channel.
        async for message in ch.history(limit=1, oldest_first=True):
            if message.author == bot.user and channel_details["description"] != message.content:
                await ch.edit(topic=channel_details["description"])
                await message.edit(content=f"{channel_details['description']}")
                updated_num += 1
    await interaction.followup.send(
        f"Updated {display}'s channels Tiles. {updated_num} channel(s) tiles updated."
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
    await interaction.response.defer(thinking=True)
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    team_names = list(settings["teams"].keys())
    team_number = team_names.index(team_name) + 1
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
                channel_name = f"{team_number}-general-{channel_name}"
                overwrites = overwrites_w_out_spectator
            else:
                overwrites = overwrites_with_spectator
        if "voice" in channel_name:
            channel_name = f"{team_number}-{channel_name}"
            chan = await interaction.guild.create_voice_channel(
                name=channel_name, category=cat, overwrites=overwrites
            )
        else:
            description = channel["description"]
            await create_discord_text_channel(interaction, channel_name, description, cat, overwrites)
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
    if tile < 0:
        tile = 1
    # Goes through the score log so /score history and /score undo include it.
    await _change_score(interaction, team_name, set_to=tile, reason="/set_tile", kind="set")


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
    await interaction.response.defer(thinking=True)
    if tile < 0:
        tile = None
    async with edit_settings() as settings:
        error = validate_team_name(team_name, settings)
        if not error:
            settings["teams"][team_name]["prev"] = tile
    if error:
        await interaction.followup.send(error)
        return
    await interaction.followup.send(
        f"Updated prev tile for Team: {team_name} to {tile}"
    )


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
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.response.send_message(error)
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
    # Defer first: building the chutes and ladders board can take longer than 3s.
    await interaction.response.defer(thinking=True)
    error = await update_server_score_board_channel(interaction=interaction)
    await interaction.followup.send(error or "Updated!")




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
    tile_list_ch = discord.utils.get(interaction.guild.text_channels, name="tile-list")
    if tile_list_ch is None:
        await interaction.followup.send("No #tile-list channel found.")
        return

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

    class ToggleRolling(ModeratorView):
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
@bot.tree.command(name="brief_teams_channels",
    description=f"Toggles the brief teams channels setting. Prevents tiles from being posted in team categories.")
async def brief_teams_channels(interaction: discord.Interaction):
    """
    Toggles the brief teams channels setting and sends a response indicating the new status.

    Parameters:
    interaction (discord.Interaction): The interaction object representing the user's interaction with the bot.

    Returns:
    None
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    if settings.get("brief_teams_channels", False):
        settings["brief_teams_channels"] = False
    else:
        settings["brief_teams_channels"] = True
    save_settings_json(settings)
    await interaction.followup.send(
        f"Brief teams channels are now {'ENABLED' if settings['brief_teams_channels'] else 'DISABLED'}."
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
    Marks a tile as completed for a specific team, adds its points (and any
    line or blackout bonus), and updates the Bingo Card and #score-board.

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
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    parsed = parse_table_location(location)
    if parsed is None:
        await interaction.followup.send(
            f'"{location}" is not a valid tile. Use a column A-E and a row 1-5, e.g. "A1".'
        )
        return
    row, col = parsed
    await interaction.followup.send(
        await set_tile_completion(interaction, team_name, row, col, completed=True)
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
    team_names = list(settings["teams"].keys())
    if for_all_teams or team_name is None:
        targets = team_names[: settings["total_teams"]]
    else:
        error = validate_team_name(team_name, settings)
        if error:
            await interaction.followup.send(error)
            return
        targets = [team_name]
    posted, problems = [], []
    for target in targets:
        error = await post_or_update_bingo_card(interaction, settings, target)
        if error:
            problems.append(error)
        else:
            posted.append(get_team_display_name(settings, target))
    message = f"Posted Bingo Card image in {', '.join(posted) or 'no'} Bingo Card Channel(s)"
    if problems:
        message += "\n" + "\n".join(problems)
    await interaction.followup.send(message)


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
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    error = await post_or_update_bingo_card(interaction, settings, team_name)
    if error:
        await interaction.followup.send(error)
        return
    await interaction.followup.send(
        f"Posted Bingo Card image in {get_team_display_name(settings, team_name)}'s Bingo Card Channel"
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
    await interaction.response.defer(thinking=True)
    if not file:
        await interaction.followup.send(
            f"Please attach an image to set as the default Bingo Card Image"
        )
        return
    async with edit_settings() as settings:
        # check game style
        if settings["bot_mode"]["current"] == "chutes and ladders":
            image_path = os.path.join(IMAGE_TEMPLATE_PATH, "bingo_card_image.png")
            settings["board_template"] = image_path
        else:
            image_path = os.path.join(IMAGE_PATH, "bingo_card_image.png")
            # update all settings['teams'][team_name]['image']
            for team_name in settings["teams"]:
                settings["teams"][team_name]["image"] = image_path
        # download attachment
        with open(image_path, "wb") as f:
            await file.save(f)
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
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
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
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    team_names = [x for x in settings["teams"].keys()]
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
    logger.info("sync command")
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
    if not start_here_channel or not rules_accepted_role:
        await interaction.followup.send(
            "Server closed but could not find start-here channel or Rules Accepted role to update permissions."
        )
        return
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
    if total_teams < 1 or total_teams > MAX_TEAMS:
        await interaction.followup.send(
            f"Number of active teams must be between 1 and {MAX_TEAMS}"
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

    class ConfirmReset(ModeratorView):
        def __init__(self, *, timeout: Optional[float] = 180):
            super().__init__(timeout=timeout)

        @discord.ui.button(label="Don't Reset", style=discord.ButtonStyle.danger)
        async def abort_reset(
            self, interaction: discord.Interaction,
            button: discord.ui.Button
        ):
            await interaction.response.edit_message(
                content=None,
                embed=discord.Embed(
                    description=f"Reset cancelled by {interaction.user.display_name}. Nothing was modified."
                ),
                view=None,
            )

        @discord.ui.button(label="Reset", style=discord.ButtonStyle.green)
        async def reset_settings(
            self, interaction: discord.Interaction,
            button: discord.ui.Button
        ):
            async with _settings_lock:
                try:
                    renamed = _reset_all_settings()
                except OSError as e:
                    await interaction.response.edit_message(
                        content=None,
                        embed=discord.Embed(description=f"Failed to reset settings: {e}"),
                        view=None,
                    )
                    return
            # Respond now; renaming categories can take longer than Discord's 3s limit.
            await interaction.response.edit_message(
                content=None,
                embed=discord.Embed(description="Resetting team scores and names..."),
                view=None,
            )
            # Rename team categories back to their default names (Team 1..Team N).
            problems = []
            for team_key, old_name in renamed.items():
                cat = discord.utils.get(interaction.guild.categories, name=old_name)
                if not cat:
                    problems.append(f'No category named "{old_name}" for {team_key}')
                    continue
                try:
                    await cat.edit(name=team_key)
                except discord.HTTPException as e:
                    logger.error(f'Failed to rename category "{old_name}" to "{team_key}": {e}')
                    problems.append(f'Could not rename "{old_name}" to "{team_key}": {e}')
            description = (
                f"All team scores, settings and team names were reset by "
                f"{interaction.user.display_name}."
            )
            if problems:
                description += "\n\n" + "\n".join(problems)
            await interaction.edit_original_response(
                embed=discord.Embed(description=description)
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
                content = generate_team_assignment_text(all_roles, total_teams, settings)
                await m.edit(content=content)
                break
        else:
            content = generate_team_assignment_text(all_roles, total_teams, settings)
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





# ======================================= Score Commands ====================================================


async def set_tile_completion(
    interaction: discord.Interaction, team_name: str, row: int, column: int, *, completed: bool, reason: str = ""
) -> str:
    """
    Mark or unmark a normal mode tile, update the score, bingo card,
    #score-board and team chat.

    Returns:
        str: The message to show the moderator.
    """
    by = interaction.user.display_name
    card_error = None
    async with edit_settings() as settings:
        if completed:
            entries = complete_tile(settings, team_name, row, column, by=by, reason=reason)
        else:
            entries = uncomplete_tile(settings, team_name, row, column, by=by)
        if entries is not None:
            try:
                render_team_card(settings, team_name)
            except (OSError, ValueError) as e:
                logger.error(f"Failed to draw bingo card for {team_name}: {e}")
                card_error = f"Bingo card image could not be drawn: {e}"
    display = get_team_display_name(settings, team_name)
    label = describe_location(settings, row, column)
    if entries is None:
        return f"{display}'s tile {label} is {'already' if completed else 'not'} marked as completed."
    problems = await publish_score_change(interaction, team_name, entries, card_changed=card_error is None)
    if card_error:
        problems.insert(0, card_error)
    total = sum(e["delta"] for e in entries)
    message = (
        f"{'Marked' if completed else 'Unmarked'} {display}'s tile {label}: "
        f"{total:+d} pts, score is now {entries[-1]['after']}."
    )
    return "\n".join([message] + problems)


async def _change_score(
    interaction: discord.Interaction,
    team_name: str,
    *,
    delta: int = 0,
    set_to: Optional[int] = None,
    reason: str,
    kind: str = "manual",
) -> None:
    """Shared body of /score add, /score remove, /score set and /set_tile."""
    await interaction.response.defer(thinking=True)
    entry = None
    async with edit_settings() as settings:
        error = validate_team_name(team_name, settings)
        if not error:
            entry = apply_score_change(
                settings, team_name, delta=delta, set_to=set_to,
                reason=reason, by=interaction.user.display_name, kind=kind,
            )
    if error:
        await interaction.followup.send(error)
        return
    problems = await publish_score_change(interaction, team_name, [entry])
    lines = [format_score_entries(settings, team_name, [entry])]
    requested = set_to if set_to is not None else entry["before"] + delta
    if requested != entry["after"]:
        lines.append(f"Score was limited to {entry['after']} (it can't go below 0{' or past the last tile' if is_board_mode(settings) else ''}).")
    if is_board_mode(settings):
        lines.append("In this mode the score is the team's tile. No tile channel was created.")
    await interaction.followup.send("\n".join(lines + problems))


score_group = app_commands.Group(
    name="score", description="Change and review team scores.", guild_only=True
)


@score_group.command(name="add", description="Add points to a team. In candyland/chutes and ladders this moves the team forward.")
@app_commands.describe(points="Points to add", reason="Why, shown to the team and in /score history")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role(MODERATOR_ROLE)
async def score_add(
    interaction: discord.Interaction,
    team_name: str,
    points: app_commands.Range[int, 1, 100000],
    reason: Optional[str] = None,
):
    """Add points to a team's score."""
    await _change_score(interaction, team_name, delta=points, reason=reason or "Added by moderator")


@score_group.command(name="remove", description="Remove points from a team. In candyland/chutes and ladders this moves the team back.")
@app_commands.describe(points="Points to remove", reason="Why, shown to the team and in /score history")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role(MODERATOR_ROLE)
async def score_remove(
    interaction: discord.Interaction,
    team_name: str,
    points: app_commands.Range[int, 1, 100000],
    reason: Optional[str] = None,
):
    """Remove points from a team's score."""
    await _change_score(interaction, team_name, delta=-points, reason=reason or "Removed by moderator")


@score_group.command(name="set", description="Set a team's score. In candyland/chutes and ladders this sets the team's tile.")
@app_commands.describe(points="The new score", reason="Why, shown to the team and in /score history")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role(MODERATOR_ROLE)
async def score_set(
    interaction: discord.Interaction,
    team_name: str,
    points: app_commands.Range[int, 0, 100000],
    reason: Optional[str] = None,
):
    """Set a team's score."""
    await _change_score(interaction, team_name, set_to=points, reason=reason or "Set by moderator", kind="set")


@score_group.command(name="undo", description="Undo a team's last score change, including tile marks and their bonuses.")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role(MODERATOR_ROLE)
async def score_undo(interaction: discord.Interaction, team_name: str):
    """Undo a team's most recent score change."""
    await interaction.response.defer(thinking=True)
    undone, new_entries = [], []
    card_changed = False
    card_error = None
    async with edit_settings() as settings:
        error = validate_team_name(team_name, settings)
        if not error:
            undone, new_entries = undo_last_score_change(settings, team_name, by=interaction.user.display_name)
            if any(e["kind"] == "tile" for e in undone) and not is_board_mode(settings):
                try:
                    render_team_card(settings, team_name)
                    card_changed = True
                except (OSError, ValueError) as e:
                    card_error = f"Bingo card image could not be drawn: {e}"
    if error:
        await interaction.followup.send(error)
        return
    if not undone:
        await interaction.followup.send(f"{get_team_display_name(settings, team_name)} has no score changes to undo.")
        return
    problems = await publish_score_change(interaction, team_name, new_entries, card_changed=card_changed)
    if card_error:
        problems.insert(0, card_error)
    await interaction.followup.send("\n".join([format_score_entries(settings, team_name, new_entries)] + problems))


@score_group.command(name="history", description="Show a team's recent score changes.")
@app_commands.describe(count="How many changes to show")
@app_commands.autocomplete(team_name=team_names_autocomplete)
@has_role(MODERATOR_ROLE)
async def score_history(
    interaction: discord.Interaction,
    team_name: str,
    count: app_commands.Range[int, 1, 25] = 10,
):
    """Show a team's score log, newest first. Undone changes are struck through."""
    settings = load_settings_json()
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    team = settings["teams"][team_name]
    log = team.get("score_log", [])[-count:]
    lines = []
    for e in reversed(log):
        line = f"`#{e['id']}` {e['delta']:+d} -> {e['after']} | {e['reason'][:80]} | {e['by']} | <t:{e['at']}:R>"
        if e.get("undone"):
            line = f"~~{line}~~"
        lines.append(line)
    embed = discord.Embed(
        title=f"{get_team_display_name(settings, team_name)} score history (now {team.get('current') or 0})",
        description="\n".join(lines) or "No score changes yet.",
        color=0xF7E302,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@score_group.command(name="config", description="View or change tile points, line/blackout bonuses and approvals needed.")
@app_commands.describe(
    default_tile_points="Points for a tile when the sheet has no points column value",
    line_bonus="Extra points for each completed row, column or diagonal (0 = off)",
    blackout_bonus="Extra points for completing every tile (0 = off)",
    approvals_required="Different moderators needed to approve a /submit",
)
@has_role(MODERATOR_ROLE)
async def score_config(
    interaction: discord.Interaction,
    default_tile_points: Optional[app_commands.Range[int, 0, 10000]] = None,
    line_bonus: Optional[app_commands.Range[int, 0, 10000]] = None,
    blackout_bonus: Optional[app_commands.Range[int, 0, 10000]] = None,
    approvals_required: Optional[app_commands.Range[int, 1, 5]] = None,
):
    """Show the scoring settings, changing any that were given."""
    changes = {
        "default_tile_points": default_tile_points,
        "line_bonus": line_bonus,
        "blackout_bonus": blackout_bonus,
        "approvals_required": approvals_required,
    }
    changes = {k: v for k, v in changes.items() if v is not None}
    async with edit_settings() as settings:
        scoring = get_scoring(settings)
        scoring.update(changes)
        settings["scoring"] = scoring
    lines = [f"{'Updated scoring' if changes else 'Scoring'} settings:"]
    lines += [f"- {k}: {v}" for k, v in scoring.items()]
    if changes:
        lines.append("Changes apply to tiles marked from now on. Existing scores are not recalculated.")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


bot.tree.add_command(score_group)


@has_role(MODERATOR_ROLE)
@app_commands.autocomplete(team_name=team_names_autocomplete)
@bot.tree.command(name="unmark_tile_completed",
    description="Unmark a completed tile on the bingo board and take back its points. 'A1' for example.")
async def unmark_tile_completed(interaction: discord.Interaction, team_name: str, location: str):
    """
    Unmarks a completed tile for a team, removes its points (and any line or
    blackout bonus it was part of) and redraws the Bingo Card.
    """
    await interaction.response.defer(thinking=True)
    settings = load_settings_json()
    if settings['bot_mode']['current'] != "normal":
        await interaction.followup.send(f"This command only works when Bot is in mode 'normal'. Current Mode: {settings['bot_mode']['current']}")
        return
    error = validate_team_name(team_name, settings)
    if error:
        await interaction.followup.send(error)
        return
    parsed = parse_table_location(location)
    if parsed is None:
        await interaction.followup.send(
            f'"{location}" is not a valid tile. Use a column A-E and a row 1-5, e.g. "A1".'
        )
        return
    row, col = parsed
    await interaction.followup.send(
        await set_tile_completion(interaction, team_name, row, col, completed=False)
    )


# ======================================= Submissions ====================================================


def is_moderator(user) -> bool:
    """True if the member has the Bingo Moderator role."""
    return discord.utils.get(getattr(user, "roles", []), name=MODERATOR_ROLE) is not None


def get_submissions(settings: dict) -> dict:
    """settings["submissions"], created for older settings.json files."""
    return settings.setdefault("submissions", {"next_id": 1, "items": {}})


def channel_slug(text: str) -> str:
    """Normalise a channel or tile name for comparison, e.g. "Zulrah's Pet!" -> "zulrah-s-pet"."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def submission_tile_label(settings: dict, tile_key: str) -> str:
    """Label for a submitted tile: "A1 Zulrah" in normal mode, "Tile 12 Zulrah" in board modes."""
    item = settings.get("items", {}).get(str(tile_key), {})
    if is_board_mode(settings):
        return f"Tile {tile_key}{' ' + item['name'] if item.get('name') else ''}"
    location = location_for_tile_key(tile_key)
    return describe_location(settings, *location) if location else f"Tile {tile_key}"


def resolve_submission_tile(settings: dict, channel_name: str, tile_arg: Optional[str]) -> (Optional[str], Optional[str]):
    """
    Work out which tile a /submit is for: the tile argument if given,
    otherwise the channel it was used in.

    Returns:
        tuple: (tile key, None) or (None, error message)
    """
    items = settings.get("items", {})
    if not items:
        return None, "No tiles are loaded. A moderator needs to run /upload_tiles."
    if tile_arg:
        tile_arg = tile_arg.strip()
        if not is_board_mode(settings):
            parsed = parse_table_location(tile_arg)
            if parsed:
                return tile_key_for_location(*parsed), None
        if tile_arg.isdigit() and tile_arg in items:
            if not is_board_mode(settings) and location_for_tile_key(tile_arg) is None:
                return None, f"Tile {tile_arg} is not on the 5x5 board."
            return tile_arg, None
        hint = "a tile number" if is_board_mode(settings) else "a location A1-E5"
        return None, f'"{tile_arg}" is not a tile. Use {hint}.'
    if is_board_mode(settings):
        # Rolled tile channels are named "<tile>-<name>"
        match = re.match(r"^(\d+)-", channel_name)
        if match and match.group(1) in items:
            return match.group(1), None
    else:
        slug = channel_slug(channel_name)
        for key, item in items.items():
            if item.get("name") and channel_slug(create_discord_friendly_name(item["name"])) == slug:
                if location_for_tile_key(key) is None:
                    return None, f"Tile {key} is not on the 5x5 board."
                return key, None
    return None, "Use /submit in the tile's channel, or say which tile with the tile option."


SUBMISSION_COLORS = {"pending": 0xF7E302, "approved": 0x2ECC71, "rejected": 0xE74C3C}


def build_submission_embed(settings: dict, sub: dict) -> discord.Embed:
    """The review message embed for a submission."""
    required = get_scoring(settings)["approvals_required"]
    embed = discord.Embed(
        title=f"Submission #{sub['id']}: {get_team_display_name(settings, sub['team'])} - {submission_tile_label(settings, sub['tile'])}",
        description=sub.get("note") or None,
        color=SUBMISSION_COLORS.get(sub["status"], 0xF7E302),
        timestamp=datetime.datetime.fromtimestamp(sub["created_at"], datetime.timezone.utc),
    )
    if sub["status"] == "pending":
        status = f"Pending ({len(sub['approvers'])}/{required} approvals)"
        if sub["approvers"]:
            status += f": {', '.join(sub['approvers'])}"
    elif sub["status"] == "approved":
        status = f"Approved by {', '.join(sub['approvers'])}"
        if sub.get("result"):
            status += f"\n{sub['result']}"
    else:
        status = f"Rejected by {sub.get('rejected_by', 'a moderator')}"
        if sub.get("reason"):
            status += f": {sub['reason']}"
    embed.add_field(name="Status", value=status[:1024], inline=False)
    embed.add_field(name="Submitted by", value=f"<@{sub['submitter_id']}>")
    embed.add_field(name="Channel", value=f"<#{sub['channel_id']}>")
    embed.set_image(url=f"attachment://{sub['filename']}")
    return embed


class SubmissionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"bingo:submission:(?P<action>approve|reject):(?P<id>\d+)",
):
    """
    Approve/Reject button on a submission review message. The submission ID is
    in the custom_id, so the buttons keep working after the bot restarts.
    """

    def __init__(self, action: str, submission_id: int):
        approve = action == "approve"
        super().__init__(
            discord.ui.Button(
                label="Approve" if approve else "Reject",
                style=discord.ButtonStyle.green if approve else discord.ButtonStyle.danger,
                custom_id=f"bingo:submission:{action}:{submission_id}",
            )
        )
        self.action = action
        self.submission_id = submission_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match, /):
        return cls(match["action"], int(match["id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_moderator(interaction.user):
            return True
        await interaction.response.send_message(
            f"Only a {MODERATOR_ROLE} can review submissions.", ephemeral=True
        )
        return False

    async def callback(self, interaction: discord.Interaction):
        if self.action == "approve":
            await approve_submission(interaction, self.submission_id)
        else:
            await interaction.response.send_modal(RejectSubmissionModal(self.submission_id))


def submission_view(submission_id: int) -> discord.ui.View:
    """The Approve/Reject buttons for a pending submission."""
    view = discord.ui.View(timeout=None)
    view.add_item(SubmissionButton("approve", submission_id))
    view.add_item(SubmissionButton("reject", submission_id))
    return view


class RejectSubmissionModal(discord.ui.Modal):
    """Asks the moderator why a submission is rejected."""

    reason = discord.ui.TextInput(
        label="Reason (shown to the team)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, submission_id: int):
        super().__init__(title=f"Reject submission #{submission_id}")
        self.submission_id = submission_id

    async def on_submit(self, interaction: discord.Interaction):
        await reject_submission(interaction, self.submission_id, (self.reason.value or "").strip())


async def notify_submitter(sub: dict, text: str) -> None:
    """Tell the submitter about a decision in the channel they submitted from."""
    channel = bot.get_channel(sub["channel_id"])
    if channel is None:
        return
    try:
        await channel.send(f"<@{sub['submitter_id']}> {text}")
    except discord.HTTPException as e:
        logger.error(f"Failed to notify submitter of #{sub['id']}: {e}")


async def approve_submission(interaction: discord.Interaction, submission_id: int) -> None:
    """
    Add the moderator's approval. Once enough different moderators approve,
    mark the tile completed (normal mode: points, bonuses and bingo card) and
    tell the team.
    """
    by = interaction.user.display_name
    entries = []
    card_error = None
    async with edit_settings() as settings:
        sub = get_submissions(settings)["items"].get(str(submission_id))
        if sub is None:
            outcome = "This submission no longer exists (the bingo may have been reset)."
        elif sub["status"] != "pending":
            outcome = f"This submission was already {sub['status']}."
        elif interaction.user.id == sub["submitter_id"]:
            outcome = "You can't approve your own submission."
        elif interaction.user.id in sub["approver_ids"]:
            outcome = "You already approved this submission. It needs a different moderator."
        else:
            outcome = None
            sub["approver_ids"].append(interaction.user.id)
            sub["approvers"].append(by)
            if len(sub["approver_ids"]) >= get_scoring(settings)["approvals_required"]:
                sub["status"] = "approved"
                team = settings["teams"][sub["team"]]
                if is_board_mode(settings):
                    done = team.setdefault("board_tiles_completed", [])
                    if int(sub["tile"]) not in done:
                        done.append(int(sub["tile"]))
                    sub["result"] = "Tile recorded as completed."
                else:
                    row, col = location_for_tile_key(sub["tile"])
                    entries = complete_tile(
                        settings, sub["team"], row, col, by=by, reason=f"submission #{submission_id}"
                    )
                    if entries is None:
                        entries = []
                        sub["result"] = "The tile was already completed, so no points were added."
                    else:
                        sub["result"] = f"{sum(e['delta'] for e in entries):+d} pts"
                        try:
                            render_team_card(settings, sub["team"])
                        except (OSError, ValueError) as e:
                            logger.error(f"Failed to draw bingo card for {sub['team']}: {e}")
                            card_error = f"Bingo card image could not be drawn: {e}"
    if outcome:
        await interaction.response.send_message(outcome, ephemeral=True)
        return
    approved = sub["status"] == "approved"
    await interaction.response.edit_message(
        embed=build_submission_embed(settings, sub),
        view=None if approved else submission_view(submission_id),
    )
    if not approved:
        return
    problems = [card_error] if card_error else []
    if entries:
        problems += await publish_score_change(interaction, sub["team"], entries, card_changed=card_error is None)
    else:
        await announce_to_team(
            interaction.guild, settings, sub["team"],
            f"Submission #{submission_id} for {submission_tile_label(settings, sub['tile'])} was approved.",
        )
    await notify_submitter(
        sub, f"Submission #{submission_id} for {submission_tile_label(settings, sub['tile'])} was approved. {sub.get('result', '')}"
    )
    if problems:
        await interaction.followup.send("\n".join(problems), ephemeral=True)


async def reject_submission(interaction: discord.Interaction, submission_id: int, reason: str) -> None:
    """Reject a pending submission and tell the submitter why."""
    async with edit_settings() as settings:
        sub = get_submissions(settings)["items"].get(str(submission_id))
        if sub is None:
            outcome = "This submission no longer exists (the bingo may have been reset)."
        elif sub["status"] != "pending":
            outcome = f"This submission was already {sub['status']}."
        else:
            outcome = None
            sub["status"] = "rejected"
            sub["rejected_by"] = interaction.user.display_name
            sub["reason"] = reason
    if outcome:
        await interaction.response.send_message(outcome, ephemeral=True)
        return
    await interaction.response.edit_message(embed=build_submission_embed(settings, sub), view=None)
    await notify_submitter(
        sub,
        f"Submission #{submission_id} for {submission_tile_label(settings, sub['tile'])} was rejected"
        f"{': ' + reason if reason else '.'}",
    )


PROOF_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


@bot.tree.command(name="submit", description="Submit a screenshot showing your team completed a tile, for moderators to approve.")
@app_commands.describe(
    proof="Screenshot showing the tile is completed",
    tile="Only needed outside the tile's channel: A1-E5, or the tile number in candyland/chutes and ladders",
    note="Anything the moderators should know",
)
@app_commands.guild_only()
async def submit(
    interaction: discord.Interaction,
    proof: discord.Attachment,
    tile: Optional[str] = None,
    note: Optional[str] = None,
):
    """
    Sends a tile completion to the review channel (#submissions, or
    #bot-commands) with Approve/Reject buttons for Bingo Moderators.
    Must be used in one of the team's channels by a member of the team.
    """
    if not (proof.content_type or "").startswith("image/"):
        await interaction.response.send_message("Please attach an image as proof.", ephemeral=True)
        return
    settings = load_settings_json()
    category = getattr(interaction.channel, "category", None)
    team_name = get_team_key_by_display_name(settings, category.name) if category else None
    if not team_name:
        await interaction.response.send_message("Use /submit in one of your team's channels.", ephemeral=True)
        return
    team_role = discord.utils.get(interaction.guild.roles, name=team_name)
    if team_role not in getattr(interaction.user, "roles", []) and not is_moderator(interaction.user):
        await interaction.response.send_message("Only members of this team can submit for it.", ephemeral=True)
        return
    tile_key, error = resolve_submission_tile(settings, interaction.channel.name, tile)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return
    label = submission_tile_label(settings, tile_key)
    if not is_board_mode(settings):
        if list(location_for_tile_key(tile_key)) in settings["teams"][team_name].get("tiles_completed", []):
            await interaction.response.send_message(f"{label} is already completed for your team.", ephemeral=True)
            return
    for existing in get_submissions(settings)["items"].values():
        if existing["team"] == team_name and existing["tile"] == tile_key and existing["status"] == "pending":
            await interaction.response.send_message(
                f"{label} already has a pending submission (#{existing['id']}).", ephemeral=True
            )
            return
    review_channel = discord.utils.get(interaction.guild.text_channels, name=SUBMISSIONS_CHANNEL) or discord.utils.get(
        interaction.guild.text_channels, name=mod_channel
    )
    if review_channel is None:
        await interaction.response.send_message(
            f"No #{SUBMISSIONS_CHANNEL} or #{mod_channel} channel to send submissions to. Ask a moderator.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)
    ext = os.path.splitext(proof.filename)[1].lower()
    filename = f"proof{ext if ext in PROOF_EXTENSIONS else '.png'}"
    file = await proof.to_file(filename=filename)
    async with edit_settings() as settings:
        submissions = get_submissions(settings)
        submission_id = submissions["next_id"]
        submissions["next_id"] += 1
        sub = {
            "id": submission_id,
            "team": team_name,
            "tile": tile_key,
            "submitter_id": interaction.user.id,
            "submitter": interaction.user.display_name,
            "channel_id": interaction.channel.id,
            "note": (note or "")[:1000],
            "filename": filename,
            "status": "pending",
            "approver_ids": [],
            "approvers": [],
            "created_at": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        }
        submissions["items"][str(submission_id)] = sub
    try:
        message = await review_channel.send(
            embed=build_submission_embed(settings, sub), file=file, view=submission_view(submission_id)
        )
    except discord.HTTPException as e:
        async with edit_settings() as settings:
            get_submissions(settings)["items"].pop(str(submission_id), None)
        await interaction.followup.send(f"Could not send the submission for review: {e}")
        return
    async with edit_settings() as settings:
        saved = get_submissions(settings)["items"].get(str(submission_id))
        if saved is not None:
            saved["review_channel_id"] = review_channel.id
            saved["review_message_id"] = message.id
    await interaction.followup.send(
        f"Submitted #{submission_id} for {label}. A {MODERATOR_ROLE} will review it."
    )


@has_role(MODERATOR_ROLE)
@bot.tree.command(name="pending_submissions", description="List tile submissions waiting for review.")
async def pending_submissions(interaction: discord.Interaction):
    """Lists pending submissions with links to their review messages."""
    settings = load_settings_json()
    lines = []
    for sub in get_submissions(settings)["items"].values():
        if sub["status"] != "pending":
            continue
        line = f"#{sub['id']} {get_team_display_name(settings, sub['team'])} - {submission_tile_label(settings, sub['tile'])} by {sub['submitter']}"
        if sub.get("review_message_id"):
            line += f" [review](https://discord.com/channels/{interaction.guild.id}/{sub['review_channel_id']}/{sub['review_message_id']})"
        lines.append(line)
    text = "\n".join(lines) or "No submissions are waiting for review."
    await interaction.response.send_message(text[:2000], ephemeral=True)


async def _setup_hook():
    # Lets submission buttons sent before a restart keep working.
    bot.add_dynamic_items(SubmissionButton)


bot.setup_hook = _setup_hook


if __name__ == '__main__':
    logger.info('About to log in with bot')
    bot.run(config.DISCORD_BOT_TOKEN)

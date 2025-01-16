import json
import datetime
import math
from PIL import Image, ImageDraw
from bot import *

settings1 = {
    "bot_mode": {
        "bot_options": [
            "candyland",
            "normal",
            "chutes and ladders" 
        ],
        "current": "normal"
    },
    "tiles": {
        "url": "https://docs.google.com/spreadsheets/d/1rYlZF3dHTKQZTPGMbV77tulP07hU-6WLvHw26F9FFsE/edit?usp=sharing",
        "spreadsheet_id": "1rYlZF3dHTKQZTPGMbV77tulP07hU-6WLvHw26F9FFsE",
        "items": {}
    },
    "running": True,
    "rerolling": True,
    "total_teams": 7,
    "teams": {
        "Team 1": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/home/benerman/github/OSRS-Bingo-Discord-Bot/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "Team 2": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/app/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "Team 3": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/app/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "Team 4": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/app/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "Team 5": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/app/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "Team 6": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/app/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "Team 7": {
            "current": 0,
            "prev": 0,
            "reroll": 0,
            "roll_history": [],
            "image": "/app/images/bingo_card_image.png",
            "board": "/home/benerman/github/OSRS-Bingo-Discord-Bot/template_images/bingo_card_image.png",
            "tiles_completed": []
        },
        "image_bounds": {
                "x_offset": 52,
                "y_offset": 35,
                "x_right_offset": 52,
                "y_bottom_offset": 100,
                "x": 0,
                "y": 0,
                "gutter": 15
        },
        "board_bounds": {
            "tile_count": 100,
            "tile_size": 100,
            "team_icon_x_offset": 6,
            "team_icon_y_offset": 6,
            "x_offset": 5,
            "y_offset": 5,
            "x_right_offset": 5,
            "y_bottom_offset": 5,
            "x": 0,
            "y": 0,
            "gutter": 4
        }
    },
    "items": {
        "1": {
            "name": "Skotizo Unique",
            "desc": "Skotizo unique - Jar, Claw, Pet, Onyx, Full totem, Basically anything on Skotizo Log but Ancient Shard",
            "discord_name": "Skotizo Unique - Skotizo unique - Jar, Claw, Pet, Onyx, Full totem, Basically anything on Skotizo Log but Ancient Shard"
        },
        "2": {
            "name": "25m Drop",
            "desc": "Boost yer stonks with a juicy drop. Receive a drop in chat that exceeds 25mil",
            "discord_name": "25m Drop - Boost yer stonks with a juicy drop. Receive a drop in chat that exceeds 25mil"
        },
        "3": {
            "name": "GM Tasks",
            "desc": "1 gm speed time, 1 gm mechanical, 1 perfection, 1 restriction, 1 stamina. - 1 of each gm task minus kc.",
            "discord_name": "GM Tasks - 1 gm speed time, 1 gm mechanical, 1 perfection, 1 restriction, 1 stamina. - 1 of each gm task minus kc."
        },
        "4": {
            "name": "Clue Boot",
            "desc": "Any clue boot from Medium clues",
            "discord_name": "Clue Boot - Any clue boot from Medium clues"
        },
        "5": {
            "name": "Nex Unique",
            "desc": "Any Nex Unique - Hilt, Armor, Nihil horn, Pet",
            "discord_name": "Nex Unique - Any Nex Unique - Hilt, Armor, Nihil horn, Pet"
        },
        "6": {
            "name": "Raid Armor",
            "desc": "Any raids clothing item (head, body, legs).",
            "discord_name": "Raid Armor - Any raid clothing item (head, body, legs)."
        },
        "7": {
            "name": "Rev Uniques",
            "desc": "Rev weapon or 16m gp worth of totems. Rev boss guaranteed drops do not count.",
            "discord_name": "Rev Uniques - Rev weapon or 16m gp worth of totems. Rev boss guaranteed drops do not count."
        },
        "8": {
            "name": "Hydra Unique",
            "desc": "A Hydra's claw OR full ring(Eye, Heart, Fang)",
            "discord_name": "Hydra Unique - A Hydra's claw OR full ring(Eye, Heart, Fang)"
        },
        "9": {
            "name": "Shard/Seed",
            "desc": "Blood shard and Enhanced crystal seed drop - drops OR thieving. IF THIEVING, Log with bingo password is required.",
            "discord_name": "Shard/Seed - Blood shard and Enhanced crystal seed drop - drops OR thieving. IF THIEVING, Log with bingo password is required."
        },
        "10": {
            "name": "Unsired",
            "desc": "3 Unsired",
            "discord_name": "Unsired - 3 Unsired"
        },
        "11": {
            "name": "Cerb Crystals",
            "desc": "4 Cerberus crystals(and stone) - no dupes",
            "discord_name": "Cerb Crystals - 4 Cerberus crystals(and stone) - no dupes"
        },
        "12": {
            "name": "GWD Uniques",
            "desc": "1 unique from every GWD boss(Includes pet) (No Saradomin Sword[too EZ],No shards, No Nex)",
            "discord_name": "GWD Uniques - 1 unique from every GWD boss(Includes pet) (No Saradomin Sword[too EZ],No shards, No Nex)"
        },
        "13": {
            "name": "Raids Cosmetic",
            "desc": "Dust, or Kit from Raids EXCLUDES ALL TOA KITS",
            "discord_name": "Raids Cosmetic - Dust, or Kit from Raids EXCLUDES ALL TOA KITS"
        },
        "14": {
            "name": "Boss jar",
            "desc": "Any Boss jar",
            "discord_name": "Boss jar - Any Boss jar"
        },
        "15": {
            "name": "Basilisk Jaw",
            "desc": "1 Basilisk jaw",
            "discord_name": "Basilisk Jaw - 1 Basilisk jaw"
        },
        "16": {
            "name": "Zalcano unique",
            "desc": "Zalcano unique",
            "discord_name": "Zalcano unique - Zalcano unique"
        },
        "17": {
            "name": "Axe/Cudgel",
            "desc": "Zombie axe AND Sarachnis Cudgel",
            "discord_name": "Axe/Cudgel - Zombie axe AND Sarachnis Cudgel"
        },
        "18": {
            "name": "Voidwaker",
            "desc": "Build a Voidwaker",
            "discord_name": "Voidwaker - Build a Voidwaker"
        },
        "19": {
            "name": "Helm Recolor",
            "desc": "3 slayer helm recolors NO DUPES, (KBD, VORK, KQ, HYDRA, SIRE, CLAW)",
            "discord_name": "Helm Recolor - 3 slayer helm recolors NO DUPES, (KBD, VORK, KQ, HYDRA, SIRE, CLAW)"
        },
        "20": {
            "name": "Full Moon",
            "desc": "Two(2) Different Full Perilous Moon Sets",
            "discord_name": "Full Moon - Two(2) Different Full Perilous Moon Sets"
        },
        "21": {
            "name": "Raids Weapon",
            "desc": "Any Raids weapon (Kodia counts)",
            "discord_name": "Raids Weapon - Any Raids weapon (Kodia counts)"
        },
        "22": {
            "name": "Zulrah Uniques",
            "desc": "Magic Fang, Tanz Fang, Onyx, and Serp Visage(ALL 4) OR 1 mutagen from Zulrah",
            "discord_name": "Zulrah Uniques - Magic Fang, Tanz Fang, Onyx, and Serp Visage(ALL 4) OR 1 mutagen from Zulrah"
        },
        "23": {
            "name": "Raids Shield",
            "desc": "1 Raids shield slot/shield (Dinhs counts)",
            "discord_name": "Raids Shield - 1 Raids shield slot/shield (Dinhs counts)"
        },
        "24": {
            "name": "Nightmare Unique",
            "desc": "Excludes Slepey tab, and Parasitic Egg",
            "discord_name": "Nightmare Unique - Excludes Slepey tab, and Parasitic Egg"
        },
        "25": {
            "name": "DT2 Unique",
            "desc": "Virtus Piece, Vestige, Axe piece, or Three(3) Ingots",
            "discord_name": "DT2 Unique - Virtus Piece, Vestige, Axe piece, or Three(3) Ingots"
        },
        "26": {
            "name": "Bonus Tiles",
            "desc": "Dirty rotten cloggers... eat your hearts out. Ring of Endurance, Dragon Full Helm(Drop or Pyre), Eternal Glory",
            "discord_name": "Bonus Tiles - Dirty rotten cloggers... eat your hearts out. Ring of Endurance, Dragon Full Helm(Drop or Pyre), Eternal Glory"
        }
    },
    "posts": {
        "score-board": {
            "id": 1292637097030717493,
            "content": "Raw Dogs: 91\nRats N Batts: 101\nVarlamores Whores: 99"
        }
    }
}


shortcuts = (
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

settings = load_settings_json()


def calculate_shortcut(score):
    idx = [x[1] for x in shortcuts if x[0] == score]
    if idx:
        return idx[0]
    
if new_score := calculate_shortcut(score):
    score = new_score

def calculate_row_and_column(score):
    # breakpoint()
    row = math.floor((score-1) / 10)
    actual_row = 10 - row
    column = score % 10
    if column == 0:
        column = 10
    row_even = True if row % 2 == 1 else False
    if row_even:
        actual_column = 10 - column if column != 10 else 1
    else:
        actual_column = column
    return actual_row, actual_column

    
def calculate_location_x_and_y(score):
    settings = load_settings_json()
    board_bounds = settings['board_bounds']
    tile_size = board_bounds['tile_size']
    print(f'Calc start: {score = }')
    print('Calculate Row and Column')
    row, column = calculate_row_and_column(score)
    print(f'({row}, {column})')
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


def mark_team_icons_on_board() -> None:
    settings = load_settings_json()
    if settings['bot_mode']['current'] != "chutes and ladders":
        print("Error: Bot mode is set to something other than 'chutes and ladders'")
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

    # establish path

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
        # score = settings['teams'][team_name]['current']
        score = team_scores[i][1]
        print(f'{team_name = } - {score = }')
        if score == 0:
            # do not draw on board
            print(f'skipping {team_name} due to score: 0')
            continue
        # check if score exists for other teams
        shared_tile = False if all_scores.count(score) == 1 else True
        number_of_tiles = all_scores.count(score)
        # open image
        img_team = Image.open(icon_team_files[i])
        team_x, team_y = img_team.size
        img_team = img_team.resize((math.floor(team_x * 0.75), math.floor(team_y * 0.75)))
        x, y = calculate_location_x_and_y(score)
        print(f'({x = }, {y = })')
        offset_width = tile_size - img_team.size[0]
        if shared_tile:
            print(f'{dupe_scores_processed = }')
            offset_multiplier = number_of_tiles - dupe_scores_processed - 1
            new_x = x + (board_bounds['team_icon_x_offset'] + offset_multiplier * (math.floor(offset_width / number_of_tiles)))
            dupe_scores_processed += 1
            print(f'{dupe_scores_processed = }')
        else:
            new_x = x + board_bounds['team_icon_x_offset']
        new_y = y + board_bounds['team_icon_y_offset']
        print(f'({new_x = }, {new_y = })')
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
    return settings


mark_team_icons_on_board()




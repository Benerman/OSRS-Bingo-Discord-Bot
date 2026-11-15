OSRS Bingo Bot
by: Benerman

This bot is utilized to help manage and make the moderating process simple for Old School Runescape Bingos that our clan hosts.
We have a server that we maintain and build out the functionality of this bot as needs arise.

The bot uses "/" slash commands

My deployment changes make it so pushing commit to github rebuilds the docker container with updated code, so sorry for spam.


Listing out the commands that the bot uses and the simple use cases below(if required)

# Configuring Bingo Settings Commands

## Essential Commands

### /upload_tiles <sheet_link: str> <process_sheet: bool = True>
Sets the tiles for the bingo game using a PUBLIC Google Sheet.
Provide the FULL URL link to the Google Sheets document containing the tile data.
settings['items'] will get updated with the new tile URL.
If process_sheet is True, the sheet will be processed and the settings will be updated.
Blank rows are skipped. If the link includes a `gid=`, that sheet tab is used, otherwise the first tab.

Normal bingo sheets have the columns: name, description, points (optional).
Tiles are read left to right, top to bottom onto the 5x5 card: rows 1-5 of the sheet are A1-E1, row 6 is A2, and so on.
Tiles without a points value are worth `default_tile_points` (see /score config).

    Example of Normal Bingo Template is:
    https://docs.google.com/spreadsheets/d/1zkhEsUOME7lRTQ8m5n3puieyKJsG3fcqiiTonQQwWoA/edit?usp=sharing

    Example of Candyland Bingo Template is:
    https://docs.google.com/spreadsheets/d/1-S-m4r3JCMdzbc-AfBCaUDPQO08SQWC0vjcwO44kHBg/edit?usp=sharing

    Parameters:
    - sheet_link (str): The FULL URL link to the Google Sheets document containing the tile data.
    - process_sheet (bool, optional): Whether to process the sheet and update the settings. Defaults to True.

### /create_team_channels <team_name: str>
Creates the team's category (named after its display name) and team-specific channels of the tile lists(settings['items']).
The category's ID is saved, so the bot finds it even if it is renamed. Refuses if the team already has a category; use /delete_team first.
Adds to channel descriptions and posts message of the tile description.
Adds some other basic channels specified:
    - DEFAULT_CHANNELS = ["chat", "bingo-card", "drop-spam", "pets", "voice-chat"]
    - CANDYLAND_DEFAULT_CHANNELS = ["chat", "bingo-card", "dice-roll", "photo-dump", "voice-chat"]

    "drop-spam" gets a webhook generated and posted to the channel.

    Parameters:
    - team_name (str): The name of the team for which channels will be created.

### /post_tiles
Posts the tiles to the #tile-list channel in the guild if it doesn't exist. Updates if it does.
Uses the stored settings to get the proper channel and message ID, looks it up if it doesn't exist.
Uses the settings.json file to get the tiles(settings['items']).


### /post_bingo_card <for_all_teams: bool = False> <team_name: Optional[str] = None>
Posts a bingo card image in the corresponding team's Bingo Card Channel. Works in every bot mode.

    Parameters:
    - for_all_teams: A boolean indicating whether to post the bingo card for all teams or not. Default is False.
    - team_name: The name of the team for which to post the bingo card. Default is None. Only required if NOT for_all_teams

### /mark_specific_tile_completed <team_name: str> <location: str>
Marks a tile as completed for a specific team, adds the tile's points (plus any line or blackout bonus),
redraws the Bingo Card, updates #score-board and posts the change in the team's chat channel.
Works for 5x5 bingo style board, requires /set_image_bounds to properly display within image correctly
Table Columns and Rows are labeled like Excel, Columns A - E with Rows 1 - 5
/mark_specific_tile_completed team_name: Team 1 location: A2

    Parameters:
    - team_name (str): The name of the team.
    - location (str): The location of the tile in the Bingo Card.

### /unmark_tile_completed <team_name: str> <location: str>
Unmarks a completed tile, takes back its points (and any line or blackout bonus it was part of) and redraws the Bingo Card.

### /update_score
Updates the score in the #score-board channel, 
Uses the settings['total_teams'] to display teams
Uses the stored settings to get the proper channel and message ID, looks it up if it doesn't exist.

### /update_tiles_channels <team_name: str>
Updates the channels' tiles for a specific team.
Edits existing message in the channel and updates channel description.
Used if there are changes to the tiles after the game has started.
Updates only team specified.

    Parameters:
    - team_name (str): The name of the team.

### /default_bingo_card  <team_name>
Posts the default bingo card image in the specified team's Bingo Card Channel.

### /change_team_name <team_name: str> <new_team_name: str>
Changes the team's display name and renames its category. Pick the team from the list (it shows display names).
If the team has no category yet, only the name is changed and /create_team_channels will use it.

    Parameters:
    - team_name (str): The current name of the team to be changed.
    - new_team_name (str): The new name for the team.

### /delete_team <team_name: str>
Deletes the team's category and all its channels, resets its display name and forgets the saved category.
Prompts for user's confirmation on bot's response before deleting the channels.

    Parameters:
    - team_name (str): The name of the team whose channels are to be deleted.

### /version <bingo_version: bool = False> <candyland: bool = False>
Views or updates the bot version based on the provided parameters
Both options are optional, if none are provided as True, current version is displayed.

    Parameters:
    - bingo_version: A boolean indicating whether to set the bot version to "normal" (True) or not (False).
    - candyland: A boolean indicating whether to set the bot version to "candyland" (True) or not (False).

### /sync
Synchronizes the command tree with the bot.

## Bingo Settings Commands

### /set_tile <team_name: str> <tile: int>
Sets the current tile or score for a given team in the OSRS Bingo Discord Bot.

    Parameters:
    - team_name (str): The name of the team for which to set the tile.
    - tile (int): The tile number or score to set for the team.

### /set_previous_tile <team_name: str> <tile: int>
Sets the previous tile/score for a given team in the settings.

    Parameters:
    - team_name (str): The name of the team.
    - tile (int): The number or score of the previous tile.

### /reset_bingo_settings
Resets the bingo settings for all teams.

### /update_total_teams <total_teams: 1-7>
Updates the number of active teams in the settings and sends a response message.

    Parameters:
    - total_teams (int): The new number of active teams.

### /upload_board_image <file: discord.Attachment>
Uploads a board image and updates the default Bingo Card Image for all teams.

    Parameters:
    - file (discord.Attachment): The image file to be uploaded.

### /set_image_bounds <x: int> <y: int> <x_left_offset: int> <x_right_offset: int> <y_top_offset: int> <y_bottom_offset: int> <gutter: int>        
Sets the image bounds for each team in the settings.

    Parameters:
    - x: The x-coordinate of the image.
    - y: The y-coordinate of the image.
    - x_left_offset: The left offset of the image.
    - x_right_offset: The right offset of the image.
    - y_top_offset: The top offset of the image.
    - y_bottom_offset: The bottom offset of the image.
    - gutter: The gutter size of the image.

## Scoring Commands

A team's score is its points in normal bingo, and its tile in candyland / chutes and ladders.
Every change is logged with who made it and why, refreshes #score-board, and is posted in the team's chat channel.
#score-board ranks the teams and shows how far each is behind the leader.

### /score add <team_name> <points> [reason]
Adds points. In candyland / chutes and ladders this moves the team forward (no tile channel is created).

### /score remove <team_name> <points> [reason]
Removes points (never below 0). In candyland / chutes and ladders this moves the team back.

### /score set <team_name> <points> [reason]
Sets the score. /set_tile does the same and is also logged.

### /score undo <team_name>
Undoes the team's last score change. Undoing a tile mark also unmarks the tile and removes any bonus it gave.

### /score history <team_name> [count]
Shows recent score changes (only to you). Undone changes are struck through.

### /score config [default_tile_points] [line_bonus] [blackout_bonus] [approvals_required] [show_tile_count]
Shows or changes scoring settings. Point and bonus changes only affect tiles marked afterwards.
- default_tile_points: points for tiles with no points value in the sheet (default 1)
- line_bonus: extra points for each completed row, column or diagonal (default 0 = off)
- blackout_bonus: extra points for completing all 25 tiles (default 0 = off)
- approvals_required: how many different moderators must approve a /submit (default 1)
- show_tile_count: show tiles completed on #score-board in normal bingo, counted against the tiles loaded, up to 25 (default on)

## Submissions

### /submit <proof: image> [tile] [note]
Players submit a screenshot from the tile's channel. The tile is worked out from the channel,
or given with `tile` (A1-E5, or the tile number in candyland / chutes and ladders).
The submission is sent to #submissions (or #bot-commands if there is no #submissions channel) with Approve and Reject buttons.
Only Bingo Moderators can use the buttons, and they keep working after the bot restarts.
- Approve: once enough different moderators approve (a player can't approve their own), the tile is marked completed.
  In normal bingo this adds the points, redraws the Bingo Card and updates #score-board.
- Reject: asks for a reason, which is sent to the player.

### /pending_submissions
Lists submissions waiting for review with links to them.

## Role Related Commands

### /add_team_role <team_name: str> <members: str>
Adds a team role to the specified members.
Specify team name and @ the users to add the role to.
members: @user1 @user2 @user3

    Parameters:
    - team_name (str): The name of the team to add the role for.
    - members (str): A string containing the mentions of the members to add the role to.

### /spectators <members: str> <unassign: bool = False>
Assigns or unassigns the "spectator" role to the specified members.
Use of @everyone will assign/unassign the role to all members in the server.
Specify the unassign parameter to remove or add the role. The default is to add the role(Unassign = False).
members: @user1 @user2 @user3

    Parameters:
    - members: A string containing the mentions of the members to assign/unassign the role to.
    - unassign: A boolean indicating whether to unassign the role (default: False).

### /clear_team_role <team_name: str>
Disbands a team by removing the corresponding role from all members in the guild.

    Parameters:
    - team_name (str): The name of the team to disband.

### /close_server
Closes the server by removing all 'spectators roles' and 'Rules Accepted' roles effectively limiting all access to non 'Bingo-Moderator'.

## Candyland Style Specific Commands


### /roll
Rolls the dice for a team in the bingo game.
uses roll_dice() to get a random number between 1 and DICE_SIDES
Requires the user to have the appropriate team role and be in the correct channel: roll_channel.
Updates the team's current tile, previous tile, and roll history in the settings.
Creates a new channel for the newly rolled tile and posts the tile information in the channel.

### /reroll
Rerolls the dice for a team in the bingo game.
Requires the user to have the appropriate team role and be in the correct channel: roll_channel.
Uses previous tile and roll to determine the new tile.
5/2/24 - Currently can reroll the same tile that it is on. This needs to be updated.
Updates the team's current tile, previous tile, and roll history in the settings.
Creates a new channel for the newly rolled tile and posts the tile information in the channel.

### /configure_team_reroll <team_name: str>
Prompts the user to Give or Revoke reroll by responding to bot's message

    Parameters:
    - team_name (str): The name of the team to set the reroll configuration for.

### /check_roll_enabled
Checks if rolling is enabled and displays status.

### /toggle_rolling
Toggles the rolling functionality for the bot based on user interaction with bot response.
User has option to disable rolling or enable rolling by clicking button on bot's response.

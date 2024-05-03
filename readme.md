OSRS Bingo Bot
by: Benerman

This bot is utilized to help manage and make the moderating process simple for Old School Runescape Bingos that our clan hosts.
We have a server that we maintain and build out the functionality of this bot as needs arise.

The bot uses "/" slash commands

My deployment changes make it so pushing commit to github rebuilds the docker container with updated code, so sorry for spam.


Listing out the commands that the bot uses and the simple use cases below(if required)

# Configuring Bingo Settings Commands

## Essential Commands

### /set_tiles <sheet_link: str> <process_sheet: bool = True>
Sets the tiles for the bingo game using a PUBLIC Google Sheet.
Provide the FULL URL link to the Google Sheets document containing the tile data.
settings['items'] will get updated with the new tile URL.
If process_sheet is True, the sheet will be processed and the settings will be updated.

    Example of Normal Bingo Template is:
    https://docs.google.com/spreadsheets/d/1zkhEsUOME7lRTQ8m5n3puieyKJsG3fcqiiTonQQwWoA/edit?usp=sharing

    Example of Candyland Bingo Template is:
    https://docs.google.com/spreadsheets/d/1-S-m4r3JCMdzbc-AfBCaUDPQO08SQWC0vjcwO44kHBg/edit?usp=sharing

    Parameters:
    - sheet_link (str): The FULL URL link to the Google Sheets document containing the tile data.
    - process_sheet (bool, optional): Whether to process the sheet and update the settings. Defaults to True.

### /create_team_channels <team_name: str>
Creates team-specific channels of the tile lists(settings['items'])
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
Posts a bingo card image in the corresponding team's Bingo Card Channel.

    Parameters:
    - for_all_teams: A boolean indicating whether to post the bingo card for all teams or not. Default is False.
    - team_name: The name of the team for which to post the bingo card. Default is None. Only required if NOT for_all_teams

### /mark_tile_completed <team_name: str> <location: str>
Marks a tile as completed for a specific team and updates the Bingo Card.
Works for 5x5 bingo style board, requires /image_bounds to properly display within image correctly
Table Columns and Rows are labeled like Excel, Columns A - E with Rows 1 - 5
/mark_tile_completed team_name: Team 1 location: A2

    Parameters:
    - team_name (str): The name of the team.
    - location (str): The location of the tile in the Bingo Card.

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
Changes the name of a team in the settings and updates the corresponding category name.
Requires the Team Name to be the same as in the settings, will fail if it isn't.
If fails, change the team name(Category) manually and try running category command again. 

    Parameters:
    - team_name (str): The current name of the team to be changed.
    - new_team_name (str): The new name for the team.

### /delete_team <team_name: str>
Deletes all channels associated with a team.
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

## Future Implementation

### /tile_completed
NOT IMPLEMENTED YET
Updates the tile completion status and score in the settings and scoreboard channel.
could be used to mark a channel completed for Candyland style bingo

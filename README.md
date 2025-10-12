# Discord Random Voice Picker Bot

This project provides a minimal Discord bot with slash commands for randomizing members of a voice channel.

## Features
- Slash commands for picking a random winner, creating balanced teams, moving them to other channels, and bringing them back.
- Uses Discord embeds and ephemeral responses so results are easy to read without spamming text channels.
- Persists the most recent team assignments and move destinations per voice channel for follow-up commands.

## Prerequisites
- Python 3.10+
- A Discord application with a bot token and the `applications.commands` scope enabled.
- The bot must have the following gateway intents enabled in the [Discord Developer Portal](https://discord.com/developers/applications):
  - **Server Members Intent**
  - **Presence Intent** (not required but recommended if you extend the bot)
  - **Message Content Intent** is not required for this project.

## Installation
1. Clone this repository and navigate into it.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project directory:
   ```env
   DISCORD_BOT_TOKEN=your_token_here
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

## Running the bot

```bash
export DISCORD_BOT_TOKEN="your_token_here"
python bot.py
```

Once the bot is running, invoke `/random_winner` or `/random_teams` in any guild where the bot is present. If you don't specify a voice channel, the bot will use your current one.

## Command reference

All commands operate on the voice channel the user is currently connected to.

| Command | Options | Description |
| --- | --- | --- |
| `/random_winner` | _None_ | Selects a random non-bot member from your current voice channel and announces them as the winner. |
| `/random_teams` | `red_captain` (optional), `blue_captain` (optional) | Shuffles the channel into balanced red and blue teams. You can pin captains for each team, provided they are distinct human members already in the channel. |
| `/move_teams` | `red_voice`, `blue_voice` (voice channels, required) | Moves the most recently generated red and blue teams into the supplied destination voice channels. Must be run from the channel where `/random_teams` was last used. |
| `/reconvene` | _None_ | Returns the most recently moved team members from their destination channels back to your current voice channel. |

If a command fails (for example, no previous teams were generated or a member can’t be moved), the bot responds with an ephemeral error message explaining what to fix.

# Discord Random Voice Picker Bot

This project provides a minimal Discord bot with slash commands for randomizing members of a voice channel.

## Features
- Slash command `/random_winner` that selects a random member from a specified voice channel.
- Slash command `/random_teams` that splits members into evenly sized red and blue teams using an embedded response, with optional captains and excluded users.
- Both commands default to the voice channel of the invoking user if no channel is provided.
- Optionally include bots in either command's selection.

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
   ```
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project directory:
   ```
   DISCORD_BOT_TOKEN=your_token_here
   ```

3. Run the bot:
   ```
   python bot.py
   ```

## Running the bot

```bash
export DISCORD_BOT_TOKEN="your_token_here"
python bot.py
```

Once the bot is running, invoke `/random_winner` or `/random_teams` in any guild where the bot is present. If you don't specify a voice channel, the bot will use your current one. For `/random_teams`, the `excluded_users` option accepts multiple user mentions or raw Discord IDs separated by spaces.

## Move performance tuning

The bot now supports environment variables for voice move throughput and retry behavior:

- `MEMBER_FETCH_CONCURRENCY` (default: `8`): Parallel member fetches.
- `MEMBER_MOVE_CONCURRENCY` (default: `8`): Parallel voice move requests.
- `MEMBER_MOVE_DELAY_SECONDS` (default: `0`): Optional delay after each move. Keep at `0` for fastest moves.
- `MEMBER_MOVE_TARGET_PER_SECOND` (default: `0`): Optional smoothing rate. Example `4` sends roughly 4 move requests/second for steadier behavior.
- `MEMBER_MOVE_MAX_RETRIES` (default: `3`): Retries for transient move failures.
- `MEMBER_MOVE_RETRY_BASE_SECONDS` (default: `0.75`): Base backoff for retries.

Example:

```bash
export MEMBER_FETCH_CONCURRENCY=8
export MEMBER_MOVE_CONCURRENCY=10
export MEMBER_MOVE_DELAY_SECONDS=0
export MEMBER_MOVE_TARGET_PER_SECOND=4
export MEMBER_MOVE_MAX_RETRIES=4
export MEMBER_MOVE_RETRY_BASE_SECONDS=0.75
python bot.py
```

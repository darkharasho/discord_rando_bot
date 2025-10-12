# Discord Random Voice Picker Bot

This project provides a minimal Discord bot with a slash command that chooses a random user in a voice channel.

## Features
- Slash command `/random_voice` that selects a random member from a specified voice channel.
- Defaults to the voice channel of the invoking user if no channel is provided.
- Optionally include bots in the random selection.

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

3. Create a `.env` file or export the `DISCORD_BOT_TOKEN` environment variable with your bot token.

## Running the bot

```bash
export DISCORD_BOT_TOKEN="your_token_here"
python bot.py
```

Once the bot is running, invoke `/random_voice` in any guild where the bot is present. If you don't specify a voice channel, the bot will use your current one.

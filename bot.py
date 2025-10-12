"""Discord bot that provides random voice channel utilities via slash commands."""
from __future__ import annotations

import os
import random

import discord
from discord import app_commands
from discord.ext import commands

TOKEN_ENV_VAR = "DISCORD_BOT_TOKEN"


def get_token() -> str:
    """Return the bot token from the environment, raising a helpful error if missing."""
    token = os.getenv(TOKEN_ENV_VAR)
    if not token:
        raise RuntimeError(
            f"Environment variable {TOKEN_ENV_VAR} is not set. "
            "Set it to your bot token before running the bot."
        )
    return token


intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    """Log readiness and sync the application commands."""
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.command(name="random_winner", description="Pick a random member from a voice channel")
@app_commands.describe(
    channel="Voice channel to pick from. Defaults to your current channel.",
    include_bots="Whether to include bots in the selection.",
)
async def random_winner(
    interaction: discord.Interaction,
    channel: discord.VoiceChannel | None = None,
    include_bots: bool = False,
) -> None:
    """Select a random user in the provided voice channel."""
    target_channel = channel or getattr(interaction.user.voice, "channel", None)

    if target_channel is None:
        await interaction.response.send_message(
            "You must be in a voice channel or specify one.",
            ephemeral=True,
        )
        return

    members = [member for member in target_channel.members if include_bots or not member.bot]

    if not members:
        await interaction.response.send_message(
            f"No eligible members found in {target_channel.mention}.",
            ephemeral=True,
        )
        return

    winner = random.choice(members)
    await interaction.response.send_message(
        f"🎲 Selected {winner.mention} from {target_channel.mention}!"
    )


@bot.tree.command(
    name="random_teams",
    description="Shuffle members in a voice channel into red and blue teams",
)
@app_commands.describe(
    channel="Voice channel to draw teams from. Defaults to your current channel.",
    include_bots="Whether to include bots in the team assignments.",
)
async def random_teams(
    interaction: discord.Interaction,
    channel: discord.VoiceChannel | None = None,
    include_bots: bool = False,
) -> None:
    """Shuffle channel members into two evenly sized teams."""
    target_channel = channel or getattr(interaction.user.voice, "channel", None)

    if target_channel is None:
        await interaction.response.send_message(
            "You must be in a voice channel or specify one.",
            ephemeral=True,
        )
        return

    members = [member for member in target_channel.members if include_bots or not member.bot]

    if len(members) < 2:
        await interaction.response.send_message(
            f"Need at least two eligible members in {target_channel.mention} to form teams.",
            ephemeral=True,
        )
        return

    shuffled_members = members[:]
    random.shuffle(shuffled_members)

    red_team = shuffled_members[::2]
    blue_team = shuffled_members[1::2]

    embed = discord.Embed(
        title=f"Random Teams for {target_channel.name}",
        colour=discord.Colour.random(),
    )
    embed.add_field(
        name="🟥 Red Team",
        value="\n".join(member.mention for member in red_team) or "(none)",
        inline=True,
    )
    embed.add_field(
        name="🟦 Blue Team",
        value="\n".join(member.mention for member in blue_team) or "(none)",
        inline=True,
    )

    await interaction.response.send_message(embed=embed)


def main() -> None:
    """Entrypoint to run the bot."""
    token = get_token()
    bot.run(token)


if __name__ == "__main__":
    main()

"""Discord bot that provides random voice channel utilities via slash commands."""
from __future__ import annotations

import os
import random

from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands

load_dotenv()
TOKEN_ENV_VAR = "DISCORD_BOT_TOKEN"
SYNC_GUILDS_ENV_VAR = "DISCORD_SYNC_GUILD_IDS"


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


def parse_sync_guild_ids() -> list[int]:
    """Return guild IDs from the environment for faster command registration."""
    raw_ids = os.getenv(SYNC_GUILDS_ENV_VAR, "")
    guild_ids: list[int] = []
    for raw_id in raw_ids.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            guild_ids.append(int(raw_id))
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(
                f"Invalid guild ID '{raw_id}' in {SYNC_GUILDS_ENV_VAR}."
            ) from exc
    return guild_ids


@bot.event
async def setup_hook() -> None:
    """Register application commands globally or per guild before the bot becomes ready."""
    guild_ids = parse_sync_guild_ids()
    if guild_ids:
        for guild_id in guild_ids:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
        print(
            "Synced application commands for guilds: "
            + ", ".join(str(guild_id) for guild_id in guild_ids)
        )
    else:
        await bot.tree.sync()
        print("Synced global application commands.")


@bot.event
async def on_ready() -> None:
    """Log readiness once Discord signals the client is ready."""
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.command(name="random_winner", description="Pick a random member from your current voice channel")
async def random_winner(
    interaction: discord.Interaction,
) -> None:
    """Select a random user in the provided voice channel."""
    target_channel = getattr(interaction.user.voice, "channel", None)

    if target_channel is None:
        await interaction.response.send_message(
            "You must be in a voice channel to use this command.",
            ephemeral=True,
        )
        return

    members = [member for member in target_channel.members if not member.bot]

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
    red_captain="Optional member to designate as the red team captain.",
    blue_captain="Optional member to designate as the blue team captain.",
)
async def random_teams(
    interaction: discord.Interaction,
    red_captain: discord.Member | None = None,
    blue_captain: discord.Member | None = None,
) -> None:
    """Shuffle channel members into two evenly sized teams."""
    target_channel = getattr(interaction.user.voice, "channel", None)

    if target_channel is None:
        await interaction.response.send_message(
            "You must be in a voice channel to use this command.",
            ephemeral=True,
        )
        return

    if red_captain and red_captain == blue_captain:
        await interaction.response.send_message(
            "Red and blue captains must be different members.",
            ephemeral=True,
        )
        return

    for captain, colour in (
        (red_captain, "red"),
        (blue_captain, "blue"),
    ):
        if captain is None:
            continue
        if captain not in target_channel.members:
            await interaction.response.send_message(
                f"The {colour} team captain must be in {target_channel.mention}.",
                ephemeral=True,
            )
            return
        if captain.bot:
            await interaction.response.send_message(
                "Bots cannot be captains.",
                ephemeral=True,
            )
            return

    members = [member for member in target_channel.members if not member.bot]

    if len(members) < 2:
        await interaction.response.send_message(
            f"Need at least two eligible members in {target_channel.mention} to form teams.",
            ephemeral=True,
        )
        return

    shuffled_members = members[:]
    random.shuffle(shuffled_members)

    excluded_captain_ids = {
        captain.id for captain in (red_captain, blue_captain) if captain is not None
    }

    remaining_members = [
        member for member in shuffled_members if member.id not in excluded_captain_ids
    ]

    red_team = [red_captain] if red_captain else []
    blue_team = [blue_captain] if blue_captain else []

    total_members = len(members)
    base_team_size = total_members // 2
    extra_team: str | None = None
    if total_members % 2 == 1:
        extra_team = random.choice(["red", "blue"])

    team_targets = {
        "red": base_team_size + (1 if extra_team == "red" else 0),
        "blue": base_team_size + (1 if extra_team == "blue" else 0),
    }

    for member in remaining_members:
        possible_teams = [
            team_name
            for team_name, team_members in (("red", red_team), ("blue", blue_team))
            if len(team_members) < team_targets[team_name]
        ]
        if possible_teams:
            chosen_team = random.choice(possible_teams)
        else:
            chosen_team = "red" if len(red_team) <= len(blue_team) else "blue"
        if chosen_team == "red":
            red_team.append(member)
        else:
            blue_team.append(member)

    def format_team_member(member: discord.Member, captain: discord.Member | None) -> str:
        if captain and member.id == captain.id:
            return f"⭐ {member.mention} (Captain)"
        return member.mention

    def build_team_field(team: list[discord.Member], captain: discord.Member | None) -> str:
        if not team:
            return "(none)"
        return "\n".join(format_team_member(member, captain) for member in team)

    embed = discord.Embed(
        title=f"Random Teams for {target_channel.name}",
        colour=discord.Colour.random(),
    )
    embed.add_field(
        name="🟥 Red Team",
        value=build_team_field(red_team, red_captain),
        inline=True,
    )
    embed.add_field(
        name="🟦 Blue Team",
        value=build_team_field(blue_team, blue_captain),
        inline=True,
    )

    if extra_team is not None:
        extra_colour = "Red" if extra_team == "red" else "Blue"
        embed.set_footer(text=f"{extra_colour} team received the extra player this round.")

    await interaction.response.send_message(embed=embed)


def main() -> None:
    """Entrypoint to run the bot."""
    token = get_token()
    bot.run(token)


if __name__ == "__main__":
    main()

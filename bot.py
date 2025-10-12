"""Discord bot that provides random voice channel utilities via slash commands."""
from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Dict, List

from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands

load_dotenv()
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


intents = discord.Intents.all()
intents.guilds = True
intents.members = True
intents.voice_states = True


class TeamBot(commands.Bot):
    """Custom bot implementation that synchronizes application commands."""

    async def setup_hook(self) -> None:  # type: ignore[override]
        await sync_application_commands(self)


bot = TeamBot(command_prefix="!", intents=intents)


@dataclass
class TeamAssignment:
    """Represent the latest team assignment for a voice channel."""

    red_team_ids: List[int]
    blue_team_ids: List[int]


@dataclass
class TeamDestinations:
    """Represent the most recent destination channels used for a voice channel."""

    red_voice_id: int
    blue_voice_id: int


# Mapping of voice channel ID to the most recent team assignments.
LAST_TEAM_ASSIGNMENTS: Dict[int, TeamAssignment] = {}

# Mapping of voice channel ID to the destination channels used in /move_teams.
LAST_TEAM_DESTINATIONS: Dict[int, TeamDestinations] = {}


async def sync_application_commands(client: commands.Bot) -> None:
    """Synchronize application commands for all connected guilds."""
    if not client.guilds:
        await client.tree.sync()
        print("Synced global application commands (no guilds available yet).")
        return

    for guild in client.guilds:
        try:
            await client.tree.sync(guild=guild)
        except discord.HTTPException as exc:
            print(
                f"Failed to sync application commands for guild: {guild.name} ({guild.id}) - {exc}"
            )
        else:
            print(
                f"Synced application commands for guild: {guild.name} ({guild.id})"
            )


@bot.event
async def on_ready() -> None:
    """Log readiness once Discord signals the client is ready."""
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    await sync_application_commands(bot)


@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    """Ensure commands are available immediately after joining a new guild."""
    await bot.tree.sync(guild=guild)
    print(f"Synced application commands for newly joined guild: {guild.name} ({guild.id})")


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

    LAST_TEAM_ASSIGNMENTS[target_channel.id] = TeamAssignment(
        red_team_ids=[member.id for member in red_team],
        blue_team_ids=[member.id for member in blue_team],
    )


@bot.tree.command(
    name="move_teams",
    description="Move the last randomized teams into the specified voice channels.",
)
@app_commands.describe(
    red_voice="Voice channel to move the red team into.",
    blue_voice="Voice channel to move the blue team into.",
)
async def move_teams(
    interaction: discord.Interaction,
    red_voice: discord.VoiceChannel,
    blue_voice: discord.VoiceChannel,
) -> None:
    """Move the previously randomized teams into the provided voice channels."""

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used within a server.",
            ephemeral=True,
        )
        return

    current_channel = getattr(interaction.user.voice, "channel", None)

    if current_channel is None:
        await interaction.response.send_message(
            "You must be in a voice channel to move the teams.",
            ephemeral=True,
        )
        return

    if red_voice.guild.id != interaction.guild.id or blue_voice.guild.id != interaction.guild.id:
        await interaction.response.send_message(
            "Both destination channels must belong to this server.",
            ephemeral=True,
        )
        return

    assignment = LAST_TEAM_ASSIGNMENTS.get(current_channel.id)
    if assignment is None:
        await interaction.response.send_message(
            "No team assignments found for this voice channel. Run /random_teams first.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    async def resolve_member(member_id: int) -> discord.Member | None:
        member = interaction.guild.get_member(member_id)
        if member is not None:
            return member
        try:
            return await interaction.guild.fetch_member(member_id)
        except discord.NotFound:
            return None

    async def move_members(
        member_ids: List[int],
        destination: discord.VoiceChannel,
    ) -> tuple[list[str], list[str]]:
        moved_mentions: list[str] = []
        skipped_messages: list[str] = []

        for member_id in member_ids:
            member = await resolve_member(member_id)
            if member is None:
                skipped_messages.append(f"<@{member_id}> (not found)")
                continue
            if member.voice is None or member.voice.channel is None:
                skipped_messages.append(f"{member.mention} (not in a voice channel)")
                continue
            if member.voice.channel.id == destination.id:
                moved_mentions.append(member.mention)
                continue
            try:
                await member.move_to(destination)
            except (discord.HTTPException, discord.Forbidden) as exc:
                skipped_messages.append(f"{member.mention} (failed to move: {exc})")
            else:
                moved_mentions.append(member.mention)

        return moved_mentions, skipped_messages

    team_results = []
    for team_name, member_ids, channel in (
        ("Red", assignment.red_team_ids, red_voice),
        ("Blue", assignment.blue_team_ids, blue_voice),
    ):
        moved, skipped = await move_members(member_ids, channel)
        team_results.append((team_name, channel, moved, skipped))

    lines: list[str] = []
    for team_name, channel, moved, skipped in team_results:
        lines.append(
            f"Moved {len(moved)} {team_name.lower()} team member(s) to {channel.mention}."
        )
        if skipped:
            lines.append(
                f"Skipped {len(skipped)} member(s) for the {team_name.lower()} team: "
                + ", ".join(skipped)
            )

    await interaction.followup.send("\n".join(lines), ephemeral=True)

    LAST_TEAM_DESTINATIONS[current_channel.id] = TeamDestinations(
        red_voice_id=red_voice.id,
        blue_voice_id=blue_voice.id,
    )


@bot.tree.command(
    name="reconvene",
    description="Return the most recent teams from their channels back to your current channel.",
)
async def reconvene(interaction: discord.Interaction) -> None:
    """Bring the last moved teams back into the caller's current voice channel."""

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used within a server.",
            ephemeral=True,
        )
        return

    target_channel = getattr(interaction.user.voice, "channel", None)

    if target_channel is None:
        await interaction.response.send_message(
            "You must be in a voice channel to reconvene teams.",
            ephemeral=True,
        )
        return

    destinations = LAST_TEAM_DESTINATIONS.get(target_channel.id)

    if destinations is None:
        await interaction.response.send_message(
            "No recent team moves found for this voice channel. Run /move_teams first.",
            ephemeral=True,
        )
        return

    red_channel = interaction.guild.get_channel(destinations.red_voice_id)
    blue_channel = interaction.guild.get_channel(destinations.blue_voice_id)

    for channel, colour in ((red_channel, "red"), (blue_channel, "blue")):
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message(
                f"The {colour} team channel could not be found. Run /move_teams again.",
                ephemeral=True,
            )
            return

    await interaction.response.defer(ephemeral=True)

    assignment = LAST_TEAM_ASSIGNMENTS.get(target_channel.id)

    async def resolve_member(member_id: int) -> discord.Member | None:
        member = interaction.guild.get_member(member_id)
        if member is not None:
            return member
        try:
            return await interaction.guild.fetch_member(member_id)
        except discord.NotFound:
            return None

    async def move_back_member(member: discord.Member) -> tuple[str | None, str | None]:
        if member.bot:
            return None, None
        if member.voice is None or member.voice.channel is None:
            return None, f"{member.mention} (not in a voice channel)"
        if member.voice.channel.id == target_channel.id:
            return member.mention, None
        try:
            await member.move_to(target_channel)
        except (discord.HTTPException, discord.Forbidden) as exc:
            return None, f"{member.mention} (failed to move: {exc})"
        else:
            return member.mention, None

    member_ids: set[int] = set()

    if assignment is not None:
        member_ids.update(assignment.red_team_ids)
        member_ids.update(assignment.blue_team_ids)

    for channel in (red_channel, blue_channel):
        member_ids.update(member.id for member in channel.members if not member.bot)

    moved_mentions: list[str] = []
    skipped_messages: list[str] = []

    for member_id in member_ids:
        member = await resolve_member(member_id)
        if member is None:
            skipped_messages.append(f"<@{member_id}> (not found)")
            continue

        mention, skipped = await move_back_member(member)
        if mention is not None:
            moved_mentions.append(mention)
        if skipped is not None:
            skipped_messages.append(skipped)

    lines = [
        f"Moved {len(moved_mentions)} member(s) back to {target_channel.mention}."
    ]

    if skipped_messages:
        lines.append(
            f"Skipped {len(skipped_messages)} member(s): "
            + ", ".join(skipped_messages)
        )

    await interaction.followup.send("\n".join(lines), ephemeral=True)


def main() -> None:
    """Entrypoint to run the bot."""
    token = get_token()
    bot.run(token)


if __name__ == "__main__":
    main()

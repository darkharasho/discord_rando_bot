"""Discord bot that provides random voice channel utilities via slash commands."""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands, tasks

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
        if not prune_team_state_loop.is_running():
            prune_team_state_loop.start()


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

# Mapping of voice channel ID to when the assignment was last updated.
LAST_TEAM_ASSIGNMENT_UPDATED: Dict[int, float] = {}

# Mapping of voice channel ID to the destination channels used in /move_teams.
LAST_TEAM_DESTINATIONS: Dict[int, TeamDestinations] = {}

# Mapping of voice channel ID to when the destination entry was last updated.
LAST_TEAM_DESTINATION_UPDATED: Dict[int, float] = {}

# Persist team data to disk so the bot can survive restarts and longer downtimes.
TEAM_STATE_FILE = Path(__file__).resolve().with_name("team_state.json")
TEAM_STATE_VERSION = 1
# Keep team information for one week before automatically pruning it.
TEAM_STATE_TTL_SECONDS = 7 * 24 * 60 * 60

# Delay between individual member moves to stay under Discord's rate limits.
MEMBER_MOVE_DELAY_SECONDS = 0.5


def persist_team_state() -> None:
    """Write team assignments and destinations to disk."""

    data = {
        "version": TEAM_STATE_VERSION,
        "assignments": {
            str(channel_id): {
                "red_team_ids": assignment.red_team_ids,
                "blue_team_ids": assignment.blue_team_ids,
                "updated_at": LAST_TEAM_ASSIGNMENT_UPDATED[channel_id],
            }
            for channel_id, assignment in LAST_TEAM_ASSIGNMENTS.items()
            if channel_id in LAST_TEAM_ASSIGNMENT_UPDATED
        },
        "destinations": {
            str(channel_id): {
                "red_voice_id": destinations.red_voice_id,
                "blue_voice_id": destinations.blue_voice_id,
                "updated_at": LAST_TEAM_DESTINATION_UPDATED[channel_id],
            }
            for channel_id, destinations in LAST_TEAM_DESTINATIONS.items()
            if channel_id in LAST_TEAM_DESTINATION_UPDATED
        },
    }

    tmp_path = TEAM_STATE_FILE.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp_path.replace(TEAM_STATE_FILE)
    except OSError as exc:
        print(f"Failed to persist team state: {exc}")


def prune_expired_entries(*, now: float | None = None) -> None:
    """Remove stale state entries that exceeded the retention window."""

    current_time = time.time() if now is None else now
    dirty = False

    for channel_id, updated_at in list(LAST_TEAM_ASSIGNMENT_UPDATED.items()):
        if current_time - updated_at > TEAM_STATE_TTL_SECONDS:
            LAST_TEAM_ASSIGNMENTS.pop(channel_id, None)
            LAST_TEAM_ASSIGNMENT_UPDATED.pop(channel_id, None)
            dirty = True

    for channel_id, updated_at in list(LAST_TEAM_DESTINATION_UPDATED.items()):
        if current_time - updated_at > TEAM_STATE_TTL_SECONDS:
            LAST_TEAM_DESTINATIONS.pop(channel_id, None)
            LAST_TEAM_DESTINATION_UPDATED.pop(channel_id, None)
            dirty = True

    if dirty:
        persist_team_state()


def load_persisted_team_state() -> None:
    """Load team state from disk, pruning any expired entries."""

    if not TEAM_STATE_FILE.exists():
        return

    try:
        raw_data = json.loads(TEAM_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Failed to load team state: {exc}")
        return

    version = raw_data.get("version")
    if version != TEAM_STATE_VERSION:
        print(
            "Team state file version mismatch; ignoring persisted data. "
            f"Found version {version}, expected {TEAM_STATE_VERSION}."
        )
        return

    now = time.time()
    dirty = False

    assignments = raw_data.get("assignments", {})
    for channel_id_str, record in assignments.items():
        try:
            channel_id = int(channel_id_str)
            updated_at = float(record.get("updated_at"))
        except (TypeError, ValueError):
            dirty = True
            continue

        if now - updated_at > TEAM_STATE_TTL_SECONDS:
            dirty = True
            continue

        try:
            assignment = TeamAssignment(
                red_team_ids=[int(member_id) for member_id in record["red_team_ids"]],
                blue_team_ids=[int(member_id) for member_id in record["blue_team_ids"]],
            )
        except (KeyError, TypeError, ValueError):
            dirty = True
            continue

        LAST_TEAM_ASSIGNMENTS[channel_id] = assignment
        LAST_TEAM_ASSIGNMENT_UPDATED[channel_id] = updated_at

    destinations = raw_data.get("destinations", {})
    for channel_id_str, record in destinations.items():
        try:
            channel_id = int(channel_id_str)
            updated_at = float(record.get("updated_at"))
        except (TypeError, ValueError):
            dirty = True
            continue

        if now - updated_at > TEAM_STATE_TTL_SECONDS:
            dirty = True
            continue

        try:
            destination = TeamDestinations(
                red_voice_id=int(record["red_voice_id"]),
                blue_voice_id=int(record["blue_voice_id"]),
            )
        except (KeyError, TypeError, ValueError):
            dirty = True
            continue

        LAST_TEAM_DESTINATIONS[channel_id] = destination
        LAST_TEAM_DESTINATION_UPDATED[channel_id] = updated_at

    if dirty:
        persist_team_state()


load_persisted_team_state()


@tasks.loop(minutes=30)
async def prune_team_state_loop() -> None:
    prune_expired_entries()


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
    red_count = len(red_team)
    blue_count = len(blue_team)
    embed.add_field(
        name=f"🟥 Red Team ({red_count})",
        value=build_team_field(red_team, red_captain),
        inline=True,
    )
    embed.add_field(
        name=f"🟦 Blue Team ({blue_count})",
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
    LAST_TEAM_ASSIGNMENT_UPDATED[target_channel.id] = time.time()
    persist_team_state()


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

    prune_expired_entries()

    assignment = LAST_TEAM_ASSIGNMENTS.get(current_channel.id)
    if assignment is None:
        await interaction.response.send_message(
            "No team assignments found for this voice channel. Run /random_teams first.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    fetch_semaphore = asyncio.Semaphore(5)
    move_semaphore = asyncio.Semaphore(5)

    async def resolve_members(member_ids: list[int]) -> dict[int, discord.Member | None]:
        resolved: dict[int, discord.Member | None] = {}
        missing: list[int] = []

        for member_id in member_ids:
            member = interaction.guild.get_member(member_id)
            if member is not None:
                resolved[member_id] = member
            else:
                missing.append(member_id)

        if missing:
            async def fetch_with_limit(member_id: int) -> discord.Member | None:
                async with fetch_semaphore:
                    try:
                        return await interaction.guild.fetch_member(member_id)
                    except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                        return None

            results = await asyncio.gather(
                *(fetch_with_limit(member_id) for member_id in missing)
            )
            for member_id, member in zip(missing, results):
                resolved[member_id] = member

        return resolved

    unique_member_ids = list({*assignment.red_team_ids, *assignment.blue_team_ids})
    resolved_members = await resolve_members(unique_member_ids)

    async def move_members(
        member_ids: List[int],
        destination: discord.VoiceChannel,
    ) -> tuple[list[str], list[str]]:
        async def process_member(
            member_id: int,
        ) -> tuple[str | None, str | None]:
            member = resolved_members.get(member_id)
            if member is None:
                return None, f"<@{member_id}> (not found)"
            if member.voice is None or member.voice.channel is None:
                return None, f"{member.mention} (not in a voice channel)"
            if member.voice.channel.id == destination.id:
                return member.mention, None
            async with move_semaphore:
                try:
                    await member.move_to(destination)
                except (discord.HTTPException, discord.Forbidden) as exc:
                    return None, f"{member.mention} (failed to move: {exc})"
                else:
                    await asyncio.sleep(MEMBER_MOVE_DELAY_SECONDS)
            return member.mention, None

        tasks = [process_member(member_id) for member_id in dict.fromkeys(member_ids)]
        if not tasks:
            return [], []

        results = await asyncio.gather(*tasks)
        moved_mentions: list[str] = []
        skipped_messages: list[str] = []

        for moved, skipped in results:
            if moved is not None:
                moved_mentions.append(moved)
            if skipped is not None:
                skipped_messages.append(skipped)

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
    LAST_TEAM_DESTINATION_UPDATED[current_channel.id] = time.time()
    persist_team_state()


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

    prune_expired_entries()

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



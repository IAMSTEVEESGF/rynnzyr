import discord
from discord.ext import commands
import os
import re

# --- Design Presets ---
# Each design is a dict: { "keyword_in_current_name": "new_name" }
# If a channel's name contains the keyword, it gets renamed.
# Add your own designs here.

DESIGNS = {
    "futuristic": {
        "general": "nexus",
        "chat": "comms",
        "announcements": "transmissions",
        "memes": "holo-deck",
        "gaming": "simulations",
        "music": "audio-bay",
        "bot": "ai-core",
        "rules": "protocols",
        "welcome": "arrivals",
    },
    "minimal": {
        "general": "chat",
        "announcements": "updates",
        "memes": "memes",
        "gaming": "games",
        "music": "music",
        "rules": "rules",
        "welcome": "welcome",
        "bot": "bots",
    },
    "gaming": {
        "general": "lobby",
        "chat": "party-chat",
        "announcements": "patch-notes",
        "memes": "clips",
        "music": "soundtrack",
        "rules": "rules-of-engagement",
        "welcome": "spawn-point",
        "bot": "commands",
    },
    "medieval": {
        "general": "tavern",
        "chat": "town-square",
        "announcements": "royal-decrees",
        "memes": "bards-tales",
        "music": "minstrels",
        "rules": "laws",
        "welcome": "gates",
        "bot": "oracle",
    },
}

# Aliases so users can type different things
DESIGN_ALIASES = {
    "future": "futuristic",
    "sci-fi": "futuristic",
    "scifi": "futuristic",
    "clean": "minimal",
    "simple": "minimal",
    "game": "gaming",
    "gamer": "gaming",
    "medieval": "medieval",
    "middle-ages": "medieval",
    "fantasy": "medieval",
}

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Assistant bot online as {bot.user}")


# --- Design resolver ---
def resolve_design_name(raw: str):
    """Turn whatever the user typed into a real design key, or None."""
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw in DESIGNS:
        return raw
    if raw in DESIGN_ALIASES:
        return DESIGN_ALIASES[raw]
    # fuzzy: check if any design name or alias is contained in the text
    for name in DESIGNS:
        if name in raw:
            return name
    for alias, real in DESIGN_ALIASES.items():
        if alias in raw:
            return real
    return None


# --- The assistant command ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Only react to messages starting with "."
    if not message.content.startswith("."):
        return

    content = message.content[1:].strip().lower()

    # Help
    if content in ("help", "commands"):
        designs_list = ", ".join(f"`{d}`" for d in DESIGNS.keys())
        await message.channel.send(
            f"👋 Hey! I'm your server assistant. Here's what I can do:\n"
            f"• `.change the channels design to this | <design>` — redesign channels\n"
            f"• `.redesign to <design>` — same thing, shorter\n"
            f"• `.designs` — list available designs\n\n"
            f"Available designs: {designs_list}"
        )
        return

    # List designs
    if content in ("designs", "list designs"):
        designs_list = ", ".join(f"`{d}`" for d in DESIGNS.keys())
        await message.channel.send(f"🎨 Available designs: {designs_list}")
        return

    # Detect a "change design" request
    # Triggers: contains "design" or "redesign" or "channels design"
    is_design_request = (
        "design" in content
        or "redesign" in content
    )

    if not is_design_request:
        return  # not a command we handle → ignore silently

    # Extract the design name
    # Priority 1: text after the last "|"
    # Priority 2: whole message (fuzzy match)
    design_raw = None
    if "|" in content:
        design_raw = content.split("|")[-1].strip()
    else:
        # try to find a design keyword anywhere in the message
        design_raw = content  # resolve_design_name will fuzzy-match

    design_name = resolve_design_name(design_raw)

    if not design_name:
        await message.channel.send(
            "🤔 I couldn't figure out which design you want. "
            "Try `.designs` to see the list, then use "
            "`.change the channels design to this | <design>`."
        )
        return

    # --- Do the work with assistant-style messages ---
    thinking = await message.channel.send(f"🔧 Working on it... switching channels to **{design_name}** design.")

    design_map = DESIGNS[design_name]
    guild = message.guild
    renamed = []
    skipped = []
    failed = []

    # Collect text + voice channels (skip categories to keep it safe)
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue

        current_lower = channel.name.lower()

        # Find the first keyword that matches
        matched_key = next((k for k in design_map if k in current_lower), None)
        if not matched_key:
            skipped.append(channel.name)
            continue

        new_name = design_map[matched_key]

        # Don't rename if already correct
        if channel.name == new_name:
            skipped.append(channel.name)
            continue

        try:
            await channel.edit(name=new_name)
            renamed.append(f"`{channel.name}` → `{new_name}`")
        except discord.Forbidden:
            failed.append(f"`{channel.name}` (no permission)")
        except Exception as e:
            failed.append(f"`{channel.name}` ({e})")

    # --- Report back ---
    lines = [f"✅ **Done!** Channels redesigned to **{design_name}**."]

    if renamed:
        lines.append("\n**Renamed:**")
        lines.extend(f"• {r}" for r in renamed)

    if failed:
        lines.append("\n**Couldn't rename:**")
        lines.extend(f"• {f}" for f in failed)

    if not renamed and not failed:
        lines.append("\n_No channels matched this design. Check the keywords in `DESIGNS`._")

    lines.append("\nLet me know if you need anything else! 😊")

    await thinking.edit(content="\n".join(lines))


# --- Run ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
    bot.run(token)

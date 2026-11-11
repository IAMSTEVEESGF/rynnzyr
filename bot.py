import discord
from discord.ext import commands
import os

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Assistant bot online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Only react to messages starting with "."
    if not message.content.startswith("."):
        return

    content = message.content[1:].strip()

    # --- Help Command ---
    if content.lower() in ("help", "commands"):
        await message.channel.send(
            "👋 Hey! I'm your design assistant.\n"
            "**To change a design:**\n"
            "`.change design [old_design] to [new_design]`\n"
            "**Example:**\n"
            "`.change design 〘📊〙・ to |`\n\n"
            "_This will keep the channel names, but swap the design part._"
        )
        return

    # --- The Design Changer ---
    # Trigger: .change design OLD to NEW
    if content.lower().startswith("change design "):
        
        # Extract the old and new designs
        try:
            # Slicing off ".change design " and splitting by " to "
            args = content[14:].strip()
            old_design, new_design = args.split(" to ", 1)
            old_design = old_design.strip()
            new_design = new_design.strip()
        except ValueError:
            await message.channel.send("🤔 Format error. Please use: `.change design [old] to [new]`")
            return

        # Assistant "working" message
        thinking = await message.channel.send(f"🔧 Working on it... changing design from `{old_design}` to `{new_design}`.")
        
        guild = message.guild
        renamed = []
        skipped = []
        failed = []

        # Loop through all channels (text and voice)
        for channel in guild.channels:
            # Skip categories to keep it safe
            if isinstance(channel, discord.CategoryChannel):
                continue

            # Check if the old design is inside the channel name
            if old_design in channel.name:
                
                # Replace the design, keep the name
                new_name = channel.name.replace(old_design, new_design).strip()
                
                # If the name is exactly the same, skip it
                if channel.name == new_name:
                    skipped.append(channel.name)
                    continue

                try:
                    # Apply the change
                    await channel.edit(name=new_name)
                    renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                except discord.Forbidden:
                    failed.append(f"`{channel.name}` (Missing Manage Channels Permission)")
                except Exception as e:
                    failed.append(f"`{channel.name}` (Error: {e})")
            else:
                # Channel doesn't have the old design
                skipped.append(channel.name)

        # --- Report back ---
        lines = [f"✅ **Done!** Updated the design to `{new_design}`."]
        
        if renamed:
            lines.append("\n**Channels updated:**")
            lines.extend(f"• {r}" for r in renamed)
            
        if failed:
            lines.append("\n**Couldn't update:**")
            lines.extend(f"• {f}" for f in failed)
            
        if not renamed and not failed:
            lines.append(f"\n_No channels found with the design `{old_design}`._")
            
        lines.append("\nLet me know if you need anything else! 😊")
        
        await thinking.edit(content="\n".join(lines))

# --- Run ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
    bot.run(token)

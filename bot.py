import discord
from discord.ext import commands
import os
import re

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
    if not message.content.startswith("."):
        return

    # Strip only the dot from the front, keep everything else exact
    content = message.content[1:]

    if content.lower() == "help":
        await message.channel.send(
            "**Commands:**\n"
            "`.design |` ➔ Changes all channels to `|name`\n"
            "`.design | ` ➔ Changes all channels to `| name` (notice the space)\n"
            "`.design default` ➔ Removes all symbols, leaving just `name`"
        )
        return

    if content.lower().startswith("design "):
        # Grabs EXACTLY what you typed after ".design "
        # If you type ".design | ", new_design is "| "
        # If you type ".design |", new_design is "|"
        new_design = content[7:]
        
        # Allow resetting to default names
        if new_design.strip().lower() == "default":
            new_design = ""
        elif not new_design.strip():
            await message.channel.send("🤔 You forgot the new design! Try `.design |`")
            return

        thinking = await message.channel.send(f"🔧 Working on it... changing design to `{new_design}`.")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            # Strip ALL symbols/emojis/spaces from the start of the current name
            # e.g. "〘📊〙・general" -> "general", "-nexus" -> "nexus", "| nexus" -> "nexus"
            clean_name = re.sub(r'^[^\w]+', '', channel.name)
            
            # Failsafe if the channel name was literally just symbols
            if not clean_name:
                clean_name = "channel"

            # Combine your new design + the clean name
            new_name = f"{new_design}{clean_name}"
            
            # Discord API requires names to be lowercase and without some characters
            new_name = new_name.lower().strip()
            
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                except discord.Forbidden:
                    failed.append(f"❌ No permission to edit `{channel.name}`")
                except Exception as e:
                    failed.append(f"❌ Error on `{channel.name}`: {e}")
                    
        msg = ""
        if renamed:
            msg += "✅ **Done!** Channels updated:\n" + "\n".join(renamed)
        if failed:
            msg += "\n\n**Errors:**\n" + "\n".join(failed)
        if not renamed and not failed:
            msg = f"😴 All channels already have this design."
            
        await thinking.edit(content=msg)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

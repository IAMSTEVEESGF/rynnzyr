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

    content = message.content[1:].strip()

    if content.lower() == "help":
        await message.channel.send(
            "**Commands:**\n"
            "`.design |` ➔ Changes all channels to `|name` (no space)\n"
            "`.design 〘📊〙・` ➔ Changes all channels to `〘📊〙・name`\n"
            "`.design default` ➔ Removes designs, leaving just `name`"
        )
        return

    if content.lower().startswith("design "):
        # Grab everything after ".design "
        new_design = content[7:].strip()
        
        # If they type ".design default", remove the design entirely
        if new_design.lower() == "default":
            new_design = ""
        elif not new_design:
            await message.channel.send("🤔 You forgot the new design! Try `.design |`")
            return

        thinking = await message.channel.send(f"🔧 Working on it... changing design to `{new_design}`.")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            # 1. Strip ALL symbols/emojis from the start of the current name
            clean_name = re.sub(r'^[^\w]+', '', channel.name)
            
            # 2. Add the new design to the front (NO SPACE)
            new_name = f"{new_design}{clean_name}"
            
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
            msg = f"😴 All channels are already set to `{new_design}name`."
            
        await thinking.edit(content=msg)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

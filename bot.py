import discord
from discord.ext import commands
import os
import re
import asyncio

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
    parts = content.split(" ", 1)

    if parts[0].lower() == "help":
        await message.channel.send("🤖 **Bot is alive!**\n\nType `.design pipe` for the thick ┃ line.\nType `.design |` for the thin | line.")
        return

    if parts[0].lower() == "design":
        if len(parts) < 2 or not parts[1]:
            await message.channel.send("❌ You forgot the design! Try `.design pipe`")
            return
            
        new_design = parts[1]
        
        # SHORTCUTS: If you type these words, it uses the exact symbols
        if new_design.lower() == "pipe":
            new_design = "┃"  # Thick line
        elif new_design.lower() == "line":
            new_design = "│"  # Medium line
        elif new_design.lower() == "default":
            new_design = ""

        # Show exactly what the bot sees
        thinking = await message.channel.send(f"🔧 Working on it... Changing design to: `{new_design}`")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            # Strip ALL symbols from the start (keeps only the letters/numbers)
            clean_name = re.sub(r'^[^\w]+', '', channel.name)
            if not clean_name:
                clean_name = "channel"

            # Combine the design and the clean name
            new_name = f"{new_design}{clean_name}".lower()
            
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                    # Wait 3 seconds to avoid Discord rate limits
                    await asyncio.sleep(3) 
                except Exception as e:
                    failed.append(f"❌ `{channel.name}`: {str(e)}")
                    
        msg = ""
        if renamed:
            msg += "✅ **Done!** Channels updated:\n" + "\n".join(renamed)
        if failed:
            msg += "\n\n**Errors:**\n" + "\n".join(failed)
        if not renamed and not failed:
            msg = f"😴 All channels are already correct."
            
        await thinking.edit(content=msg)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

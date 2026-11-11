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

    # Remove the dot and any outer spaces
    content = message.content[1:].strip()

    # Split the command exactly at the first space
    # ".design |" becomes ["design", "|"]
    # ".design 〘📊〙・" becomes ["design", "〘📊〙・"]
    parts = content.split(" ", 1)

    if parts[0].lower() == "help":
        await message.channel.send("Type `.design |` (for |name) or `.design | ` (for | name)")
        return

    if parts[0].lower() == "design":
        if len(parts) < 2:
            await message.channel.send("❌ You forgot the design! Try `.design |`")
            return
            
        # This is exactly what you typed after the space
        new_design = parts[1]
        
        # If you type ".design default", it removes the design entirely
        if new_design.lower() == "default":
            new_design = ""

        # Show exactly what the bot sees so you can verify
        thinking = await message.channel.send(f"🔧 Working on it... Detected design: `{new_design}`")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            # Strip EVERY symbol, emoji, and space from the start
            # "-nexus" -> "nexus"
            # "〘📊〙・general" -> "general"
            clean_name = re.sub(r'^[^\w]+', '', channel.name)
            
            if not clean_name:
                clean_name = "channel"

            # Combine exact design + clean name
            new_name = f"{new_design}{clean_name}"
            
            # Discord names must be lowercase
            new_name = new_name.lower()
            
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                except Exception as e:
                    failed.append(f"❌ `{channel.name}` failed: {str(e)}")
                    
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

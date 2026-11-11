import discord
from discord.ext import commands
import os
import re  # This is the magic library that makes it smart

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
        await message.channel.send("Type `.design |` to change all channel designs to `|`")
        return

    # The new smart command
    if content.lower().startswith("design "):
        # Grab whatever the user typed after ".design "
        new_design = content[7:].strip() 
        
        if not new_design:
            await message.channel.send("🤔 You forgot the new design! Try `.design |`")
            return

        thinking = await message.channel.send(f"🔧 Working on it... changing all channel designs to `{new_design}`.")
        
        guild = message.guild
        renamed = []
        failed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
                
            # THE SMART PART: This regex strips ALL leading symbols, brackets, and emojis
            # It looks at the start of the channel name until it hits a letter or number
            clean_name = re.sub(r'^[^\w]+', '', channel.name)
            
            # Build the new name
            new_name = f"{new_design} {clean_name}".strip()
            
            # Don't rename if it's already exactly correct
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
            msg = f"😴 No channels needed updating."
            
        await thinking.edit(content=msg)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

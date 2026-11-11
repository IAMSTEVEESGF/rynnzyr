import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

@bot.event
async def on_ready():
    print(f"🧨 Assistant bot online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.content.startswith("."):
        return

    content = message.content[1:].strip()

    if content.lower() == "help":
        await message.channel.send("Type: `.change design 〘📊〙・ to |`")
        return

    if content.lower().startswith("change design "):
        try:
            args = content[14:].strip()
            old_design, new_design = args.split(" to ", 1)
            old_design = old_design.strip()
            new_design = new_design.strip()
        except ValueError:
            await message.channel.send("🤔 Format error. Please use: `.change design OLD to NEW`")
            return

        thinking = await message.channel.send(f"🔧 Working on it... changing design from `{old_design}` to `{new_design}`.")
        
        guild = message.guild
        renamed = []
        
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
            if old_design in channel.name:
                new_name = channel.name.replace(old_design, new_design).strip()
                if channel.name != new_name:
                    try:
                        await channel.edit(name=new_name)
                        renamed.append(f"`{channel.name}` ➔ `{new_name}`")
                    except Exception as e:
                        print(e)
                        
        if renamed:
            msg = "✅ **Done!** Channels updated:\n" + "\n".join(renamed)
        else:
            msg = f"❌ No channels found with `{old_design}` in the name."
            
        await thinking.edit(content=msg)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

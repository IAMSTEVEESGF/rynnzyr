import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
import random # <-- Added this for the random designs
from openai import AsyncOpenAI

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key="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" 
)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Bot is online and ready!")

@bot.tree.command(name="build", description="Build a perfectly organized server using AI")
async def build(interaction: discord.Interaction, prompt: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    if len(prompt.strip()) < 10:
        await interaction.response.send_message("❌ **Too short!** Please describe your server properly.", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🧠 **AI is designing a perfect server layout for you...**")

    system_prompt = """
    You are a master Discord server architect. The user will give you a theme. 
    You must output ONLY a JSON object. Do not include markdown formatting.
    
    The JSON must follow this exact structure:
    {
      "categories": [
        {
          "name": "CATEGORY NAME",
          "channels": [
            {"name": "channel-name", "emoji": "💬", "type": "text"},
            {"name": "voice-channel", "emoji": "🔊", "type": "voice"}
          ]
        }
      ]
    }
    
    STRICT RULES FOR BUILDING:
    1. ORDER MATTERS: Sort the categories in this exact order from top to bottom:
       - IMPORTANT (Rules, Announcements, etc.)
       - WELCOME / VERIFICATION
       - GENERAL (General chat, media, bots, etc.)
       - COMMUNITY / GAME SPECIFIC (Create 2-3 categories specific to the user's theme).
       - VOICE CHATS (All voice channels here)
       - STAFF (Staff chat, logs, staff VC - always put this at the very bottom).
    2. Create 4 to 7 channels per category. Make it feel complete.
    3. Make sure the emoji perfectly matches the channel name.
    """

    try:
        response = await ai_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        layout = json.loads(response.choices[0].message.content)
        await interaction.edit_original_response(content="🔧 **Building your server now... (This takes a few minutes. Do not spam!)**")

        count = 0
        
        for cat in layout.get("categories", []):
            cat_name = f"---- 《{cat.get('name', 'CATEGORY')}》 ----"
            category = await interaction.guild.create_category(cat_name)
            await asyncio.sleep(2)
            
            for ch in cat.get("channels", []):
                emoji = ch.get('emoji', '')
                ch_name = ch.get('name', 'channel').lower()
                
                # --- THIS IS THE RANDOM DESIGN PICKER ---
                formats = [
                    f"〔{emoji}〕・{ch_name}",
                    f"{emoji}┃{ch_name}",
                    f"〘{emoji}〙・{ch_name}",
                    f"{emoji}・{ch_name}"
                ]
                full_name = random.choice(formats)
                # ----------------------------------------
                
                if ch.get('type') == 'voice':
                    await interaction.guild.create_voice_channel(full_name, category=category)
                else:
                    await interaction.guild.create_text_channel(full_name, category=category)
                
                count += 1
                await asyncio.sleep(3) 

        await interaction.edit_original_response(content=f"✅ **Done!** Built **{count}** channels with random designs. Press `Cmd + R` to refresh Discord.")

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

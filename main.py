import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
from openai import AsyncOpenAI

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- YOUR API KEY IS HARDCODED HERE ---
ai_client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key="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" 
)
# --------------------------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ AI Bot online as {bot.user}")

@bot.tree.command(name="build", description="Use AI to build a server layout")
@app_commands.describe(prompt="Describe the server you want")
async def build(interaction: discord.Interaction, prompt: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🧠 **AI is thinking up a design...**")

    system_prompt = """
    You are a Discord server designer. The user will give you a prompt.
    You must output ONLY a JSON object with a "categories" key.
    Inside categories, have a list of objects with "name" and "channels".
    Channels have "name", "emoji", and "type" (text or voice).
    Example:
    {"categories": [{"name": "GENERAL", "channels": [{"name": "chat", "emoji": "💬", "type": "text"}]}]}
    """

    try:
        response = await ai_client.chat.completions.create(
            model="llama3-8b-8192", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        layout = json.loads(response.choices[0].message.content)
        await interaction.edit_original_response(content="🔧 **Building your server now... (Takes 3s per channel)**")

        guild = interaction.guild
        count = 0

        for category_data in layout.get("categories", []):
            cat_name = f"〔✨ {category_data['name']} 〕"
            category = await guild.create_category(cat_name)
            await asyncio.sleep(2)
            
            for ch in category_data.get("channels", []):
                full_name = f"{ch.get('emoji', '')}┃{ch['name']}"
                if ch['type'] == 'voice':
                    await guild.create_voice_channel(full_name, category=category)
                else:
                    await guild.create_text_channel(full_name, category=category)
                count += 1
                await asyncio.sleep(3) 

        await interaction.edit_original_response(content=f"✅ **Done!** AI built {count} channels for you. Press `Cmd + R` to refresh Discord.")

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ AI Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

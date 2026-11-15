import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import json
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

@bot.tree.command(name="build", description="Tell the AI what kind of server you want")
async def build(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    await interaction.edit_original_response(content="🧠 AI is thinking...")

    system_prompt = """
    Output ONLY JSON. Format:
    {"categories": [{"name": "CATEGORY NAME", "channels": [{"name": "channel-name", "emoji": "💬", "type": "text"}]}]}
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
        await interaction.edit_original_response(content="🔧 Building channels now... (Slowly to avoid Discord limits)")

        count = 0
        for cat in layout.get("categories", []):
            category = await interaction.guild.create_category(f"〔✨ {cat['name']} 〕")
            await asyncio.sleep(2)
            
            for ch in cat.get("channels", []):
                name = f"{ch.get('emoji', '')}┃{ch['name']}"
                if ch['type'] == 'voice':
                    await interaction.guild.create_voice_channel(name, category=category)
                else:
                    await interaction.guild.create_text_channel(name, category=category)
                count += 1
                await asyncio.sleep(2)

        await interaction.edit_original_response(content=f"✅ Done! Built {count} channels. Refresh Discord (Cmd+R).")

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

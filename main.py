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

# Store the last action so we can Undo it
last_actions = {}

# --- THE UNDO BUTTON ---
class UndoView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300) # Button lasts for 5 minutes
        self.guild_id = guild_id

    @discord.ui.button(label="Undo", style=discord.ButtonStyle.danger)
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.guild_id in last_actions:
            await interaction.response.defer()
            guild = interaction.guild
            
            # Restore the old names
            for channel_id, old_name in last_actions[self.guild_id].items():
                channel = guild.get_channel(channel_id)
                if channel:
                    await channel.edit(name=old_name)
                    await asyncio.sleep(2) # Avoid rate limits
            
            del last_actions[self.guild_id]
            await interaction.edit_original_response(content="✅ Successfully undid the last action.", view=None)
        else:
            await interaction.response.send_message("❌ Nothing to undo!", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Bot online!")

# --- THE SMART COMMAND ---
@bot.tree.command(name="tidy", description="Use AI to tidy up your channels")
@app_commands.describe(prompt="E.g., 'Move all old channels to an ARCHIVE category' or 'Make everything emoji based'")
async def tidy(interaction: discord.Interaction, prompt: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    await interaction.response.defer()
    await interaction.edit_original_response(content="🧠 **AI is analyzing your server...**")

    guild = interaction.guild
    
    # Gather current server structure for the AI to read
    server_state = []
    for cat in guild.categories:
        cat_channels = [ch.name for ch in cat.channels]
        server_state.append(f"Category: {cat.name} | Channels: {', '.join(cat_channels)}")
        
    system_prompt = f"""
    You are an AI Discord manager. The user wants to tidy up their server. 
    Here is the current server state:
    {chr(10).join(server_state)}
    
    The user's request: {prompt}
    
    Output ONLY a JSON object with a list of "actions" to perform.
    Formats allowed:
    1. Rename: {{"action": "rename", "channel_id": 123, "new_name": "new-name"}}
    2. Move: {{"action": "move", "channel_id": 123, "new_category": "Category Name"}}
    
    Example output:
    {{"actions": [{{"action": "rename", "channel_id": 123, "new_name": "📚┃rules"}}]}}
    """

    try:
        response = await ai_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"}
        )
        
        ai_data = json.loads(response.choices[0].message.content)
        actions = ai_data.get("actions", [])
        
        if not actions:
            await interaction.edit_original_response(content="😴 AI decided no changes were needed.")
            return

        # Save state for UNDO
        last_actions[guild.id] = {ch.id: ch.name for ch in guild.channels}

        steps_done = []
        
        for act in actions:
            ch = guild.get_channel(act["channel_id"])
            if not ch: continue

            if act["action"] == "rename":
                await ch.edit(name=act["new_name"])
                steps_done.append(f"Renamed {ch.name} to {act['new_name']}")
                await asyncio.sleep(2)

            elif act["action"] == "move":
                category = discord.utils.get(guild.categories, name=act["new_category"])
                if not category:
                    category = await guild.create_category(act["new_category"])
                await ch.edit(category=category)
                steps_done.append(f"Moved {ch.name} to {act['new_category']}")
                await asyncio.sleep(2)

        # Create the final success embed
        embed = discord.Embed(
            title="✅ AI Finished Task",
            description=f"**{len(steps_done)} steps done**",
            color=discord.Color.green()
        )
        embed.add_field(name="Changes made:", value="\n".join([f"✓ {s}" for s in steps_done[:10]]), inline=False)
        
        # Add the Undo Button
        view = UndoView(guild.id)
        await interaction.edit_original_response(content=None, embed=embed, view=view)

    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))

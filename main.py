import asyncio
import json
import os
from contextlib import asynccontextmanager

import discord
import httpx
import uvicorn
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
undo_snapshots: dict[int, list[str]] = {}


def get_ai_client() -> AsyncOpenAI:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured in Railway Variables")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    token = os.getenv("DISCORD_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
    else:
        print("DISCORD_TOKEN is missing")
    yield
    if not bot.is_closed():
        await bot.close()


app = FastAPI(title="Rynnzyr Discord Architect", lifespan=lifespan)


class GuildRequest(BaseModel):
    guild_id: int
    prompt: str = ""


class PlanRequest(BaseModel):
    guild_id: int
    prompt: str = Field(min_length=3, max_length=1000)


ChatRequest = PlanRequest


class ApplyRequest(BaseModel):
    guild_id: int
    plan: dict


@app.get("/")
def serve_website():
    try:
        with open("index.html", encoding="utf-8") as website:
            response = HTMLResponse(website.read())
    except FileNotFoundError:
        raise HTTPException(500, "index.html is missing from the deployment")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/login")
def login():
    if not all((CLIENT_ID, REDIRECT_URI)):
        return HTMLResponse("Missing CLIENT_ID or REDIRECT_URI", status_code=500)
    from urllib.parse import urlencode
    query = urlencode({"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "identify guilds"})
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{query}")


@app.get("/callback")
async def callback(code: str | None = None):
    if not code:
        return RedirectResponse("/?error=auth_failed")
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
    async with httpx.AsyncClient() as client:
        response = await client.post("https://discord.com/api/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = response.json().get("access_token")
    if not token:
        return RedirectResponse("/?error=auth_failed")
    redirect = RedirectResponse("/?logged_in=true")
    redirect.set_cookie("discord_token", token, httponly=True, samesite="lax", max_age=604800)
    return redirect


@app.get("/api/user-guilds")
async def user_guilds(request: Request):
    if not bot.is_ready():
        return {"error": "The Discord bot is starting. Please try again."}
    access_token = request.cookies.get("discord_token")
    if not access_token:
        raise HTTPException(401, "Not logged in")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://discord.com/api/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200:
        raise HTTPException(401, "Discord login expired")
    result = []
    for user_guild in response.json():
        permissions = int(user_guild.get("permissions", 0))
        if not (permissions & 0x8 or permissions & 0x20):
            continue
        guild_id = int(user_guild["id"])
        has_bot = bot.get_guild(guild_id) is not None
        result.append({"id": guild_id, "name": user_guild["name"], "icon": user_guild.get("icon"), "has_bot": has_bot,
                       "invite_url": None if has_bot else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={guild_id}"})
    return {"guilds": result}


def guild_or_error(guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    member = guild.me
    if member is None:
        raise HTTPException(503, "Bot membership is not available yet")
    if not member.guild_permissions.manage_channels:
        raise HTTPException(403, "Bot needs Manage Channels permission")
    if not member.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Roles permission")
    return guild


def is_voice_channel(channel) -> bool:
    # discord.py uses VoiceChannel and StageChannel; VocalGuildChannel is not public API.
    return isinstance(channel, (discord.VoiceChannel, discord.StageChannel))


def safe_state(guild: discord.Guild) -> dict:
    roles = [{"name": role.name, "position": role.position} for role in guild.roles if not role.managed]
    categories = [{"name": category.name, "channels": [{"name": channel.name, "type": "voice" if is_voice_channel(channel) else "text"} for channel in category.channels]}
                  for category in guild.categories[:30]]
    return {"name": guild.name, "roles": roles[-20:], "categories": categories,
            "uncategorized": [{"name": channel.name, "type": "voice" if is_voice_channel(channel) else "text"} for channel in guild.channels
                               if channel.category is None and isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel))][:30]}


def sanitize_name(value, fallback="community"):
    text = str(value or "").strip().lower()
    text = "".join(char if char.isalnum() or char in "-_ " else "-" for char in text)
    text = "-".join(text.split())[:100].strip("-")
    return text or fallback


def sanitize_plan(plan: dict) -> dict:
    roles = []
    for item in (plan.get("roles") or [])[:8]:
        if not isinstance(item, dict):
            continue
        name = sanitize_name(item.get("name"), "member").replace("-", " ").title()
        if name.lower() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "#5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name[:100], "color": max(0, min(color, 0xFFFFFF)), "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})
    categories = []
    for item in (plan.get("categories") or [])[:12]:
        if not isinstance(item, dict):
            continue
        channels = []
        for channel in (item.get("channels") or [])[:8]:
            if not isinstance(channel, dict):
                continue
            channel_type = "voice" if channel.get("type") == "voice" else "text"
            channels.append({"name": sanitize_name(channel.get("name")), "type": channel_type,
                             "topic": str(channel.get("topic") or "")[:1024] if channel_type == "text" else ""})
        categories.append({"name": str(item.get("name") or "Community")[:100], "channels": channels})
    return {"summary": str(plan.get("summary") or "Professional server layout")[:500], "roles": roles, "categories": categories}


async def generate_plan(guild: discord.Guild, prompt: str) -> dict:
    system_prompt = f"""
You are Rynnzyr, an expert Discord server architect. Design a polished server for the user's request.
Return only valid JSON with this schema:
{{"summary":"short explanation","roles":[{{"name":"Role","color":"#5865F2","hoist":false,"mentionable":false}}],"categories":[{{"name":"Category","channels":[{{"name":"channel-name","type":"text or voice","topic":"optional"}}]}}]}}
Limits: 8 roles, 12 categories, 8 channels/category. Never create administrator-permission roles. Keep names concise.
Current server: {json.dumps(safe_state(guild), ensure_ascii=False)}
"""
    response = await get_ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        temperature=0.35, max_tokens=1800, response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    return sanitize_plan(json.loads(content))


async def apply_guild_plan(guild: discord.Guild, plan: dict) -> list[str]:
    plan = sanitize_plan(plan)
    created_ids = []
    created = []
    for spec in plan["roles"]:
        if discord.utils.get(guild.roles, name=spec["name"]):
            continue
        role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr AI server architect")
        created_ids.append(f"role:{role.id}")
        created.append(f"Role: {role.name}")
    for category_spec in plan["categories"]:
        category = discord.utils.get(guild.categories, name=category_spec["name"])
        if category is None:
            category = await guild.create_category(category_spec["name"], reason="Created by Rynnzyr AI server architect")
            created_ids.append(f"category:{category.id}")
            created.append(f"Category: {category.name}")
        for channel_spec in category_spec["channels"]:
            if discord.utils.get(category.channels, name=channel_spec["name"]):
                continue
            if channel_spec["type"] == "voice":
                channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Created by Rynnzyr AI server architect")
            else:
                channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec["topic"] or None, reason="Created by Rynnzyr AI server architect")
            created_ids.append(f"channel:{channel.id}")
            created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            await asyncio.sleep(0.35)
    undo_snapshots[guild.id] = created_ids
    return created


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    guild = guild_or_error(req.guild_id)
    try:
        return {"plan": await generate_plan(guild, req.prompt)}
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    guild = guild_or_error(req.guild_id)
    try:
        return {"success": True, "created": await apply_guild_plan(guild, req.plan)}
    except discord.Forbidden:
        raise HTTPException(403, "Bot is missing Discord permissions")
    except discord.HTTPException as exc:
        raise HTTPException(502, f"Discord rejected a change: {exc.text}")


@app.post("/api/undo")
async def undo(req: GuildRequest):
    guild = guild_or_error(req.guild_id)
    ids = undo_snapshots.pop(guild.id, [])
    if not ids:
        return {"error": "Nothing to undo"}
    deleted = 0
    for identifier in reversed(ids):
        kind, item_id = identifier.split(":", 1)
        object_id = int(item_id)
        item = discord.utils.get(guild.roles, id=object_id) if kind == "role" else guild.get_channel(object_id)
        if item:
            try:
                await item.delete(reason="Undo by Rynnzyr AI server architect")
                deleted += 1
                await asyncio.sleep(0.25)
            except discord.Forbidden:
                continue
    return {"success": True, "deleted": deleted}


@bot.tree.command(name="ping", description="Check that Rynnzyr is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Rynnzyr is online and ready.", ephemeral=True)


@bot.tree.command(name="design", description="Ask Rynnzyr AI to design and build this server")
@app_commands.describe(prompt="Describe the server you want Rynnzyr to build")
async def design(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
        await interaction.response.send_message("You need Manage Server permission to use this command.", ephemeral=True)
        return
    bot_member = interaction.guild.me
    if bot_member is None or not (bot_member.guild_permissions.manage_channels and bot_member.guild_permissions.manage_roles):
        await interaction.response.send_message("I need Manage Channels and Manage Roles permissions.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        plan = await generate_plan(interaction.guild, prompt[:1000])
        created = await apply_guild_plan(interaction.guild, plan)
        summary = "\n".join(f"• {item}" for item in created[:30]) or "No changes were needed; the design already exists."
        await interaction.followup.send(f"**{plan['summary']}**\n{summary}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Discord denied a change. Check my Manage Channels/Manage Roles permissions and role position.", ephemeral=True)
    except Exception as exc:
        print(f"/design failed: {type(exc).__name__}: {exc}")
        message = str(exc) if "GROQ_API_KEY" in str(exc) else "I couldn't build that layout. Check Railway logs and your AI API configuration."
        await interaction.followup.send(message[:1800], ephemeral=True)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot online as {bot.user}; synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Failed to sync application commands: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

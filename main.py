import asyncio
import os
from contextlib import asynccontextmanager
from typing import Literal

import discord
import httpx
import uvicorn
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

aio = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

undo_snapshots: dict[int, list[str]] = {}


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


class ApplyRequest(BaseModel):
    guild_id: int
    plan: dict


@app.get("/")
def serve_website():
    response = HTMLResponse(open("index.html", "r", encoding="utf-8").read())
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/login")
def login():
    if not all((CLIENT_ID, REDIRECT_URI)):
        return HTMLResponse("Missing CLIENT_ID or REDIRECT_URI", status_code=500)
    return RedirectResponse(
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        "&response_type=code&scope=identify%20guilds"
    )


@app.get("/callback")
async def callback(code: str | None = None):
    if not code:
        return RedirectResponse("/?error=auth_failed")
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://discord.com/api/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
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
        response = await client.get(
            "https://discord.com/api/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code != 200:
        raise HTTPException(401, "Discord login expired")

    bot_guilds = {guild.id: guild for guild in bot.guilds}
    result = []
    for guild in response.json():
        permissions = int(guild.get("permissions", 0))
        is_admin = bool(permissions & 0x8)
        can_manage = bool(permissions & 0x20)
        if not (is_admin or can_manage):
            continue
        guild_id = int(guild["id"])
        has_bot = guild_id in bot_guilds
        result.append({
            "id": guild_id,
            "name": guild["name"],
            "icon": guild.get("icon"),
            "has_bot": has_bot,
            "invite_url": None if has_bot else (
                "https://discord.com/api/oauth2/authorize"
                f"?client_id={CLIENT_ID}&permissions=402653184&scope=bot%20applications.commands"
                f"&guild_id={guild_id}"
            ),
        })
    return {"guilds": result}


def guild_or_error(guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(404, "Bot is not in this server")
    if not guild.me.guild_permissions.manage_channels:
        raise HTTPException(403, "Bot needs Manage Channels permission")
    if not guild.me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Roles permission")
    return guild


def safe_state(guild: discord.Guild) -> dict:
    roles = [{"name": role.name, "position": role.position} for role in guild.roles if not role.managed]
    categories = []
    for category in guild.categories:
        categories.append({
            "name": category.name,
            "channels": [{"name": channel.name, "type": "voice" if isinstance(channel, discord.VocalGuildChannel) else "text"}
                          for channel in category.channels],
        })
    uncategorized = [{"name": channel.name, "type": "voice" if isinstance(channel, discord.VocalGuildChannel) else "text"}
                     for channel in guild.channels if channel.category is None and isinstance(channel, (discord.TextChannel, discord.VocalGuildChannel))]
    return {"name": guild.name, "roles": roles[-20:], "categories": categories[:30], "uncategorized": uncategorized[:30]}


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    guild = guild_or_error(req.guild_id)
    state = safe_state(guild)
    system_prompt = f"""
You are Rynnzyr, an expert Discord server architect.
Design a complete, polished server from the user's request.
Only return valid JSON, no markdown and no commentary.
Use this exact schema:
{{
  "summary": "short explanation",
  "roles": [{{"name":"Role Name","color":"#5865F2","hoist":false,"mentionable":false}}],
  "categories": [{{
    "name":"Category Name",
    "channels":[{{"name":"channel-name","type":"text"|"voice","topic":"optional"}}]
  }}]
}}
Limits: max 8 roles, max 12 categories, max 8 channels per category.
Prefer useful standard roles: Admin, Moderator, Member, Community.
Do not include @everyone, administrator, bot, or dangerous permission roles.
Keep names concise and Discord-friendly.
Existing server state:
{state}
"""
    try:
        response = await aio.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.prompt},
            ],
            temperature=0.35,
            max_tokens=1800,
            response_format={"type": "json_object"},
        )
        import json
        plan = json.loads(response.choices[0].message.content)
        plan = sanitize_plan(plan)
        return {"plan": plan}
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


def sanitize_name(value, fallback="Community"):
    text = str(value or "").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in "-_ " else "-" for ch in text)
    text = "-".join(text.split())[:100].strip("-")
    return text or fallback.lower()


def sanitize_plan(plan: dict) -> dict:
    roles = []
    for item in (plan.get("roles") or [])[:8]:
        name = sanitize_name(item.get("name"), "Member").replace("-", " ").title()
        if name.lower() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "#5865F2")).lstrip("#"), 16)
        except ValueError:
            color = 0x5865F2
        roles.append({"name": name[:100], "color": color, "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})

    categories = []
    for item in (plan.get("categories") or [])[:12]:
        name = str(item.get("name") or "Community")[:100]
        channels = []
        for channel in (item.get("channels") or [])[:8]:
            channel_type = "voice" if channel.get("type") == "voice" else "text"
            channels.append({
                "name": sanitize_name(channel.get("name")),
                "type": channel_type,
                "topic": str(channel.get("topic") or "")[:1024] if channel_type == "text" else "",
            })
        categories.append({"name": name, "channels": channels})
    return {"summary": str(plan.get("summary") or "Professional server layout")[:500], "roles": roles, "categories": categories}


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    guild = guild_or_error(req.guild_id)
    plan = sanitize_plan(req.plan)
    created_ids: list[str] = []
    created = []

    member_role = guild.default_role
    try:
        for role_spec in plan["roles"]:
            existing = discord.utils.get(guild.roles, name=role_spec["name"])
            if existing:
                continue
            role = await guild.create_role(
                name=role_spec["name"][:100],
                colour=discord.Colour(role_spec["color"]),
                hoist=role_spec["hoist"],
                mentionable=role_spec["mentionable"],
                reason="Created by Rynnzyr AI server architect",
            )
            created_ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")

        for category_spec in plan["categories"]:
            category = discord.utils.get(guild.categories, name=category_spec["name"])
            if not category:
                category_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=True),
                }
                category = await guild.create_category(
                    category_spec["name"],
                    overwrites=category_overwrites,
                    reason="Created by Rynnzyr AI server architect",
                )
                created_ids.append(f"category:{category.id}")
                created.append(f"Category: {category.name}")

            for channel_spec in category_spec["channels"]:
                existing = discord.utils.get(category.channels, name=channel_spec["name"])
                if existing:
                    continue
                if channel_spec["type"] == "voice":
                    channel = await guild.create_voice_channel(
                        channel_spec["name"], category=category,
                        reason="Created by Rynnzyr AI server architect",
                    )
                else:
                    channel = await guild.create_text_channel(
                        channel_spec["name"], category=category,
                        topic=channel_spec["topic"] or None,
                        reason="Created by Rynnzyr AI server architect",
                    )
                created_ids.append(f"channel:{channel.id}")
                created.append(f"{'Voice' if channel_spec['type'] == 'voice' else 'Text'}: {channel_spec['name']}")
                await asyncio.sleep(0.35)
    except discord.Forbidden:
        raise HTTPException(403, "The bot is missing Discord permissions")
    except discord.HTTPException as exc:
        raise HTTPException(502, f"Discord rejected a change: {exc.text}")

    undo_snapshots[guild.id] = created_ids
    return {"success": True, "created": created, "summary": plan["summary"]}


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
        if kind == "role":
            item = discord.utils.get(guild.roles, id=object_id)
        elif kind == "category":
            item = discord.utils.get(guild.categories, id=object_id)
        else:
            item = guild.get_channel(object_id)
        if item:
            try:
                await item.delete(reason="Undo by Rynnzyr AI server architectt")
                deleted += 1
                await asyncio.sleep(0.25)
            except discord.Forbidden:
                pass
    return {"success": True, "deleted": deleted}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    return await create_plan(req)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

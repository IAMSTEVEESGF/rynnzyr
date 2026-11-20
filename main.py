import asyncio
import json
import os
import re
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

CORE = [
    ("staff", "──── ⟪STAFF GENERAL⟫ ────", True, [("📚", "staff-rules", "text"), ("📣", "staff-announcements", "text"), ("💬", "staff-chat", "text"), ("🎉", "staff-promotions", "text"), ("🗂️", "staff-logs", "text"), ("⚠️", "staff-demotions", "text"), ("🎙️", "staff-vc", "voice")]),
    ("welcome", "──── ⟪WELCOME⟫ ────", False, [("🛤️", "invite-tracker", "text"), ("👋", "welcome", "text"), ("🕊️", "goodbye", "text")]),
    ("verification", "──── ⟪VERIFICATION⟫ ────", False, [("✅", "verification", "text")]),
    ("important", "──── ⟪IMPORTANT⟫ ────", False, [("📚", "rules", "text"), ("📣", "announcements", "text"), ("📊", "sab-leaks", "text"), ("🚀", "server-boosts", "text"), ("⚡", "boosters-rewards", "text"), ("📊", "polls", "text"), ("⚠️", "scammers", "text"), ("📝", "applications", "text"), ("🔄", "server-updates", "text"), ("🏅", "hall-of-fame", "text"), ("🎬", "content", "text"), ("🎟️", "support-ticket", "text")]),
    ("middleman", "──── ⟪MIDDLEMAN⟫ ────", False, [("💫", "verified-middleman", "text"), ("🎫", "middleman-ticket", "text"), ("✅", "middleman-vouches", "text")]),
    ("giveaways", "──── ⟪GIVEAWAYS⟫ ────", False, [("🎉", "giveaways", "text"), ("🎰", "flash-giveaways", "text"), ("📸", "giveaways-vouches", "text"), ("🎮", "giveaways-vc", "voice")]),
    ("general", "──── ⟪GENERAL⟫ ────", False, [("💬", "general", "text"), ("📸", "media", "text"), ("⚙️", "commands", "text"), ("📊", "levels", "text"), ("🛠️", "suggestions", "text")]),
]
EMOJI_RULES = {"announcement":"📣","rules":"📚","leak":"📊","poll":"🗳️","boost":"🚀","reward":"🎁","scam":"⚠️","application":"📝","update":"🔄","hall":"🏅","content":"🎬","support":"🎟️","ticket":"🎫","middleman":"🤝","verified":"✅","vouch":"✅","giveaway":"🎁","invite":"🛤️","welcome":"👋","goodbye":"🕊️","general":"💬","chat":"🗨️","media":"📸","photo":"📷","video":"🎥","clip":"🎞️","stream":"📡","meme":"😂","suggest":"🛠️","feedback":"📝","help":"🆘","faq":"❓","bug":"🐛","staff":"🛡️","log":"🗂️","trade":"💱","market":"🛒","shop":"🏪","sell":"🏷️","buy":"💰","auction":"🔨","report":"🚨","level":"📈","leaderboard":"🏆","command":"⚙️","bot":"🤖","voice":"🔊","music":"🎵","game":"🎮","roblox":"🧱","squad":"🪖","team":"👥","match":"⚔️","tournament":"🏆","fan":"💖","art":"🎨","creator":"✨","collab":"🤝","event":"📅","guide":"🧭","idea":"💡"}
FALLBACK_EMOJIS = ["🌟","🧩","🪄","🧿","🌈","🪐","🦋","🍀","🔥","💎","🧸","🪷","🌙","🎨","🪙","🧠","🪁","💫","🔮","🧵","🎪","🪸","🪻","🧃","🧊","🧪","🧭"]


def clean_text(value, limit=100):
    text = str(value or "").replace("@everyone", "everyone").replace("@here", "here")
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    return " ".join(text.split())[:limit].strip()


def slug(value):
    text = clean_text(value, 120).casefold()
    text = re.sub(r"^[〔【\[（(].*?[〕】\]）)]\s*[・•|:：-]*\s*", "", text)
    text = re.sub(r"^[^\w]+", "", text, flags=re.UNICODE).replace("_", "-")
    text = "".join(c if c.isalnum() or c in "- " else "-" for c in text)
    return "-".join(text.split()).strip("-")[:72] or "channel"


def key(value):
    return "".join(c for c in slug(value) if c.isalnum())


def icon_for(name, used):
    name = slug(name)
    for word, icon in sorted(EMOJI_RULES.items(), key=lambda pair: len(pair[0]), reverse=True):
        if word in name and icon not in used:
            used.add(icon)
            return icon
    offset = sum(ord(c) for c in name) % len(FALLBACK_EMOJIS)
    for i in range(len(FALLBACK_EMOJIS)):
        icon = FALLBACK_EMOJIS[(offset + i) % len(FALLBACK_EMOJIS)]
        if icon not in used:
            used.add(icon)
            return icon
    return "✨"


def detect_prompt(prompt):
    text = prompt.casefold()
    roblox = "roblox" in text
    brainrot = "steal a brainrot" in text or "brainrot" in text
    trade = any(word in text for word in ("trade", "trading", "market", "middleman", "sell", "buy", "auction", "robux", "item exchange"))
    content = any(word in text for word in ("content", "clips", "videos", "media", "stream", "youtube", "tiktok")) or roblox
    creators = any(word in text for word in ("creator", "creators", "artist", "art", "streamer", "influencer", "youtuber")) or roblox
    return {"roblox": roblox, "brainrot": brainrot, "trade": trade or roblox, "content": content, "creators": creators}


def get_ai_client():
    token = os.getenv("GROQ_API_KEY")
    if not token:
        raise RuntimeError("GROQ_API_KEY is not configured in Railway Variables")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=token)


@asynccontextmanager
async def lifespan(app):
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
    try:
        with open("index.html", encoding="utf-8") as page:
            response = HTMLResponse(page.read())
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
    token = request.cookies.get("discord_token")
    if not token:
        raise HTTPException(401, "Not logged in")
    async with httpx.AsyncClient() as client:
        response = await client.get("https://discord.com/api/users/@me/guilds", headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise HTTPException(401, "Discord login expired")
    result = []
    for item in response.json():
        permissions = int(item.get("permissions", 0))
        if not (permissions & 0x8 or permissions & 0x20):
            continue
        gid = int(item["id"])
        has_bot = bot.get_guild(gid) is not None
        result.append({"id": gid, "name": item["name"], "icon": item.get("icon"), "has_bot": has_bot,
                       "invite_url": None if has_bot else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={gid}"})
    return {"guilds": result}


def get_guild(guild_id):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    if guild.me is None or not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Channels and Manage Roles")
    return guild


def safe_state(guild):
    return {
        "name": guild.name,
        "categories": [
            {"name": category.name, "channels": [channel.name for channel in category.channels]}
            for category in guild.categories[:30]
        ],
    }


def add_category(categories, name, definitions, *, staff_only=False):
    used, channels = set(), []
    for icon, channel_name, kind, topic in definitions:
        channel_name = slug(channel_name)
        icon = icon or icon_for(channel_name, used)
        used.add(icon)
        channels.append({"name": f"〔{icon}〕・{channel_name}", "type": kind,
                         "topic": clean_text(topic, 1024) if kind == "text" else ""})
    if channels:
        categories.append({"name": name, "staff_only": staff_only, "channels": channels})


def sanitize_plan(plan, prompt):
    if not isinstance(plan, dict):
        plan = {}
    context = detect_prompt(prompt)
    roles = []
    for item in (plan.get("roles") or [])[:8]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        if not name or name.casefold() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name, "color": max(0, min(color, 0xFFFFFF)), "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})

    categories, used_channels = [], set()
    for _, name, private, definitions in CORE:
        entries = []
        for icon, channel_name, kind in definitions:
            entries.append({"name": f"〔{icon}〕・{channel_name}", "type": kind, "topic": ""})
            used_channels.add(key(channel_name))
        categories.append({"name": name, "staff_only": private, "channels": entries})

    custom = []
    if context["content"]:
        prefix = "roblox" if context["roblox"] else ""
        definitions = [("🎬", f"{prefix}-content-drops" if prefix else "content-drops", "text", "Share community updates, clips, and creations."),
                       ("🎞️", f"{prefix}-clips" if prefix else "clips", "text", "Post short clips and highlights."),
                       ("📸", f"{prefix}-screenshots" if prefix else "screenshots", "text", "Share screenshots and images.")]
        add_category(custom, "🎬 : CONTENT : ✨", definitions)
    if context["creators"]:
        prefix = "roblox" if context["roblox"] else ""
        definitions = [("✨", f"{prefix}-creator-showcase" if prefix else "creator-showcase", "text", "Showcase original work and projects."),
                       ("🤝", "collab-requests", "text", "Find people for creative collaborations."),
                       ("📣", "creator-updates", "text", "Share creator news and releases.")]
        add_category(custom, "✨ : CREATORS ONLY : 🌙", definitions)
    if context["trade"]:
        prefix = "roblox" if context["roblox"] else "community"
        definitions = [("💱", f"{prefix}-trade-chat", "text", "Discuss fair trades; follow game/platform rules."),
                       ("🛒", f"{prefix}-trade-offers", "text", "Post clear offers and requests."),
                       ("✅", "trade-vouches", "text", "Share completed-trade feedback."),
                       ("🛡️", "trade-safety", "text", "Read safety guidance and report suspicious trades.")]
        add_category(custom, "💱 : TRADING : 🛒", definitions)

    extras, used_categories = [], set()
    raw_categories = plan.get("categories") if isinstance(plan.get("categories"), list) else []
    for category in raw_categories[:6]:
        if not isinstance(category, dict):
            continue
        title = clean_text(category.get("name"), 100)
        title_key = key(title)
        if not title or any(core_name in title_key for core_name in ("staffgeneral", "welcome", "verification", "important", "middleman", "giveaways", "general")):
            continue
        if title_key in used_categories or any(title_key in key(existing["name"]) or key(existing["name"]) in title_key for existing in custom):
            continue
        if "brainrot" in title.casefold() and not context["brainrot"]:
            continue
        used_categories.add(title_key)
        used_icons, text_entries = set(), []
        channels = category.get("channels") if isinstance(category.get("channels"), list) else []
        for channel in channels[:10]:
            if not isinstance(channel, dict):
                continue
            channel_slug = slug(channel.get("name"))
            if "brainrot" in channel_slug and not context["brainrot"]:
                continue
            normalized = key(channel_slug)
            if not normalized or normalized in used_channels:
                continue
            used_channels.add(normalized)
            kind = "voice" if channel.get("type") == "voice" else "text"
            if kind == "voice":
                continue  # all voice chats are consolidated into the final category
            icon = icon_for(channel_slug, used_icons)
            text_entries.append({"name": f"〔{icon}〕・{channel_slug}", "type": "text", "topic": clean_text(channel.get("topic"), 1024)})
        if text_entries:
            extras.append({"name": title, "staff_only": False, "channels": text_entries})

    categories.extend(custom)
    categories.extend(extras)
    if context["roblox"]:
        voice_defaults = [("🎮", "roblox-game-voice"), ("🗣️", "community-voice"), ("🎙️", "creator-voice")]
    else:
        voice_defaults = [("🎙️", "community-voice"), ("🎮", "gaming-voice"), ("🎵", "music-voice")]
    voice_channels, voice_seen = [], set()
    for icon, name in voice_defaults:
        voice_seen.add(key(name))
        voice_channels.append({"name": f"〔{icon}〕・{name}", "type": "voice", "topic": ""})
    for category in raw_categories:
        if not isinstance(category, dict):
            continue
        raw_voice = category.get("channels") if isinstance(category.get("channels"), list) else []
        for channel in raw_voice:
            if not isinstance(channel, dict) or channel.get("type") != "voice":
                continue
            channel_slug = slug(channel.get("name"))
            if "brainrot" in channel_slug and not context["brainrot"]:
                continue
            channel_key = key(channel_slug)
            if channel_key and channel_key not in voice_seen:
                voice_seen.add(channel_key)
                icon = icon_for(channel_slug, set())
                voice_channels.append({"name": f"〔{icon}〕・{channel_slug}", "type": "voice", "topic": ""})
    categories.append({"name": "🎙️ : VOICE LOUNGE : 🎧", "staff_only": False, "channels": voice_channels})
    return {"summary": clean_text(plan.get("summary") or "A tailored community server blueprint", 500), "roles": roles, "categories": categories}


async def generate_plan(guild, prompt):
    context = detect_prompt(prompt)
    response = await get_ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[{"role": "system", "content": f"""
You are a careful Discord community architect. Return JSON only with summary, roles, categories.
The app always creates fixed sections in order: STAFF GENERAL (private), WELCOME, VERIFICATION, IMPORTANT, MIDDLEMAN, GIVEAWAYS, GENERAL (ends at suggestions). It then adds prompt-relevant CONTENT, CREATORS ONLY, TRADING, optional custom categories, then the final VOICE LOUNGE. Do not output those sections. Create at most 3 additional prompt-specific text-only categories.
Prompt context: {json.dumps(context)}. Roblox means the platform generally: never invent a specific Roblox game such as Steal a Brainrot unless the prompt explicitly names it. Be precise to the user's prompt, avoid filler and unrelated games. Do not duplicate existing channels: {json.dumps(safe_state(guild), ensure_ascii=False)}.
Schema: {{"summary":"...","roles":[{{"name":"Member","color":"5865F2"}}],"categories":[{{"name":"🎮 : ROBLOX HANGOUT : 🎮","channels":[{{"name":"game-chat","type":"text","topic":"..."}}]}}]}}
No voice channels; code ensures a final voice lounge. Do not create any permissions/admin roles.
"""}, {"role": "user", "content": prompt}],
        temperature=0.3, max_tokens=3000, response_format={"type": "json_object"})
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    return sanitize_plan(json.loads(content), prompt)


async def lifespan(app):
    token = os.getenv("DISCORD_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
    else:
        print("DISCORD_TOKEN is missing")
    yield
    if not bot.is_closed():
        await bot.close()


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    try:
        return {"plan": await generate_plan(get_guild(req.guild_id), req.prompt)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


def is_category(channel):
    return isinstance(channel, discord.CategoryChannel)


def is_regular_channel(channel):
    return not is_category(channel) and isinstance(channel, discord.abc.GuildChannel)


async def delete_existing_layout(guild):
    for channel in list(guild.channels):
        if is_regular_channel(channel):
            await channel.delete(reason="User-confirmed Rynnzyr rebuild")
            await asyncio.sleep(0.2)
    for category in reversed(list(guild.categories)):
        await category.delete(reason="User-confirmed Rynnzyr rebuild")
        await asyncio.sleep(0.2)


async def build_fresh_layout(guild, plan):
    await delete_existing_layout(guild)
    created_ids, created = [], []
    roles = {}
    role_specs = list(plan.get("roles", []))
    if not any("staff" in role.get("name", "").casefold() for role in role_specs):
        role_specs.append({"name": "Staff", "color": 0x5865F2, "hoist": False, "mentionable": False})
    for spec in role_specs:
        role = discord.utils.get(guild.roles, name=spec["name"])
        if role is None:
            role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr")
            created_ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")
        roles[role.name.casefold()] = role
    staff_role = roles.get("staff") or discord.utils.get(guild.roles, name="Staff")

    # Create top-level categories sequentially; no category is ever a category's parent.
    for spec in plan["categories"]:
        overwrites = {}
        if spec.get("staff_only"):
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                          staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)}
        category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Fresh Rynnzyr layout")
        created_ids.append(f"category:{category.id}")
        created.append(f"Category: {category.name}" + (" (staff-only)" if spec.get("staff_only") else ""))
        for channel_spec in spec["channels"]:
            if channel_spec["type"] == "voice":
                channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Fresh Rynnzyr layout")
            else:
                channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec.get("topic") or None, reason="Fresh Rynnzyr layout")
            created_ids.append(f"channel:{channel.id}")
            created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            await asyncio.sleep(0.2)
    undo_snapshots[guild.id] = created_ids
    return created


def make_embed(guild, plan):
    embed = discord.Embed(title=f"✨ {guild.name} — Server blueprint", description=plan["summary"], color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if item["type"] == "voice" else "# ") + item["name"] for item in category["channels"]]
        if category.get("staff_only"):
            lines.append("🔒 Staff-only — access through Staff role")
        embed.add_field(name=category["name"], value=("\n".join(lines) or "No channels")[:1024], inline=True)
    embed.set_footer(text="WARNING: confirmation permanently deletes all existing channels and categories.")
    return embed


class RebuildView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild, self.plan, self.author_id, self.done = guild, plan, author_id, False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the requesting manager can confirm this destructive rebuild.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Delete all channels & rebuild", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def rebuild(self, interaction, button):
        if self.done:
            await interaction.response.send_message("This blueprint was already handled.", ephemeral=True)
            return
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Rebuild confirmed. Removing old channels and creating the ordered layout…", view=self)
        try:
            changes = await build_fresh_layout(self.guild, self.plan)
            summary = "\n".join(f"• {line}" for line in changes[:35])
            await interaction.followup.send(f"✅ **Fresh layout created.**\n{summary}", ephemeral=True)
        except Exception as exc:
            print(f"Fresh rebuild failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send(f"Rebuild stopped: {type(exc).__name__}: {str(exc)[:600]}. Some existing channels may already be deleted; inspect the server before retrying.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction, button):
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Rebuild cancelled. No server changes were made.", embed=None, view=self)


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    raise HTTPException(409, "Destructive rebuild is only available after explicit confirmation in the Discord preview.")


@app.post("/api/undo")
async def undo(req: GuildRequest):
    guild = get_guild(req.guild_id)
    ids = undo_snapshots.pop(guild.id, [])
    deleted = 0
    for entry in reversed(ids):
        kind, raw_id = entry.split(":", 1)
        item = discord.utils.get(guild.roles, id=int(raw_id)) if kind == "role" else guild.get_channel(int(raw_id))
        if item:
            try:
                await item.delete(reason="Undo by Rynnzyr")
                deleted += 1
                await asyncio.sleep(0.2)
            except discord.Forbidden:
                pass
    return {"success": True, "deleted": deleted}


@bot.tree.command(name="ping", description="Check that Rynnzyr is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Rynnzyr is online and ready.", ephemeral=True)


@bot.tree.command(name="design", description="Preview and rebuild your community server")
@app_commands.describe(prompt="Describe your community; e.g. Roblox, creator, trading, or gaming server")
async def design(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use this inside a server.", ephemeral=True)
        return
    member = interaction.user
    if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
        await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
        return
    me = interaction.guild.me
    if me is None or not (me.guild_permissions.manage_channels and me.guild_permissions.manage_roles):
        await interaction.response.send_message("I need Manage Channels and Manage Roles.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        plan = await generate_plan(interaction.guild, prompt[:1000])
        warning = "**Destructive rebuild warning:** confirming permanently deletes every existing channel and category, including all messages. Roles are kept. Nothing changes until you press the red button."
        await interaction.followup.send(warning, embed=make_embed(interaction.guild, plan), view=RebuildView(interaction.guild, plan, interaction.user.id), ephemeral=True)
    except Exception as exc:
        print(f"/design failed: {type(exc).__name__}: {exc}")
        message = str(exc) if "GROQ_API_KEY" in str(exc) else "I couldn't design that layout. Check Railway logs and AI configuration."
        await interaction.followup.send(message[:1800], ephemeral=True)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot online as {bot.user}; synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Command sync failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

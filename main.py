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


def ai_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)


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


CORE_LAYOUT = [
    {"name": "──── ⟪STAFF GENERAL⟫ ────", "private": True, "channels": [
        ("📚", "staff-rules", "text"), ("📣", "staff-announcements", "text"),
        ("💬", "staff-chat", "text"), ("🎉", "staff-promotions", "text"),
        ("🗂️", "staff-logs", "text"), ("⚠️", "staff-demotions", "text"),
        ("🎙️", "staff-vc", "voice")
    ]},
    {"name": "──── ⟪WELCOME⟫ ────", "private": False, "channels": [
        ("🛤️", "invite-tracker", "text"), ("👋", "welcome", "text"), ("🕊️", "goodbye", "text")
    ]},
    {"name": "──── ⟪VERIFICATION⟫ ────", "private": False, "channels": [("✅", "verification", "text")]},
    {"name": "──── ⟪IMPORTANT⟫ ────", "private": False, "channels": [
        ("📚", "rules", "text"), ("📣", "announcements", "text"), ("📊", "sab-leaks", "text"),
        ("🚀", "server-boosts", "text"), ("⚡", "boosters-rewards", "text"), ("📊", "polls", "text"),
        ("⚠️", "scammers", "text"), ("📝", "applications", "text"), ("🔄", "server-updates", "text"),
        ("🏅", "hall-of-fame", "text"), ("🎬", "content", "text"), ("🎟️", "support-ticket", "text")
    ]},
    {"name": "──── ⟪MIDDLEMAN⟫ ────", "private": False, "channels": [
        ("💫", "verified-middleman", "text"), ("🎫", "middleman-ticket", "text"), ("✅", "middleman-vouches", "text")
    ]},
    {"name": "──── ⟪GIVEAWAYS⟫ ────", "private": False, "channels": [
        ("🎉", "giveaways", "text"), ("🎰", "flash-giveaways", "text"),
        ("📸", "giveaways-vouches", "text"), ("🎮", "giveaways-vc", "voice")
    ]},
    {"name": "──── ⟪GENERAL⟫ ────", "private": False, "channels": [
        ("💬", "general", "text"), ("📸", "media", "text"), ("⚙️", "commands", "text"),
        ("📊", "levels", "text"), ("🛠️", "suggestions", "text")
    ]}
]

EMOJI_RULES = {
    "rule": "📚", "announce": "📣", "news": "📰", "update": "🔄", "poll": "🗳️",
    "welcome": "👋", "intro": "👋", "goodbye": "🕊️", "invite": "🛤️", "verify": "✅",
    "general": "💬", "chat": "🗨️", "discussion": "🗣️", "media": "📸", "photo": "📷",
    "video": "🎥", "clip": "🎞️", "stream": "📡", "content": "🎬", "meme": "😂",
    "suggest": "🛠️", "feedback": "📝", "help": "🆘", "support": "🎟️", "ticket": "🎫",
    "faq": "❓", "bug": "🐛", "staff": "🛡️", "log": "🗂️", "application": "📋",
    "promotion": "🎉", "demotion": "⚠️", "boost": "🚀", "reward": "🎁", "giveaway": "🎁",
    "trade": "💱", "market": "🛒", "shop": "🏪", "sell": "🏷️", "buy": "💰",
    "auction": "🔨", "scam": "🚨", "report": "🚨", "level": "📈", "leaderboard": "🏆",
    "command": "⚙️", "bot": "🤖", "voice": "🔊", "music": "🎵", "game": "🎮",
    "lfg": "🔎", "team": "👥", "match": "⚔️", "rank": "🥇", "tournament": "🥇",
    "scrim": "🥊", "minecraft": "⛏️", "roblox": "🧱", "fortnite": "🪂", "valorant": "🎯",
    "fan": "💖", "art": "🎨", "creator": "✨", "collab": "🤝", "event": "📅",
    "calendar": "📅", "resource": "🧰", "guide": "🧭", "tutorial": "🧑‍🏫", "idea": "💡",
}
FALLBACK_EMOJIS = ["🌟", "🧩", "🪄", "🧿", "🌈", "🪐", "🦋", "🍀", "🔥", "💎", "🧸", "🪷", "🌙", "🎨", "🪙", "🧠", "🪁", "💫", "🔮", "🧵", "🎪", "🪸", "🪻", "🧃", "🧊", "🧪", "🧭"]

ARCHETYPES = {
    "trading": {
        "sections": [
            ("💎 : MARKETPLACE : 💸", [("🛒", "marketplace", "text"), ("💱", "trade-chat", "text"), ("🎯", "trade-requests", "text"), ("🔎", "looking-to-buy", "text"), ("🔨", "auctions", "text"), ("📦", "deal-room", "voice")]),
            ("🤝 : MIDDLEMAN SERVICE : 🛡️", [("🤝", "request-middleman", "text"), ("📋", "active-deals", "text"), ("✅", "completed-trades", "text"), ("🎫", "deal-support", "text")]),
            ("⭐ : REPUTATION : 🏆", [("✅", "vouches", "text"), ("⚠️", "scam-reports", "text"), ("🏅", "top-traders", "text")]),
        ], "roles": [("Verified Trader", 0x57E39A), ("Middleman", 0xF7B84B), ("Trusted Seller", 0x5865F2)]
    },
    "gaming": {
        "sections": [
            ("🎮 : GAME LOUNGE : 🕹️", [("💬", "game-chat", "text"), ("😂", "clips-and-memes", "text"), ("📸", "screenshots", "text"), ("🎙️", "lobby-chat", "voice")]),
            ("🔎 : FIND YOUR SQUAD : 🪖", [("🧩", "looking-for-group", "text"), ("👥", "team-up", "text"), ("🎯", "competitive", "text"), ("🧪", "playtesting", "text")]),
            ("🏆 : COMPETITIVE : ⚔️", [("📅", "matches", "text"), ("📊", "leaderboards", "text"), ("🥇", "tournaments", "text"), ("🥊", "scrim-voice", "voice")]),
        ], "roles": [("Player", 0x5865F2), ("Competitor", 0xED4245), ("Team Captain", 0xFEE75C)]
    },
    "creator": {
        "sections": [
            ("📡 : LIVE & CONTENT : 🎬", [("📢", "content-drops", "text"), ("📺", "stream-notifications", "text"), ("🎞️", "latest-clips", "text"), ("🔴", "watch-party", "voice")]),
            ("🎨 : FAN WORKS : 💖", [("🖼️", "fan-art", "text"), ("✂️", "edits", "text"), ("💡", "content-ideas", "text")]),
            ("🤝 : COLLABORATIONS : ✨", [("📨", "collab-requests", "text"), ("🧑‍🎤", "creator-network", "text"), ("🎤", "guest-voice", "voice")]),
        ], "roles": [("Member", 0x5865F2), ("Creator", 0xEB459E), ("Collaborator", 0x57F287)]
    },
    "community": {
        "sections": [
            ("💬 : COMMUNITY : 🎉", [("👋", "introductions", "text"), ("☕", "general-chat", "text"), ("😂", "memes", "text"), ("📸", "photo-dump", "text"), ("🗣️", "community-voice", "voice")]),
            ("💡 : COMMUNITY IDEAS : 🧩", [("🛠️", "suggestions", "text"), ("🗳️", "community-polls", "text"), ("🎨", "feedback", "text")]),
            ("🎉 : EVENTS : 📅", [("📅", "upcoming-events", "text"), ("🎤", "event-stage", "voice"), ("📸", "event-gallery", "text")]),
        ], "roles": [("Member", 0x5865F2), ("Active Member", 0x57F287), ("Event Host", 0xEB459E)]
    },
}


def clean_text(value, limit=100):
    text = str(value or "").replace("@everyone", "everyone").replace("@here", "here")
    text = re.sub(r"[\r\n\t\x00-\x1f]", " ", text)
    return " ".join(text.split())[:limit].strip()


def slug_channel(value):
    raw = clean_text(value, 100)
    raw = re.sub(r"^[〔【\[（(].*?[〕】\]）)]\s*[・•|:：-]*\s*", "", raw)
    raw = re.sub(r"^[^\w]+", "", raw, flags=re.UNICODE)
    raw = raw.lower().replace("_", "-")
    raw = "".join(ch if ch.isalnum() or ch in "- " else "-" for ch in raw)
    return "-".join(raw.split()).strip("-")[:72] or "channel"


def choose_emoji(slug, used):
    ordered = sorted(EMOJI_RULES.items(), key=lambda item: len(item[0]), reverse=True)
    for keyword, emoji in ordered:
        if keyword in slug and emoji not in used:
            return emoji
    seed = sum(ord(ch) for ch in slug)
    for offset in range(len(FALLBACK_EMOJIS)):
        emoji = FALLBACK_EMOJIS[(seed + offset) % len(FALLBACK_EMOJIS)]
        if emoji not in used:
            return emoji
    return "✨"


def format_channel(slug, fixed=None, used=None):
    slug = slug_channel(slug)
    if used is None:
        used = set()
    emoji = fixed or choose_emoji(slug, used)
    used.add(emoji)
    return f"〔{emoji}〕・{slug}"


def detect_archetype(prompt):
    text = prompt.lower()
    checks = {
        "trading": ("trade", "trading", "market", "middleman", "sell", "buy", "auction", "voucher", "stock"),
        "gaming": ("gaming", "game", "esports", "clan", "guild", "minecraft", "roblox", "valorant", "fortnite", "tournament", "scrim"),
        "creator": ("creator", "stream", "youtube", "twitch", "tiktok", "fan", "artist", "art"),
    }
    for name, words in checks.items():
        if any(word in text for word in words):
            return name
    return "community"


@app.get("/")
def serve_website():
    response = HTMLResponse(open("index.html", encoding="utf-8").read())
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
        guild_id = int(item["id"])
        result.append({"id": guild_id, "name": item["name"], "icon": item.get("icon"), "has_bot": bot.get_guild(guild_id) is not None,
                       "invite_url": None if bot.get_guild(guild_id) else f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=268435472&scope=bot%20applications.commands&guild_id={guild_id}"})
    return {"guilds": result}


def get_guild(guild_id):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(404, "Bot is not in this server")
    me = guild.me
    if me is None:
        raise HTTPException(503, "Bot membership is not available")
    if not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
        raise HTTPException(403, "Bot needs Manage Channels and Manage Roles")
    return guild


def safe_state(guild):
    roles = [role.name for role in guild.roles if not role.managed][-15:]
    categories = [{"name": category.name, "channels": [channel.name for channel in category.channels]} for category in guild.categories[:30]]
    return {"name": guild.name, "roles": roles, "categories": categories}


def sanitize_plan(plan):
    roles = []
    for item in (plan.get("roles") or [])[:10]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        if name.lower() in {"everyone", "here", "admin", "administrator", "bot"}:
            continue
        try:
            color = int(str(item.get("color", "5865F2")).lstrip("#"), 16)
        except (ValueError, TypeError):
            color = 0x5865F2
        roles.append({"name": name, "color": max(0, min(color, 0xFFFFFF)), "hoist": bool(item.get("hoist")), "mentionable": bool(item.get("mentionable"))})

    categories = []
    for core in CORE_LAYOUT:
        used = set()
        channels = [{"name": format_channel(channel_name, emoji, used), "type": kind, "topic": ""}
                    for emoji, channel_name, kind in core["channels"]]
        categories.append({"name": core["name"], "staff_only": core["private"], "channels": channels})

    extras = plan.get("categories") if isinstance(plan.get("categories"), list) else []
    for item in extras[:8]:
        if not isinstance(item, dict):
            continue
        name = clean_text(item.get("name"), 100)
        if not name:
            continue
        channels = []
        used = set()
        for channel in (item.get("channels") or [])[:10]:
            if not isinstance(channel, dict):
                continue
            kind = "voice" if channel.get("type") == "voice" else "text"
            channels.append({"name": format_channel(channel.get("name"), None, used), "type": kind,
                             "topic": clean_text(channel.get("topic"), 1024) if kind == "text" else ""})
        if channels:
            categories.append({"name": name, "staff_only": False, "channels": channels})
    return {"summary": clean_text(plan.get("summary"), 500), "roles": roles, "categories": categories}


async def generate_plan(guild, prompt):
    archetype = detect_archetype(prompt)
    template = ARCHETYPES[archetype]

    response = await ai_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        messages=[
            {"role": "system", "content": f"""
Return JSON only. Create 3-6 highly specific EXTRA categories for the user's community.
The system already adds fixed reference categories and therefore they must not be returned.
Detected community type: {archetype}. Use the same quality level as these template ideas:
{json.dumps(template['sections'])}
Improve and adapt the ideas rather than copying them blindly. Remove irrelevant sections.
Create useful channel names, channel types, and short topics.
Avoid duplicate categories, duplicate channel purposes, and generic emoji names.
Schema: {{"summary":"...","roles":[{{"name":"...","color":"5865F2","hoist":false,"mentionable":false}}],"categories":[{{"name":"🎮 : GAME LOUNGE : 🎮","channels":[{{"name":"game-chat","type":"text","topic":"..."}}]}}]}}
"""},
            {"role": "user", "content": prompt}
        ],
        temperature=0.65,
        max_tokens=5000,
        response_format={"type": "json_object"}
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("AI returned an empty design")
    plan = json.loads(content)

    # Preserve the proven archetype structure even if the model returns weak or incomplete output.
    if not isinstance(plan.get("categories"), list) or len(plan["categories"]) < 2:
        plan["categories"] = [{"name": name, "channels": [{"name": slug_channel(channel_name), "type": kind,
                                                            "topic": ""} for _, channel_name, kind in channels]}
                               for name, channels in template["sections"]]
    if not isinstance(plan.get("roles"), list) or len(plan["roles"]) < 3:
        plan["roles"] = [{"name": name, "color": f"{color:06X}", "hoist": False, "mentionable": False}
                         for name, color in template["roles"]]
    return sanitize_plan(plan)


async def apply_guild_plan(guild, plan):
    plan = sanitize_plan(plan)
    ids, created = [], []

    roles = {}
    for spec in plan["roles"]:
        role = discord.utils.get(guild.roles, name=spec["name"])
        if role is None:
            role = await guild.create_role(name=spec["name"], colour=discord.Colour(spec["color"]), hoist=spec["hoist"], mentionable=spec["mentionable"], reason="Created by Rynnzyr")
            ids.append(f"role:{role.id}")
            created.append(f"Role: {role.name}")
        roles[role.name.lower()] = role

    staff_role = next((role for name, role in roles.items() if "staff" in name or "moderator" in name or name == "mod"), None)
    staff_role = staff_role or discord.utils.get(guild.roles, name="Staff")
    if staff_role is None:
        staff_role = await guild.create_role(name="Staff", colour=discord.Colour(0x5865F2), reason="Private staff access")
        ids.append(f"role:{staff_role.id}")
        created.append("Role: Staff")

    resolved = []
    for position, spec in enumerate(plan["categories"]):
        overwrites = {}
        if spec["staff_only"]:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                          staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True)}
        category = discord.utils.get(guild.categories, name=spec["name"])
        if category is None:
            category = await guild.create_category(spec["name"], overwrites=overwrites, reason="Rynnzyr server blueprint")
            ids.append(f"category:{category.id}")
            created.append(f"Category: {category.name}" + (" (staff-only)" if spec["staff_only"] else ""))
        elif spec["staff_only"]:
            await category.edit(overwrites=overwrites, reason="Secure staff category")
        resolved.append((category, spec))

    for position, (category, _) in enumerate(resolved):
        await category.edit(position=position, reason="Apply blueprint category order")

    for category, spec in resolved:
        for position, channel_spec in enumerate(spec["channels"]):
            channel = discord.utils.get(category.channels, name=channel_spec["name"])
            if channel is None:
                if channel_spec["type"] == "voice":
                    channel = await guild.create_voice_channel(channel_spec["name"], category=category, reason="Rynnzyr server blueprint")
                else:
                    channel = await guild.create_text_channel(channel_spec["name"], category=category, topic=channel_spec["topic"] or None, reason="Rynnzyr server blueprint")
                ids.append(f"channel:{channel.id}")
                created.append(f"{channel_spec['type'].title()}: {channel_spec['name']}")
            else:
                await channel.edit(position=position, sync_permissions=spec["staff_only"], reason="Apply blueprint channel order")
            await asyncio.sleep(0.2)

    undo_snapshots[guild.id] = ids
    return created


def make_embed(guild, plan):
    embed = discord.Embed(title=f"✨ {guild.name} — Smart server blueprint", description=plan["summary"] or "A polished, community-specific layout.", color=0x7C83FF)
    for category in plan["categories"]:
        if len(embed.fields) >= 24:
            break
        lines = [("🔊 " if channel["type"] == "voice" else "# ") + channel["name"] for channel in category["channels"]]
        if category["staff_only"]:
            lines.append("🔒 Staff-only")
        embed.add_field(name=category["name"], value=("\n".join(lines) or "No channels")[:1024], inline=True)
    embed.set_footer(text="Fixed foundations first • Smart topic sections second • Preview before build")
    return embed


class BlueprintView(discord.ui.View):
    def __init__(self, guild, plan, author_id):
        super().__init__(timeout=180)
        self.guild = guild
        self.plan = plan
        self.author_id = author_id
        self.finished = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the requesting server manager can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Build this server", style=discord.ButtonStyle.success, emoji="🏗️")
    async def build_button(self, interaction, button):
        if self.finished:
            await interaction.response.send_message("This blueprint was already handled.", ephemeral=True)
            return
        self.finished = True
        button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            changes = await apply_guild_plan(self.guild, self.plan)
            report = "\n".join(f"• {line}" for line in changes[:35]) or "Everything already existed."
            await interaction.followup.send(f"✅ **Server built!**\n{report}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Discord denied the change. Check Manage Channels and Manage Roles permissions.", ephemeral=True)
        except Exception as exc:
            print(f"Blueprint apply failed: {type(exc).__name__}: {exc}")
            await interaction.followup.send("The build hit an error. Check Railway logs.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction, button):
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Blueprint cancelled — no changes made.", embed=None, view=self)


@app.post("/api/plan")
async def create_plan(req: PlanRequest):
    try:
        return {"plan": await generate_plan(get_guild(req.guild_id), req.prompt)}
    except Exception as exc:
        raise HTTPException(502, f"AI planning failed: {exc}")


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    try:
        return {"success": True, "created": await apply_guild_plan(get_guild(req.guild_id), req.plan)}
    except discord.Forbidden:
        raise HTTPException(403, "Bot is missing Discord permissions")
    except discord.HTTPException as exc:
        raise HTTPException(502, f"Discord rejected a change: {exc.text}")


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


@bot.tree.command(name="design", description="Preview and build a custom AI-designed server")
@app_commands.describe(prompt="Describe your community and the server you want")
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
        await interaction.followup.send(embed=make_embed(interaction.guild, plan), view=BlueprintView(interaction.guild, plan, interaction.user.id), ephemeral=True)
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

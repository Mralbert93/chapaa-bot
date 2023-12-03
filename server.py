import asyncio
from datetime import datetime, timedelta, timezone
from interactions import Client, Intents, listen, slash_command, SlashContext, OptionType, slash_option, ActionRow, Button, ButtonStyle, StringSelectMenu, Guild
from interactions.api.events import Component
import os
from party_type import PartyTypeInfo, get_roles_list, resolve_party_type, get_supported_party_types, get_mention_role, display_quantity
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Set environment variables
token= os.environ.get("DISCORD_TOKEN")
database_url = os.environ.get("DATABASE_URL")

# Create client for Discord and MongoDB
bot = Client(intents=Intents.DEFAULT)
mongo = MongoClient(database_url)

# Test connection to database
try:
    mongo.admin.command('ping')
    print("Pinged database. You have successfully connected to MongoDB!")
except Exception as e:
    print(e)

# Set database and collections
db = mongo.chapaa
parties_collection = db["parties"]
users_collection = db["users"]

# Create a sequence collection
sequence_collection = db['sequence']

# Get next value in sequence
def get_next_sequence_value(sequence_name):
    result = sequence_collection.find_one_and_update(
        {'ID': sequence_name},
        {'$inc': {'seq': 1}},
        return_document=True
    )
    return result['seq']

# Get current time in Eastern
def get_time():
    return (datetime.utcnow() + timedelta(hours=-5)).strftime('%I:%M %p')

# Party class
class Party:
    def __init__(self, ID, Status, Type, Quantity, Host, Time=None, Multi=None,Roles=None, MessageID=None, ChannelID=None, Responses=None, **kwargs):
        self.ID = ID
        self.Status = Status if Status is not None else "Open"
        self.Type = Type
        self.Quantity = Quantity
        self.Host = Host
        self.Time = Time
        self.Multi = Multi if Multi is not None else True
        self.Roles = Roles if Roles is not None else PartyTypeInfo[Type]["Roles"]
        self.Roles.update(kwargs)
        self.MessageID = MessageID if MessageID is not None else ""
        self.ChannelID = ChannelID if ChannelID is not None else ""
        self.Responses = Responses if Responses is not None else []

    def __str__(self):
        return f"Party(ID={self.ID}, Status={self.Status}, Type={self.Type}, Quantity={self.Quantity}, Host={self.Host}, Time={self.Time}, Multi={self.Multi}, Roles={self.Roles}, MessageID={self.MessageID}, ChannelID={self.ChannelID}, Responses={self.Responses})"
    
    def get_party_type(Type):
        return PartyTypeInfo.get(Type, {})

    def has_user_signed_up(self, user_id):
        for role in self.Roles.values():
            if user_id in role:
                return True
        return False

    def set_user_id_for_role(self, role, user_id):
        if role in self.Roles:
            role_list = self.Roles[role]
            if "Open" in self.Roles[role]:
                open_index = role_list.index("Open")
                role_list[open_index] = user_id
    
    def remove_user_from_role(self, user_id):
       for role, role_list in self.Roles.items():
           if user_id in role_list:
               user_index = role_list.index(user_id)
               role_list[user_index] = "Open"
               return role
           
    def generate_description(self):
        description = f"Hosted by {self.Host}\n"
        
        if self.Time is not None:
            description += f"Start Time: <t:{self.Time}>\n\n"
        else:
            description += "\n"
        
        required_ingredients = PartyTypeInfo.get(self.Type, {}).get("Ingredients", {})

        for role, members in self.Roles.items():
            description += f"**{role}:** {required_ingredients.get(role, 'No ingredients required')}\n"
            
            if members:
                for member in members:
                    description += f"- {member}\n"

        return description

async def edit_message(self, ctx, message_id: int):
    message = await ctx.channel.fetch_message(message_id)
    description = self.generate_description()
    now = get_time()
    embed = {
        "title": f"({self.Status}) {self.Quantity}x {self.Type} Party" if self.Quantity is not None else f"({self.Status}) {self.Type} Party",
        "description": description,
        "thumbnail": {
            "url": PartyTypeInfo.get(self.Type, {}).get("Image", ""),
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"ID: {self.ID} • Last updated at {now} Eastern"
        }
    }
    components: list[ActionRow] = [
        ActionRow(
            Button(
                style=ButtonStyle.GREEN,
                label="Sign Up",
                custom_id="signup",
            ),
            Button(
                style=ButtonStyle.RED,
                label="Unsign Up",
                custom_id="unsignup",
            )
        )
    ]
    await message.edit(embed=embed,components=components)

# Command create
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="create",
        sub_cmd_description="Create a Palia Party",
)
@slash_option(
    name="type",
    description="Type of party",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="quantity",
    description="Quantity to be made",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="host",
    description="In game name of host",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name="time",
    description="Party's planned start time (use https://www.unixtimestamp.com)",
    required=False,
    opt_type=OptionType.INTEGER
)
@slash_option(
    name="multi",
    description="Whether player can have multiple roles (true/false)",
    required=False,
    opt_type=OptionType.BOOLEAN
)
async def create(ctx: SlashContext, type: str, quantity: str, host: str, time: int = None, multi: bool = True):
    global party

    if ctx.channel.type != 11:
        error_message = await ctx.send(f"<@{ctx.author.id}>, please use #palia-parties channel to post parties.", ephemeral=True, delete_after=15)
        return

    if "palia-parties" not in ctx.channel.parent_channel.name.lower():
        error_message = await ctx.send(f"<@{ctx.author.id}>, please use #palia-parties channel to post parties.", ephemeral=True, delete_after=15)
        return

    resolved_party_type = resolve_party_type(type)
    if resolved_party_type:
        type = resolved_party_type
    else:
        supported_types_str = ', '.join(get_supported_party_types())
        error_message = await ctx.send(f"<@{ctx.author.id}>, sorry {type} party type is not supported.\nThe following party types are currently supported: {supported_types_str}", ephemeral=True, delete_after=15)
        return
    
    if display_quantity(type) == False:
        quantity = None

    next_id = get_next_sequence_value('item_id')
        
    party = Party(ID=next_id, Status="Open", Type=type, Quantity=quantity, Host=host, Time=time, Multi=multi, Roles=None)
    description = party.generate_description()
    now = get_time()
    embed = {
        "title": f"({party.Status}) {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Type} Party",
        "description": description,
        "thumbnail": {
            "url": PartyTypeInfo.get(party.Type, {}).get("Image", ""),
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"ID: {party.ID} • Last updated at {now} Eastern"
        }
    }
    
    components: list[ActionRow] = [
        ActionRow(
            Button(
                style=ButtonStyle.GREEN,
                label="Sign Up",
                custom_id="signup",
            ),
            Button(
                style=ButtonStyle.RED,
                label="Unsign Up",
                custom_id="unsignup",
            )
        )
    ]

    posting = await ctx.send(embed=embed,components=components)
    await ctx.channel.edit(name=f"({party.Status}) {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Type} Party")
    party.MessageID = posting.id
    party.ChannelID = posting.channel.id

    ping = get_mention_role(type)
    channel = bot.get_channel(posting.channel.id)
    await bot.get_channel(posting.channel.id).send(ping)


    party_data = {
        "ID": party.ID,
        "Status": party.Status,
        "Type": party.Type,
        "Quantity": party.Quantity,
        "Host": party.Host,
        "Time": party.Time,
        "Multi": party.Multi,
        "Roles": party.Roles,
        "MessageID": party.MessageID,
        "ChannelID": party.ChannelID,
        "Responses": []
    }
    parties_collection.insert_one(party_data)
    party = None

@listen(Component)
async def on_component(event: Component):
    #print(vars(event.ctx))
    ctx = event.ctx
    signup_message = None
    party = None

    async def retrieve_party(message_id, action):
        nonlocal party
        if action == "signup" or action == "unsignup":
            result = parties_collection.find_one({"MessageID": message_id})
        elif action == "role":
            result = parties_collection.find_one({"Responses": {"$elemMatch": {"$eq": message_id}}})
        party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Time=result['Time'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])
        return party

    match ctx.custom_id:
        case "signup":
            await retrieve_party(ctx.message.id, "signup")
            if party.has_user_signed_up(f"<@{ctx.author.id}>") and party.Multi == False:
                await ctx.send(f"<@{ctx.author.id}>, you have already signed up for a role. The party host is limiting users to one role. Please remove your current role to switch roles.", ephemeral=True, delete_after=15)
            else:
                roles_list = get_roles_list(party.Type)
                components = StringSelectMenu(
                    roles_list,
                    placeholder="Choose your role",
                    custom_id="role"
                    )
                signup_message = await ctx.send(f"<@{ctx.author.id}>",components=components, ephemeral=True, delete_after=15)
                parties_collection.update_one({"MessageID": party.MessageID}, {"$push":{"Responses": signup_message.id}})

        case "unsignup":
            await retrieve_party(ctx.message.id, "unsignup")
            while party.has_user_signed_up(f"<@{ctx.author.id}>"): 
                party.remove_user_from_role(f"<@{ctx.author.id}>")
            await edit_message(party, ctx, party.MessageID)
            parties_collection.update_one({"MessageID": party.MessageID}, {"$set":{"Roles": party.Roles}})
            confirmation = await ctx.send(f"<@{ctx.author.id}>, you have been removed from the party.", ephemeral=True, delete_after=3)

        case "role":
            await retrieve_party(ctx.message.id, "role")
            selected_role = ctx.values[0]
            party.set_user_id_for_role(selected_role, f"<@{ctx.author.id}>")
            await edit_message(party, ctx, party.MessageID)
            parties_collection.update_one({"MessageID": party.MessageID}, {"$set":{"Roles": party.Roles}})
            await ctx.edit_origin(content=f"<@{ctx.author.id}>, you have been added to {selected_role}", components=[])
            
        case "refresh":
            await leaderboard(ctx)
            await ctx.message.delete()

# Notify command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="notify",
        sub_cmd_description="Notify users that party is starting",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def notify(ctx: SlashContext, id: int):
    user_list = []

    result = parties_collection.find_one({"ID": id})
    party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Time=result['Time'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])


    for role_list in party.Roles.values():
        for role in role_list:
            if role != "Open" and role not in user_list:
                user_list.append(role)
    
    user_list_str = ', '.join(user_list)               

    await ctx.send(f"The party is starting now! Please add **{party.Host}** in game and report to their house. {user_list_str}")

# Close command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="close",
        sub_cmd_description="Close a party and record user participation",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def close(ctx: SlashContext, id: int):
    result = parties_collection.find_one({"ID": id})
    party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Time=result['Time'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])

    if ctx.channel_id != result["ChannelID"]:
        error_message = await ctx.send(f"<@{ctx.author.id}>, parties must be closed from their respective thread.", ephemeral=True, delete_after=15)
        return

    if result['Status'] == "Closed":
        error_message = await ctx.send(f"Error: The party has already been closed and participation has already been recorded.", ephemeral=True, delete_after=15)
        return
    
    user_list = []
    for role_list in party.Roles.values():
        for role in role_list:
            if role != "Open" and role not in user_list:
                users_collection.update_one({"ID": role}, {"$push": {"Parties": party.ID}},upsert=True)
                user_list.append(role)
    
    party.Status = "Closed"
    parties_collection.update_one({"ID": id},{"$set": {"Status": "Closed"}})

    description = party.generate_description()
    now = get_time()
    embed = {
        "title": f"({party.Status}) {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Type} Party",
        "description": description,
        "thumbnail": {
            "url": PartyTypeInfo.get(party.Type, {}).get("Image", ""),
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"ID: {party.ID} • Last updated at {now} Eastern"
        }
    }

    oldchannel = bot.get_channel(party.ChannelID)
    target_message = await oldchannel.fetch_message(party.MessageID)
    await target_message.edit(embed=embed,components=[])
    await ctx.channel.edit(name=f"({party.Status}) {party.Quantity}x {party.Type} Party" if party.Quantity is not None else f"({party.Status}) {party.Type} Party")
    confirmation = await ctx.send(f"The party has finished and participation has been recorded :partying_face:")
    await ctx.channel.edit(locked=True)

# Cancel command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="cancel",
        sub_cmd_description="Cancel a party",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def cancel(ctx: SlashContext, id: int):
    result = parties_collection.find_one({"ID": id})

    if result == None:
        error_message = await ctx.send(f"<@{ctx.author.id}>, party not found. Please ensure you are specifying a valid Party ID.", ephemeral=True, delete_after=15)
        return

    if ctx.channel_id != result["ChannelID"]:
        error_message = await ctx.send(f"<@{ctx.author.id}>, parties must be deleted from their respective thread.", ephemeral=True, delete_after=15)
        return
    
    if result["Status"] != "Open":
        error_message = await ctx.send(f"<@{ctx.author.id}>, only Open parties may be canceled.", ephemeral=True, delete_after=15)
        return

    result = parties_collection.delete_one({"ID": id})

    if result.deleted_count != 1:
        error_message = await ctx.send(f"<@{ctx.author.id}>, party unable to be canceled for unknown reason.", ephemeral=True, delete_after=15)
        return
    
    warning_message = await ctx.send(f"Party {id} has been canceled. This thread will self destruct in 30 seconds.")
    await asyncio.sleep(30)
    await warning_message.channel.delete()

# Leaderboard command
@slash_command(
        name="leaderboard",
        description="Displays leaderboard for party participation",
)
@slash_option(
    name="number",
    description="Number of places to display (Max 25)",
    required=True,
    opt_type=OptionType.INTEGER
)

async def leaderboard(ctx: SlashContext, number: int = 10):
    if number > 20: number = 20
    pipeline = [
        {
            "$project": {
                "ID": 1,
                "partyCount": {"$size": {"$ifNull": ["$Parties", []]}}
            }
        },
        {
            "$sort": {"partyCount": -1}
        },
        {
            "$limit": number
        }
    ]

    party_result = list(users_collection.aggregate(pipeline))
    # text_result = list(users_collection.find({}, {"ID":1, "MessageCount": 1}).sort("MessageCount",pymongo.DESCENDING).limit(number))
    # voice_result = list(users_collection.find({}, {"ID":1, "VoiceMins": 1}).sort("VoiceMins",pymongo.DESCENDING).limit(number))
    
    # description = "\n\u200b"
    # for index, user in enumerate(text_result, start = 1):
    #     username = user['ID']
    #     messageCount = f"{user['MessageCount']} messages"
    #     if index != len(text_result):
    #         description += "#{} - {} - {}\n\u200b".format(index, username, messageCount)
    #     else:
    #         description += "#{} - {} - {}".format(index, username, messageCount)
    
    # description += "\n\n**__Voice:__**\n\u200b"
    # for index, user in enumerate(voice_result, start = 1):
    #     username = user['ID']
    #     voiceHours = user['VoiceMins']/60.0
    #     if index != len(voice_result):
    #         description += "#{} - {} - {:.1f} hours\n\u200b".format(index, username, voiceHours)
    #     else:
    #         description += "#{} - {} - {:.1f} hours".format(index, username, voiceHours)

    description = "\n\u200b"
    for index, user in enumerate(party_result, start=1):
        username = user['ID']
        if user['partyCount'] == 1:
            partyCount = f"{user['partyCount']} Party"
        else:
            partyCount = f"{user['partyCount']} Parties"
        if index != len(party_result):
            description += "#{} - {} - {}\n\u200b".format(index, username, partyCount)
        else:
            description += "#{} - {} - {}".format(index, username, partyCount)

    now = get_time()
    embed = {
        "title": f"Party Leaderboard",
        "description": description,
        "thumbnail": {
            "url": "https://pngimg.com/uploads/golden_cup/golden_cup_PNG94626.png",
            "height": 0,
            "width": 0
        },
        "footer": {
            "text": f"Last updated at {now} Eastern"
        }
    }

    components: list[ActionRow] = [
        ActionRow(
            Button(
                style=ButtonStyle.GREEN,
                label="Refresh",
                custom_id="refresh",
            )
        )
    ]

    posting = await ctx.send(embed=embed,components=components)

@listen()
async def on_message_create(event):
    if event.message.author.bot:
        return
    users_collection.update_one({"ID": f"<@{event.message.author.id}>"}, {'$inc': {'MessageCount':1}}, upsert=True)

async def check_voice_loop():
    while True:
        await check_channels()
        await asyncio.sleep(60)

async def check_channels():
    for guild in bot.guilds:
        for channel in guild.channels:
            if channel.type == 2:
                voice_member_ids = getattr(channel, '_voice_member_ids', [])
                for member_id in voice_member_ids:
                    users_collection.update_one({"ID": f"<@{member_id}>"}, {'$inc': {'VoiceMins':1}}, upsert=True)

# Bot is ready
@listen()
async def on_startup():
    print("Bot is ready and online!")
    await check_voice_loop()

# Start bot
bot.start(token)

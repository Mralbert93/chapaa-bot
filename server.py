import asyncio
from datetime import datetime, timedelta, timezone
from interactions import Client, Intents, listen, slash_command, SlashContext, OptionType, slash_option, ActionRow, Button, ButtonStyle, StringSelectMenu
from interactions.api.events import Component
import os
from party_type import PartyTypeInfo, get_roles_list, resolve_party_type, get_supported_party_types
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
    def __init__(self, ID, Status, Type, Quantity, Host, Multi=None,Roles=None, MessageID=None, ChannelID=None, Responses=None, **kwargs):
        self.ID = ID
        self.Status = Status if Status is not None else "Open"
        self.Type = Type
        self.Quantity = Quantity
        self.Host = Host
        self.Multi = Multi if Multi is not None else True
        self.Roles = Roles if Roles is not None else PartyTypeInfo[Type]["Roles"]
        self.Roles.update(kwargs)
        self.MessageID = MessageID if MessageID is not None else ""
        self.ChannelID = ChannelID if ChannelID is not None else ""
        self.Responses = Responses if Responses is not None else []

    def __str__(self):
        return f"Party(ID={self.ID}, Status={self.Status}, Type={self.Type}, Quantity={self.Quantity}, Host={self.Host}, Multi={self.Multi}, Roles={self.Roles}, MessageID={self.MessageID}, ChannelID={self.ChannelID}, Responses={self.Responses})"
    
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
        description = f"Hosted by {self.Host}\n\n"
        
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
        "title": f"{self.Quantity}x {self.Type} Party - {self.Status}",
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
    name="multi",
    description="Whether player can have multiple roles (true/false)",
    required=False,
    opt_type=OptionType.BOOLEAN
)
async def create(ctx: SlashContext, type: str, quantity: str, host: str, multi: bool = True):
    global party

    resolved_party_type = resolve_party_type(type)
    if resolved_party_type:
        type = resolved_party_type
    else:
        supported_types_str = ', '.join(get_supported_party_types())
        error_post = await ctx.send(f"<@{ctx.author.id}>, sorry {type} party type is not supported.\nThe following party types are currently supported: {supported_types_str}")
        await asyncio.sleep(30)
        await error_post.delete()
        return
    
    next_id = get_next_sequence_value('item_id')

    party = Party(ID=next_id, Status="Open", Type=type, Quantity=quantity, Host=host, Multi=multi, Roles=None)
    description = party.generate_description()
    now = get_time()
    embed = {
        "title": f"{party.Quantity}x {party.Type} Party - {party.Status}",
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
    party.MessageID = posting.id
    party.ChannelID = posting.channel.id

    party_data = {
        "ID": party.ID,
        "Status": party.Status,
        "Type": party.Type,
        "Quantity": party.Quantity,
        "Host": party.Host,
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
    ctx = event.ctx
    signup_message = None
    party = None

    async def retrieve_party(message_id, action):
        nonlocal party
        if action == "signup":
            result = parties_collection.find_one({"MessageID": message_id})
            party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])
            return party
        if action == "unsignup":
            result = parties_collection.find_one({"MessageID": message_id})
            party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])
            return party
        elif action == "role":
            result = parties_collection.find_one({"Responses": {"$elemMatch": {"$eq": message_id}}})
            party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])
            return party
        
    async def set_deleted():
        nonlocal signup_message
        if signup_message:
            await signup_message.delete()
        signup_message = None

    match ctx.custom_id:
        case "signup":
            await retrieve_party(ctx.message.id, "signup")
            if party.has_user_signed_up(f"<@{ctx.author.id}>") and party.Multi == False:
                await ctx.author.send("You have already signed up for a role. Please remove your current role to switch roles.")
            else:
                roles_list = get_roles_list(party.Type)
                components = StringSelectMenu(
                    roles_list,
                    placeholder="Choose your role",
                    custom_id="role"
                    )
                signup_message = await ctx.send(f"<@{ctx.author.id}>",components=components)
                parties_collection.update_one({"MessageID": party.MessageID}, {"$push":{"Responses": signup_message.id}})
                await asyncio.sleep(15)
                await set_deleted()

        case "unsignup":
            await retrieve_party(ctx.message.id, "unsignup")
            while party.has_user_signed_up(f"<@{ctx.author.id}>"): 
                party.remove_user_from_role(f"<@{ctx.author.id}>")
            await edit_message(party, ctx, party.MessageID)
            parties_collection.update_one({"MessageID": party.MessageID}, {"$set":{"Roles": party.Roles}})
            confirmation = await ctx.send(f"<@{ctx.author.id}>, you have been removed from the party.")
            await asyncio.sleep(3)
            await confirmation.delete()

        case "role":
            await retrieve_party(ctx.message.id, "role")
            selected_role = ctx.values[0]
            party.set_user_id_for_role(selected_role, f"<@{ctx.author.id}>")
            await edit_message(party, ctx, party.MessageID)
            parties_collection.update_one({"MessageID": party.MessageID}, {"$set":{"Roles": party.Roles}})
            await set_deleted()
            confirmation = await ctx.send(f"<@{ctx.author.id}>, you have been added to {selected_role}")
            await asyncio.sleep(1)
            await confirmation.delete()

# Repost command
@slash_command(
        name="party",
        description="Used to manage Palia parties",
        sub_cmd_name="repost",
        sub_cmd_description="Reposts current Palia Party",
)
@slash_option(
    name="id",
    description="ID of party",
    required=True,
    opt_type=OptionType.INTEGER
)
async def repost(ctx: SlashContext, id: int):
    result = parties_collection.find_one({"ID": id})
    party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])
    now = get_time()
    description = party.generate_description()
    embed = {
        "title": f"{party.Quantity}x {party.Type} Party - {party.Status}",
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

    oldchannel = bot.get_channel(party.ChannelID)
    target_message = await oldchannel.fetch_message(party.MessageID)
    await target_message.delete()
    
    posting = await ctx.send(embed=embed,components=components)
    party.MessageID = posting.id
    party.ChannelID = posting.channel.id
    parties_collection.update_one({"ID": party.ID}, {"$set":{"MessageID": party.MessageID,"ChannelID": party.ChannelID}})

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
    party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])


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
    party = Party(ID=result['ID'], Status=result['Status'], Type=result['Type'], Quantity=result['Quantity'], Host=result['Host'], Multi=result['Multi'], Roles=result['Roles'], MessageID=result['MessageID'], ChannelID=result['ChannelID'], Responses=result['Responses'])

    if result['Status'] == "Closed":
        error_message = await ctx.send(f"Error: The party has already been closed and participation has already been recorded.")
        await asyncio.sleep(3)
        await error_message.delete()
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
        "title": f"{party.Quantity}x {party.Type} Party - {party.Status}",
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
    confirmation = await ctx.send(f"The party has been closed and participation has been recorded.")
    await asyncio.sleep(3)
    await confirmation.delete()

# Bot is ready
@listen()
async def on_startup():
    print("Bot is ready and online!")

# Start bot
bot.start(token)

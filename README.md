# README

This repository holds to source code for Chapaa Bot.

The bot has the following slash commands:

`/party create` - creates a Palia party
- type (Required) - Type of party
- quantity (Required) - Quantity to be made
- host (Required) - In game name of host
- time (Optional) - Start time of party
- multi (Optional) - Whether player can have multiple roles (true/false)

`/party notify` - notify users that party is starting
- id (Required) - ID of party

`/party close` - closes a party and records user participation
- id (Required) - ID of party

`/leaderboard` - displays leaderboard for party participation
- number (Required) - Number of places to display (Max 20)

The currently supported party types are:
- Cooking
  - Apple Pie
  - Bouillabaisse
  - Celebration Cake 
  - Chili Oil Dumpling
  - Crab Pot Pie
- Hunting
- Bug Catching
- Foraging
- Fishing
- Mining

Once a party is created, players can do the following by interacting with the party post buttons:
- Sign up for role(s)
- Unsign up from the party

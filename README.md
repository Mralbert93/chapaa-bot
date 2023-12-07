# README

This repository holds to source code for Chapaa Bot.

The bot has the following slash commands:

`/party types` - show party types

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

`/party update` - updates a party 
- id (Required) - ID of party
- host (Optional) - In game name of host
- quantity (Required) - Quantity to be made
- time (Optional) - Start time of party

`party cancel` - cancels a party and deletes its thread
- id (Required) - ID of party

`/stats` - displays personal stats for party participation

Once a party is created, players can do the following by interacting with the party post buttons:
- Sign up for role(s)
- Unsign up from the party

from torn_bot.commands.api_key import setup_api_key_commands
from torn_bot.commands.profile import setup_profile_commands
from torn_bot.commands.targets import setup_targets_commands
from torn_bot.commands.medals import setup_medals_commands
from torn_bot.commands.global_attacks import setup_global_attacks_command
from torn_bot.commands.global_keys import setup_global_keys_commands
from torn_bot.commands.faction_inactive import setup_faction_inactive_commands

def setup_all_commands(tree, storage):
    setup_api_key_commands(tree, storage)
    setup_profile_commands(tree, storage)
    setup_targets_commands(tree, storage)
    setup_medals_commands(tree, storage)
    setup_global_attacks_command(tree, storage)
    setup_global_keys_commands(tree, storage)
    setup_faction_inactive_commands(tree, storage)

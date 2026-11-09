"""The universal actions: what a dash box card can do in the game.

A game maps an action to a key in its game.toml ([keys]); a card whose action has no key is greyed
out for that game. Each action has a usual type:

    "tap"  = one short keypress per touch
    "hold" = the key is held as long as the finger is on the button
    "latch" (only as a per-game kind, [kinds] in game.toml) = one tap presses the key and keeps it
            down, the next tap lets it go; for games that act only while a key is held
"""

ACTIONS = {
    "tc_down": "tap", "tc_up": "tap",
    "tc_cut_down": "tap", "tc_cut_up": "tap",
    "abs_down": "tap", "abs_up": "tap",
    "esc_down": "tap", "esc_up": "tap",
    "bias_rear": "tap", "bias_front": "tap",
    "map_down": "tap", "map_up": "tap",
    "drive_mode_down": "tap", "drive_mode_up": "tap",
    "pit_limiter": "tap",
    "lights": "tap",
    "flash": "hold",
    "wipers": "tap",
    "ignition": "hold",
    "starter": "hold",
    "recover": "tap",
}

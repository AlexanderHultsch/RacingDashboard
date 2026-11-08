"""The universal button set.

The UI always shows these groups and buttons, whatever game is running, so the dashboard looks
the same for every game. A game maps an action to a key in its game.toml ([keys]); an action
without a key is shown greyed out for that game.

type:  "tap"  = one short keypress per touch
       "hold" = the key is held as long as the finger is on the button
       "latch" (only as a per-game kind, [kinds] in game.toml) = one tap presses the key and keeps it
               down, the next tap lets it go; for games that act only while a key is held
field: optional telemetry name shown on / lighting the button
"""

GROUPS = [
    {"name": "AIDS", "buttons": [
        {"action": "tc_down", "label": "TC -", "type": "tap", "field": "tc_level"},
        {"action": "tc_up", "label": "TC +", "type": "tap", "field": "tc_level"},
        {"action": "tc_cut_down", "label": "TC CUT -", "type": "tap", "field": "tc_cut_level"},
        {"action": "tc_cut_up", "label": "TC CUT +", "type": "tap", "field": "tc_cut_level"},
        {"action": "abs_down", "label": "ABS -", "type": "tap", "field": "abs_level"},
        {"action": "abs_up", "label": "ABS +", "type": "tap", "field": "abs_level"},
        {"action": "esc_down", "label": "ESC -", "type": "tap", "field": "esc_level"},
        {"action": "esc_up", "label": "ESC +", "type": "tap", "field": "esc_level"},
        {"action": "bias_rear", "label": "BB REAR", "type": "tap", "field": "brake_bias"},
        {"action": "bias_front", "label": "BB FRONT", "type": "tap", "field": "brake_bias"},
        {"action": "map_down", "label": "MAP -", "type": "tap", "field": "engine_map"},
        {"action": "map_up", "label": "MAP +", "type": "tap", "field": "engine_map"},
    ]},
    {"name": "CAR", "buttons": [
        {"action": "pit_limiter", "label": "PIT LIMITER", "type": "tap", "field": "pit_limiter"},
        {"action": "lights", "label": "LIGHTS", "type": "tap", "field": "lights"},
        {"action": "flash", "label": "FLASH", "type": "hold"},
        {"action": "wipers", "label": "WIPERS", "type": "tap", "field": "wipers"},
        {"action": "ignition", "label": "IGNITION", "type": "hold", "field": "ignition"},
        {"action": "starter", "label": "STARTER", "type": "hold", "field": "engine_running"},
        {"action": "indicator_left", "label": "IND LEFT", "type": "tap"},
        {"action": "indicator_right", "label": "IND RIGHT", "type": "tap"},
        {"action": "hazards", "label": "HAZARDS", "type": "tap"},
        {"action": "horn", "label": "HORN", "type": "hold"},
    ]},
    {"name": "VIEW", "buttons": [
        {"action": "camera", "label": "CAMERA", "type": "tap"},
        {"action": "hud", "label": "HUD", "type": "tap"},
        {"action": "mirror", "label": "MIRROR", "type": "tap"},
        {"action": "display", "label": "DISPLAY PAGE", "type": "tap"},
        {"action": "look_left", "label": "LOOK LEFT", "type": "hold"},
        {"action": "look_back", "label": "LOOK BACK", "type": "hold"},
        {"action": "look_right", "label": "LOOK RIGHT", "type": "hold"},
        {"action": "leaderboard", "label": "LEADERBOARD", "type": "tap"},
    ]},
    {"name": "PIT", "buttons": [
        {"action": "pause", "label": "PAUSE / ESC", "type": "tap"},
        {"action": "recover", "label": "RECOVER", "type": "tap"},
        {"action": "auto_shifter", "label": "AUTO SHIFT", "type": "tap"},
        {"action": "shift_down", "label": "SHIFT -", "type": "tap", "field": "gear"},
        {"action": "shift_up", "label": "SHIFT +", "type": "tap", "field": "gear"},
        {"action": "neutral", "label": "NEUTRAL", "type": "tap"},
        {"action": "save_replay", "label": "SAVE REPLAY", "type": "tap"},
    ]},
]

BY_NAME = {button["action"]: button for group in GROUPS for button in group["buttons"]}


def layout(keys: dict, handled: set, kinds: dict | None = None) -> list[dict]:
    """The button groups for the UI, with `enabled` set per button for the active game and the type
    replaced by the game's own kind ([kinds] in game.toml) where it has one."""
    kinds = kinds or {}
    out = []
    for group in GROUPS:
        buttons = [dict(b, enabled=bool(keys.get(b["action"])) or b["action"] in handled,
                        type=kinds.get(b["action"], b["type"])) for b in group["buttons"]]
        out.append({"name": group["name"], "buttons": buttons})
    return out

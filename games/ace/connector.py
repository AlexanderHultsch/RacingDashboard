"""Assetto Corsa EVO connector: reads the game's shared memory (Windows).

ACE (v0.6 and later) publishes three named shared memory blocks:
    Local\\acevo_pmf_physics   800 bytes, physics at the physics rate (same layout as ACC, core/kunos.py)
    Local\\acevo_pmf_graphics  HUD values: shift lights, aids, fuel, timing ...
    Local\\acevo_pmf_static    session and track, written at session start

The layouts below follow Kunos' "ACE_SharedFileOut_Documentation_v1" (31 Mar / 1 Apr 2026).
Only reading is possible: the buttons are keypresses, sent by the core.
Field notes and what is not verified yet: docs/ACE/NOTES.md.
"""
import time
from ctypes import Structure, c_bool, c_byte, c_char, c_float, c_int8, c_int16, c_int32, c_uint8, c_uint16, c_uint32, c_uint64, sizeof

import log
import telemetry
import winmem
from kunos import Physics, boost  # noqa: F401  (the physics page is shared with AC / ACC / Assetto Corsa Rally)

PHYSICS_TAG = "Local\\acevo_pmf_physics"
GRAPHICS_TAG = "Local\\acevo_pmf_graphics"
STATIC_TAG = "Local\\acevo_pmf_static"
REOPEN_S = 1.0          # retry interval while the game is not running
STALE_REOPEN_S = 5.0    # reattach after this long without new data (detects a closed game)
STATUS = {0: "off", 1: "replay", 2: "live", 3: "pause"}   # ACEVO_STATUS, assumed as in AC / ACC


class Static(Structure):
    _pack_ = 4
    _fields_ = [
        ("sm_version", c_char * 15), ("ac_evo_version", c_char * 15), ("session", c_int32),
        ("session_name", c_char * 33), ("event_id", c_uint8), ("session_id", c_uint8), ("starting_grip", c_int32),
        ("starting_ambient_temperature_c", c_float), ("starting_ground_temperature_c", c_float),
        ("is_static_weather", c_bool), ("is_timed_race", c_bool), ("is_online", c_bool),
        ("number_of_sessions", c_int32), ("nation", c_char * 33), ("longitude", c_float), ("latitude", c_float),
        ("track", c_char * 33), ("track_configuration", c_char * 33), ("track_length_m", c_float),
    ]


class TyreState(Structure):          # 256 bytes
    _pack_ = 4
    _fields_ = [
        ("slip", c_float), ("lock", c_bool), ("tyre_pressure", c_float), ("tyre_temperature_c", c_float),
        ("brake_temperature_c", c_float), ("brake_pressure", c_float), ("tyre_temperature_left", c_float),
        ("tyre_temperature_center", c_float), ("tyre_temperature_right", c_float),
        ("tyre_compound_front", c_char * 33), ("tyre_compound_rear", c_char * 33),
        ("tyre_normalized_pressure", c_float), ("tyre_normalized_temperature_left", c_float),
        ("tyre_normalized_temperature_center", c_float), ("tyre_normalized_temperature_right", c_float),
        ("brake_normalized_temperature", c_float), ("tyre_normalized_temperature_core", c_float),
        ("_reserved", c_byte * 128),
    ]


class DamageState(Structure):        # 128 bytes
    _pack_ = 4
    _fields_ = [("damage", c_float * 9), ("_reserved", c_byte * 92)]


class PitInfo(Structure):            # 64 bytes
    _pack_ = 4
    _fields_ = [("items", c_int8 * 6), ("_reserved", c_byte * 58)]


class Electronics(Structure):        # 128 bytes
    _pack_ = 4
    _fields_ = [
        ("tc_level", c_int8), ("tc_cut_level", c_int8), ("abs_level", c_int8), ("esc_level", c_int8),
        ("ebb_level", c_int8), ("brake_bias", c_float), ("engine_map_level", c_int8), ("turbo_level", c_float),
        ("ers_deployment_map", c_int8), ("ers_recharge_map", c_float), ("is_ers_heat_charging_on", c_bool),
        ("is_ers_overtake_mode_on", c_bool), ("is_drs_open", c_bool), ("diff_power_level", c_int8),
        ("diff_coast_level", c_int8), ("front_bump_damper_level", c_int8), ("front_rebound_damper_level", c_int8),
        ("rear_bump_damper_level", c_int8), ("rear_rebound_damper_level", c_int8), ("is_ignition_on", c_bool),
        ("is_pitlimiter_on", c_bool), ("active_performance_mode", c_int8), ("_reserved", c_byte * 88),
    ]


class Instrumentation(Structure):    # 128 bytes
    _pack_ = 4
    _fields_ = [
        ("main_light_stage", c_int8), ("special_light_stage", c_int8), ("cockpit_light_stage", c_int8),
        ("wiper_level", c_int8), ("rain_lights", c_bool), ("direction_light_left", c_bool),
        ("direction_light_right", c_bool), ("flashing_lights", c_bool), ("warning_lights", c_bool),
        ("selected_display_index", c_int8), ("display_current_page_index", c_int8 * 16),
        ("are_headlights_visible", c_bool), ("_reserved", c_byte * 101),
    ]


class SessionState(Structure):       # 256 bytes
    _pack_ = 4
    _fields_ = [
        ("phase_name", c_char * 33), ("time_left", c_char * 15), ("time_left_ms", c_int32),
        ("wait_time", c_char * 15), ("total_lap", c_int32), ("current_lap", c_int32), ("lights_on", c_int32),
        ("lights_mode", c_int32), ("lap_length_km", c_float), ("end_session_flag", c_int32),
        ("time_to_next_session", c_char * 15), ("flags", c_bool * 6), ("_reserved", c_byte * 143),
    ]


class TimingState(Structure):        # 256 bytes
    _pack_ = 4
    _fields_ = [
        ("current_laptime", c_char * 15), ("delta_current", c_char * 15), ("delta_current_p", c_int32),
        ("last_laptime", c_char * 15), ("delta_last", c_char * 15), ("delta_last_p", c_int32),
        ("best_laptime", c_char * 15), ("ideal_laptime", c_char * 15), ("total_time", c_char * 15),
        ("is_invalid", c_bool), ("_reserved", c_byte * 138),
    ]


class AssistsState(Structure):       # 64 bytes
    _pack_ = 4
    _fields_ = [
        ("flags", c_uint8 * 7), ("auto_steer", c_float), ("arcade_stability_control", c_float),
        ("_reserved", c_byte * 48),
    ]


class Graphics(Structure):
    _pack_ = 4
    _fields_ = [
        ("packetId", c_int32), ("status", c_int32), ("focused_car_id_a", c_uint64), ("focused_car_id_b", c_uint64),
        ("player_car_id_a", c_uint64), ("player_car_id_b", c_uint64), ("rpm", c_uint16),
        ("is_rpm_limiter_on", c_bool), ("is_change_up_rpm", c_bool), ("is_change_down_rpm", c_bool),
        ("tc_active", c_bool), ("abs_active", c_bool), ("esc_active", c_bool), ("launch_active", c_bool),
        ("is_ignition_on", c_bool), ("is_engine_running", c_bool), ("kers_is_charging", c_bool),
        ("is_wrong_way", c_bool), ("is_drs_available", c_bool), ("battery_is_charging", c_bool),
        ("is_max_kj_per_lap_reached", c_bool), ("is_max_charge_kj_per_lap_reached", c_bool),
        ("display_speed_kmh", c_int16), ("display_speed_mph", c_int16), ("display_speed_ms", c_int16),
        ("pitspeeding_delta", c_float), ("gear_int", c_int16), ("rpm_percent", c_float), ("gas_percent", c_float),
        ("brake_percent", c_float), ("handbrake_percent", c_float), ("clutch_percent", c_float),
        ("steering_percent", c_float), ("ffb_strength", c_float), ("car_ffb_multiplier", c_float),
        ("water_temperature_percent", c_float), ("water_pressure_bar", c_float), ("fuel_pressure_bar", c_float),
        ("water_temperature_c", c_int8), ("air_temperature_c", c_int8), ("oil_temperature_c", c_float),
        ("oil_pressure_bar", c_float), ("exhaust_temperature_c", c_float), ("g_forces_x", c_float),
        ("g_forces_y", c_float), ("g_forces_z", c_float), ("turbo_boost", c_float), ("turbo_boost_level", c_float),
        ("turbo_boost_perc", c_float), ("steer_degrees", c_int32), ("current_km", c_float), ("total_km", c_uint32),
        ("total_driving_time_s", c_uint32), ("time_of_day_hours", c_int32), ("time_of_day_minutes", c_int32),
        ("time_of_day_seconds", c_int32), ("delta_time_ms", c_int32), ("current_lap_time_ms", c_int32),
        ("predicted_lap_time_ms", c_int32), ("fuel_liter_current_quantity", c_float),
        ("fuel_liter_current_quantity_percent", c_float), ("fuel_liter_per_km", c_float),
        ("km_per_fuel_liter", c_float), ("current_torque", c_float), ("current_bhp", c_int32),
        ("tyre_lf", TyreState), ("tyre_rf", TyreState), ("tyre_lr", TyreState), ("tyre_rr", TyreState),
        ("npos", c_float), ("kers_charge_perc", c_float), ("kers_current_perc", c_float),
        ("control_lock_time", c_float), ("car_damage", DamageState), ("car_location", c_int32),
        ("pit_info", PitInfo), ("fuel_liter_used", c_float), ("fuel_liter_per_lap", c_float),
        ("laps_possible_with_fuel", c_float), ("battery_temperature", c_float), ("battery_voltage", c_float),
        ("instantaneous_fuel_liter_per_km", c_float), ("instantaneous_km_per_fuel_liter", c_float),
        ("gear_rpm_window", c_float), ("instrumentation", Instrumentation),
        ("instrumentation_min_limit", Instrumentation), ("instrumentation_max_limit", Instrumentation),
        ("electronics", Electronics), ("electronics_min_limit", Electronics),
        ("electronics_max_limit", Electronics), ("electronics_is_modifiable", Electronics),
        ("total_lap_count", c_int32), ("current_pos", c_uint32), ("total_drivers", c_uint32),
        ("last_laptime_ms", c_int32), ("best_laptime_ms", c_int32), ("flag", c_int32), ("global_flag", c_int32),
        ("max_gears", c_uint32), ("engine_type", c_int32), ("has_kers", c_bool), ("is_last_lap", c_bool),
        ("performance_mode_name", c_char * 33), ("diff_coast_raw_value", c_float),
        ("diff_power_raw_value", c_float), ("race_cut_gained_time_ms", c_int32),
        ("distance_to_deadline", c_int32), ("race_cut_current_delta", c_float),
        ("session_state", SessionState), ("timing_state", TimingState), ("player_ping", c_int32),
        ("player_latency", c_int32), ("player_cpu_usage", c_int32), ("player_cpu_usage_avg", c_int32),
        ("player_qos", c_int32), ("player_qos_avg", c_int32), ("player_fps", c_int32),
        ("player_fps_avg", c_int32), ("driver_name", c_char * 33), ("driver_surname", c_char * 33),
        ("car_model", c_char * 33), ("is_in_pit_box", c_bool), ("is_in_pit_lane", c_bool),
        ("is_valid_lap", c_bool), ("car_coordinates", (c_float * 3) * 60), ("gap_ahead", c_float),
        ("gap_behind", c_float), ("active_cars", c_uint8), ("fuel_per_lap", c_float),
        ("fuel_estimated_laps", c_float), ("assists_state", AssistsState), ("max_fuel", c_float),
        ("max_turbo_boost", c_float), ("use_single_compound", c_bool),
        ("car_ids", (c_uint64 * 2) * 60),      # driver id per car_coordinates slot (lower, upper 64 bits)
    ]


for _struct, _size in ((TyreState, 256), (DamageState, 128), (PitInfo, 64), (Electronics, 128),
                       (Instrumentation, 128), (SessionState, 256), (TimingState, 256), (AssistsState, 64), (Physics, 800)):
    assert sizeof(_struct) == _size, (_struct.__name__, sizeof(_struct))


def text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace").strip()


def share(value: float):
    """A 0..1 share (diff locking), None when the game sends nothing or something outside 0..1."""
    return round(value, 3) if 0 < value <= 1 else None


def lap_time(ms: int):
    return ms if 0 < ms < 2_147_000_000 else None


def setting(gr, field: str):
    """(value, adjustable, range) of a stepped electronics setting; value None when the car does not have
    it, range [low, high] only when the driver can change it. A setting the driver cannot change still
    counts when the game gives it a range above 0 and the value lies in it: the BMW M4 CSL reports ABS 1
    with min 1, max 1 and is_modifiable 0."""
    current = int(getattr(gr.electronics, field))
    low, high = int(getattr(gr.electronics_min_limit, field)), int(getattr(gr.electronics_max_limit, field))
    if getattr(gr.electronics_is_modifiable, field):
        return current, high > low, [low, high] if high > low else None
    if high > 0 and low <= current <= high:
        return current, False, None
    return None, False, None


# universal name -> ACE electronics field (current value, range and "car has it")
STEPPED = {"tc_level": "tc_level", "tc_cut_level": "tc_cut_level", "abs_level": "abs_level", "esc_level": "esc_level",
           "engine_map": "engine_map_level", "diff_power": "diff_power_level", "diff_coast": "diff_coast_level",
           "drive_mode": "active_performance_mode"}


def from_one(step: tuple) -> tuple:
    """ACE counts the engine map from 0, the car's display and HUD from 1 (Porsche 992 GT3 R: 1-3, ACE 0-2)."""
    value, adjustable, limit = step
    return (None if value is None else value + 1, adjustable, [limit[0] + 1, limit[1] + 1] if limit else None)


def tyres(ph, gr) -> tuple[list | None, list | None, list | None]:
    """Tyre temperatures (C), pressures (psi) and brake temperatures (C), front left, front right, rear left,
    rear right: from the graphics tyre blocks, else the physics page. A pressure below 6 is taken as bar and
    shown in psi. Not checked in the game yet (docs/ACE/NOTES.md)."""
    blocks = (gr.tyre_lf, gr.tyre_rf, gr.tyre_lr, gr.tyre_rr)
    temps = [b.tyre_temperature_c for b in blocks]
    if not any(t > 0 for t in temps):
        temps = list(ph.tyreCoreTemperature)
    psi = [b.tyre_pressure for b in blocks]
    if not any(p > 0 for p in psi):
        psi = list(ph.wheelsPressure)
    brakes = [b.brake_temperature_c for b in blocks]
    if not any(t > 0 for t in brakes):
        brakes = list(ph.brakeTemp)
    temps = [round(t, 1) if 0 < t < 400 else None for t in temps]
    psi = [round(p * 14.5038 if p < 6 else p, 1) if 0 < p < 100 else None for p in psi]
    brakes = [round(t) if 0 < t < 2000 else None for t in brakes]
    return (temps if any(temps) else None), (psi if any(psi) else None), (brakes if any(brakes) else None)


# Warning lamp thresholds (ACE reports the values, not the lamps; these follow common road-car dashes)
COOLANT_COLD_C = 50
COOLANT_HOT_C = 108
COOLANT_ALERT_C = 118
OIL_HOT_C = 135
OIL_LOW_BAR = 0.5
HANDBRAKE_ON = 0.05


def warnings(ph, gr) -> dict:
    """Warning lamp states from the values ACE reports (see core/telemetry.py, warn_*)."""
    ignition, running = bool(gr.is_ignition_on), bool(gr.is_engine_running)
    water, oil_c, oil_bar = gr.water_temperature_c, gr.oil_temperature_c, gr.oil_pressure_bar
    if not ignition:
        return {"warn_brake": "off", "warn_engine": "off", "warn_oil": "off", "warn_coolant": "off"}
    coolant = ("alert" if water >= COOLANT_ALERT_C else "warn" if water >= COOLANT_HOT_C
               else "cold" if 0 < water < COOLANT_COLD_C else "off")
    oil = "alert" if not running or (oil_bar > 0 and oil_bar < OIL_LOW_BAR) else "warn" if oil_c >= OIL_HOT_C else "off"
    return {
        "warn_brake": "alert" if gr.handbrake_percent > HANDBRAKE_ON else "off",
        "warn_engine": "warn" if not running else "alert" if coolant == "alert" else "off",
        "warn_oil": oil,
        "warn_coolant": coolant,
    }


def player_xy(gr) -> tuple[float | None, float | None]:
    """The player's car position on the map (x, z of car_coordinates; y is the height). The slot whose
    driver id matches player_car_id; slot 0 if none matches (single player). Not verified in the game."""
    slot = 0
    for i in range(60):
        if gr.car_ids[i][0] == gr.player_car_id_a and gr.car_ids[i][1] == gr.player_car_id_b and (gr.player_car_id_a or gr.player_car_id_b):
            slot = i
            break
    x, _, z = gr.car_coordinates[slot]
    return (round(x, 2), round(z, 2)) if (x or z) else (None, None)


def parse(physics: bytes, graphics: bytes, static: bytes) -> dict:
    """Raw shared memory bytes -> universal telemetry (core/telemetry.py)."""
    ph = Physics.from_buffer_copy(physics[:sizeof(Physics)])
    gr = Graphics.from_buffer_copy(graphics[:sizeof(Graphics)])
    st = Static.from_buffer_copy(static[:sizeof(Static)])
    el = gr.electronics
    steps = {name: setting(gr, field) for name, field in STEPPED.items()}
    steps["engine_map"] = from_one(steps["engine_map"])
    rpm_max = max(0, ph.currentMaxRpm)
    rpm_pct = gr.rpm_percent
    if rpm_pct > 1.5:                       # guard in case a build sends percent instead of 0..1
        rpm_pct /= 100
    if rpm_pct <= 0 and rpm_max:
        rpm_pct = ph.rpms / rpm_max
    best = lap_time(gr.best_laptime_ms)
    xy = player_xy(gr)
    tyre_values = tyres(ph, gr)
    return {
        "status": STATUS.get(gr.status, "live"),
        "car": text(gr.car_model),
        "track": text(st.track),
        "gear": ph.gear - 1,                # ACE: 0 = R, 1 = N, 2 = 1st
        "max_gears": int(gr.max_gears),
        "rpm": max(0, ph.rpms),
        "rpm_max": rpm_max,
        "rpm_pct": round(min(max(rpm_pct, 0.0), 1.2), 4),
        "shift_up": bool(gr.is_change_up_rpm),
        "shift_down": bool(gr.is_change_down_rpm),
        "limiter": bool(gr.is_rpm_limiter_on),
        "speed_kmh": round(max(0.0, ph.speedKmh), 1),
        "gas": round(ph.gas, 3),
        "brake": round(ph.brake, 3),
        "clutch": round(ph.clutch, 3),
        "tc_level": steps["tc_level"][0],
        "tc_cut_level": steps["tc_cut_level"][0],
        "tc_active": bool(gr.tc_active or ph.tcInAction),
        "abs_level": steps["abs_level"][0],
        "abs_active": bool(gr.abs_active or ph.absInAction),
        "brake_bias": round(ph.brakeBias, 4) if ph.brakeBias > 0 else None,
        "engine_map": steps["engine_map"][0],
        "esc_level": steps["esc_level"][0],
        "esc_active": bool(gr.esc_active),
        "diff_power": steps["diff_power"][0],
        "diff_coast": steps["diff_coast"][0],
        "diff_power_pct": share(gr.diff_power_raw_value),
        "diff_coast_pct": share(gr.diff_coast_raw_value),
        # the mode name stays from the last car on cars without modes: only with a mode
        "drive_mode": steps["drive_mode"][0],
        "drive_mode_name": (text(gr.performance_mode_name) or None) if steps["drive_mode"][0] is not None else None,
        "tyre_temp_c": tyre_values[0],
        "tyre_psi": tyre_values[1],
        "brake_temp_c": tyre_values[2],
        # boost page: graphics turbo_boost (physics turboBoost as a fallback), max_turbo_boost 0 = no turbo
        **boost(gr.turbo_boost or ph.turboBoost, gr.max_turbo_boost),
        # ACE's auto_gear assist shifts a manual gearbox for the driver, so the gear page keeps the gear
        # number. ACE reports no P / D / S selector for real automatic or electric cars yet.
        "gear_mode": None,
        **warnings(ph, gr),
        "limits": {name: limit for name, (_, _, limit) in steps.items() if limit},
        "fixed": [name for name, (value, adjustable, _) in steps.items() if value is not None and not adjustable],
        "pit_limiter": bool(ph.pitLimiterOn or el.is_pitlimiter_on),
        "ignition": bool(gr.is_ignition_on),
        "engine_running": bool(gr.is_engine_running),
        "lights": int(gr.instrumentation.main_light_stage),
        "wipers": int(gr.instrumentation.wiper_level),
        "fuel_l": round(gr.fuel_liter_current_quantity, 2),
        "fuel_max_l": round(gr.max_fuel, 1) if gr.max_fuel > 0 else None,
        "fuel_per_lap_l": round(gr.fuel_liter_per_lap or gr.fuel_per_lap, 2) or None,
        "lap": max(0, gr.total_lap_count),
        "position": int(gr.current_pos),
        "cars": int(gr.total_drivers),
        "lap_ms": lap_time(gr.current_lap_time_ms),
        "last_ms": lap_time(gr.last_laptime_ms),
        "best_ms": best,
        "delta_ms": gr.delta_time_ms if best else None,
        "lap_valid": bool(gr.is_valid_lap),
        # analysis page
        "lap_pos": round(min(max(gr.npos, 0.0), 1.0), 6),
        "track_length_m": round(st.track_length_m, 1) if st.track_length_m > 0 else None,
        "pos_x": xy[0],
        "pos_y": xy[1],
        "steer": round(max(-1.0, min(1.0, ph.steerAngle)), 3),
        "session_id": f"{st.event_id}-{st.session_id}-{st.session}-{text(st.session_name)}",
        "air_c": round(ph.airTemp, 1),
        "road_c": round(ph.roadTemp, 1),
        "tyre_compound": text(gr.tyre_lf.tyre_compound_front) or None,
        "time_of_day": f"{gr.time_of_day_hours:02d}:{gr.time_of_day_minutes:02d}",
    }


def unreported(values: dict, reported: set) -> None:
    """ACE 0.9.1 leaves the live light / wiper stages at 0 even when they work in the car (docs/ACE/NOTES.md),
    so 0 means "not reported" (None) until the game has sent a stage above 0 once in this session."""
    for name in ("lights", "wipers"):
        if values[name]:
            reported.add(name)
        elif name not in reported:
            values[name] = None


INSTRUMENTATION = ("main_light_stage", "special_light_stage", "cockpit_light_stage", "wiper_level", "rain_lights",
                   "direction_light_left", "direction_light_right", "flashing_lights", "warning_lights",
                   "selected_display_index", "are_headlights_visible")
ASSISTS = ("auto_gear", "auto_blip", "auto_clutch", "auto_clutch_on_start", "manual_ignition_e_start",
           "auto_pit_limiter", "standing_start_assist")


def watched(gr) -> dict:
    """Rarely changing raw values, logged on change to check their meaning in the game
    (lights / wipers stages and their range on this car, the assists order)."""
    inst, low, high = gr.instrumentation, gr.instrumentation_min_limit, gr.instrumentation_max_limit
    out = {name: int(getattr(inst, name)) for name in INSTRUMENTATION}
    for name in ("main_light_stage", "wiper_level"):
        out[name + "_range"] = f"{int(getattr(low, name))}..{int(getattr(high, name))}"
    out.update((name, int(gr.assists_state.flags[i])) for i, name in enumerate(ASSISTS))
    return out


def changes(before: dict | None, after: dict) -> str:
    if before is None:
        return " ".join(f"{name}={value}" for name, value in after.items())
    return " ".join(f"{name} {before[name]}->{value}" for name, value in after.items() if before[name] != value)


class Connector(telemetry.Connector):
    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.blocks = None
        self.next_try = 0.0
        self.attached_at = 0.0
        self.last_packet = None
        self.last_change = 0.0
        self.stale_s = cfg["telemetry"]["stale_s"]
        self.version = None
        self.watched = None
        self.reported = set()     # lights / wipers once the game sent a stage above 0

    def attach(self) -> bool:
        now = time.monotonic()
        if now < self.next_try:
            return False
        self.next_try = now + REOPEN_S
        blocks = []
        try:
            for tag, struct in ((PHYSICS_TAG, Physics), (GRAPHICS_TAG, Graphics), (STATIC_TAG, Static)):
                blocks.append(winmem.SharedMemory(tag, sizeof(struct)))
        except FileNotFoundError:
            for block in blocks:
                block.close()
            return False
        self.blocks, self.attached_at = blocks, now
        # Log the game and shared memory version once: if values look wrong after a game update,
        # the log shows which layout the game publishes (the connector follows layout v1).
        static = Static.from_buffer_copy(blocks[2].read()[:sizeof(Static)])
        version = (text(static.ac_evo_version), text(static.sm_version))
        if version != self.version:
            self.version = version
            log.line("ace", "shared memory", f"game {version[0] or '?'}, layout {version[1] or '?'}")
        return True

    def read(self) -> dict | None:
        if self.blocks is None and not self.attach():
            return None
        physics, graphics, static = (block.read() for block in self.blocks)
        values = parse(physics, graphics, static)
        unreported(values, self.reported)
        raw = watched(Graphics.from_buffer_copy(graphics[:sizeof(Graphics)]))
        if raw != self.watched:
            log.line("ace", "raw", changes(self.watched, raw))
            self.watched = raw
        now = time.monotonic()
        packet = (physics[:4], graphics[:4])
        if packet != self.last_packet:
            self.last_packet, self.last_change = packet, now
        values["connected"] = now - self.last_change < self.stale_s
        if not values["connected"]:
            values["status"] = "pause" if values["status"] == "live" else values["status"]
            if now - self.attached_at > STALE_REOPEN_S:
                # Our own handle keeps the block alive after the game closed, so it would still
                # read the last values. Reattach now and then: if the game is gone, that fails.
                self.close()
                self.next_try = 0.0
        return values

    def close(self) -> None:
        for block in self.blocks or ():
            block.close()
        self.blocks = None

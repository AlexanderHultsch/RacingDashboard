"""Assetto Corsa EVO connector: reads the game's shared memory (Windows).

ACE (v0.6 and later) publishes three named shared memory blocks:
    Local\\acevo_pmf_physics   800 bytes, physics at the physics rate (same layout as ACC)
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

PHYSICS_TAG = "Local\\acevo_pmf_physics"
GRAPHICS_TAG = "Local\\acevo_pmf_graphics"
STATIC_TAG = "Local\\acevo_pmf_static"
REOPEN_S = 1.0          # retry interval while the game is not running
STALE_REOPEN_S = 5.0    # reattach after this long without new data (detects a closed game)
STATUS = {0: "off", 1: "replay", 2: "live", 3: "pause"}   # ACEVO_STATUS, assumed as in AC / ACC


class Physics(Structure):
    _pack_ = 4
    _fields_ = [
        ("packetId", c_int32), ("gas", c_float), ("brake", c_float), ("fuel", c_float),
        ("gear", c_int32), ("rpms", c_int32), ("steerAngle", c_float), ("speedKmh", c_float),
        ("velocity", c_float * 3), ("accG", c_float * 3), ("wheelSlip", c_float * 4),
        ("wheelLoad", c_float * 4), ("wheelsPressure", c_float * 4), ("wheelAngularSpeed", c_float * 4),
        ("tyreWear", c_float * 4), ("tyreDirtyLevel", c_float * 4), ("tyreCoreTemperature", c_float * 4),
        ("camberRAD", c_float * 4), ("suspensionTravel", c_float * 4), ("drs", c_float), ("tc", c_float),
        ("heading", c_float), ("pitch", c_float), ("roll", c_float), ("cgHeight", c_float),
        ("carDamage", c_float * 5), ("numberOfTyresOut", c_int32), ("pitLimiterOn", c_int32), ("abs", c_float),
        ("kersCharge", c_float), ("kersInput", c_float), ("autoShifterOn", c_int32), ("rideHeight", c_float * 2),
        ("turboBoost", c_float), ("ballast", c_float), ("airDensity", c_float), ("airTemp", c_float),
        ("roadTemp", c_float), ("localAngularVel", c_float * 3), ("finalFF", c_float), ("performanceMeter", c_float),
        ("engineBrake", c_int32), ("ersRecoveryLevel", c_int32), ("ersPowerLevel", c_int32),
        ("ersHeatCharging", c_int32), ("ersIsCharging", c_int32), ("kersCurrentKJ", c_float),
        ("drsAvailable", c_int32), ("drsEnabled", c_int32), ("brakeTemp", c_float * 4), ("clutch", c_float),
        ("tyreTempI", c_float * 4), ("tyreTempM", c_float * 4), ("tyreTempO", c_float * 4),
        # ACE additions from offset 416
        ("isAIControlled", c_int32), ("tyreContactPoint", (c_float * 3) * 4),
        ("tyreContactNormal", (c_float * 3) * 4), ("tyreContactHeading", (c_float * 3) * 4),
        ("brakeBias", c_float), ("localVelocity", c_float * 3), ("P2PActivations", c_int32),
        ("P2PStatus", c_int32), ("currentMaxRpm", c_int32), ("mz", c_float * 4), ("fx", c_float * 4),
        ("fy", c_float * 4), ("slipRatio", c_float * 4), ("slipAngle", c_float * 4), ("tcInAction", c_int32),
        ("absInAction", c_int32), ("suspensionDamage", c_float * 4), ("tyreTemp", c_float * 4),
        ("waterTemp", c_float), ("brakeTorque", c_float * 4), ("frontBrakeCompound", c_int32),
        ("rearBrakeCompound", c_int32), ("padLife", c_float * 4), ("discLife", c_float * 4),
        ("ignitionOn", c_int32), ("starterEngineOn", c_int32), ("isEngineRunning", c_int32),
        ("kerbVibration", c_float), ("slipVibrations", c_float), ("roadVibrations", c_float), ("absVibrations", c_float),
    ]


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
    ]


for _struct, _size in ((TyreState, 256), (DamageState, 128), (PitInfo, 64), (Electronics, 128),
                       (Instrumentation, 128), (SessionState, 256), (TimingState, 256), (AssistsState, 64), (Physics, 800)):
    assert sizeof(_struct) == _size, (_struct.__name__, sizeof(_struct))


def text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace").strip()


def lap_time(ms: int):
    return ms if 0 < ms < 2_147_000_000 else None


def level(current: int, modifiable: int):
    return int(current) if modifiable else None


# universal name -> ACE electronics field (current value, range and "car has it")
STEPPED = {"tc_level": "tc_level", "abs_level": "abs_level", "esc_level": "esc_level",
           "engine_map": "engine_map_level", "diff_power": "diff_power_level", "diff_coast": "diff_coast_level"}


def limits(gr) -> dict:
    """The range of each stepped setting the car has, from the min / max limit blocks."""
    out = {}
    for name, field in STEPPED.items():
        if getattr(gr.electronics_is_modifiable, field):
            low, high = int(getattr(gr.electronics_min_limit, field)), int(getattr(gr.electronics_max_limit, field))
            if high > low:
                out[name] = [low, high]
    return out


def parse(physics: bytes, graphics: bytes, static: bytes) -> dict:
    """Raw shared memory bytes -> universal telemetry (core/telemetry.py)."""
    ph = Physics.from_buffer_copy(physics[:sizeof(Physics)])
    gr = Graphics.from_buffer_copy(graphics[:sizeof(Graphics)])
    st = Static.from_buffer_copy(static[:sizeof(Static)])
    el, can = gr.electronics, gr.electronics_is_modifiable
    rpm_max = max(0, ph.currentMaxRpm)
    rpm_pct = gr.rpm_percent
    if rpm_pct > 1.5:                       # guard in case a build sends percent instead of 0..1
        rpm_pct /= 100
    if rpm_pct <= 0 and rpm_max:
        rpm_pct = ph.rpms / rpm_max
    best = lap_time(gr.best_laptime_ms)
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
        "tc_level": level(el.tc_level, can.tc_level),
        "tc_active": bool(gr.tc_active or ph.tcInAction),
        "abs_level": level(el.abs_level, can.abs_level),
        "abs_active": bool(gr.abs_active or ph.absInAction),
        "brake_bias": round(ph.brakeBias, 4) if ph.brakeBias > 0 else None,
        "engine_map": level(el.engine_map_level, can.engine_map_level),
        "esc_level": level(el.esc_level, can.esc_level),
        "diff_power": level(el.diff_power_level, can.diff_power_level),
        "diff_coast": level(el.diff_coast_level, can.diff_coast_level),
        "launch": bool(gr.launch_active),
        "auto_clutch": bool(gr.assists_state.flags[2]),     # assists: auto_gear, auto_blip, auto_clutch, ...
        # automatic gearbox assist on: the gear page shows D (ACE reports no P / S selector or sport mode)
        "gear_mode": "D" if gr.assists_state.flags[0] else None,
        "limits": limits(gr),
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
    }


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

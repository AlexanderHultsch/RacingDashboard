"""The physics page of Kunos' shared memory, shared by Assetto Corsa, Assetto Corsa Competizione, Assetto
Corsa EVO (Local\\acevo_pmf_physics) and Assetto Corsa Rally (Local\\acpmf_physics): 800 bytes, the ACC
SPageFilePhysics layout. The first 416 bytes are AC1's; the rest follows ACC (ACE documents it as the same
page). Used by games/ace and games/acr.
"""
from ctypes import Structure, c_float, c_int32


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


assert __import__("ctypes").sizeof(Physics) == 800


def slips(ph) -> list | None:
    """Slip ratio of each wheel (front left, front right, rear left, rear right) from the physics page: negative
    braking, positive wheelspin (the usual sign, not yet checked in the game: docs/ACE/NOTES.md). None while the
    game leaves them all at 0 (a game or build that does not fill them)."""
    values = list(ph.slipRatio)
    if not any(values) or any(v != v for v in values):
        return None
    return [round(max(-1.0, min(3.0, v)), 3) for v in values]


def boost(value: float, peak: float) -> dict:
    """Boost page fields from a Kunos game's turbo boost and the car's maximum boost (both in bar; 0 = the car
    has no turbo). Not yet checked in a turbo car (docs/ACE/NOTES.md)."""
    turbo = peak > 0 or value > 0.01
    return {
        "turbo": turbo,
        "boost_bar": round(max(0.0, value), 3) if turbo else None,
        "boost_min_bar": 0.0,
        "boost_max_bar": round(peak, 2) if peak > 0 else None,
    }

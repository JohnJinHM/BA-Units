"""Canonical database tables, shared by the extractors without crypto dependencies."""

# ScriptableObject string field  ->  output table name.
# Every field below holds an encrypted JSON array (see module docstring).
FIELD_TO_TABLE = {
    "Units": "Units",
    "AbilitiesJson": "Abilities",
    "UnitAbilitiesJson": "UnitAbilities",
    "AmmunitionsJson": "Ammunitions",
    "ArmorsJson": "Armors",
    "MobilityJson": "Mobility",
    "FlyPresetsJson": "PlaneFlyPresets",
    "UnitPropulsionsJson": "UnitPropulsions",
    "CountriesJson": "Countries",
    "TurretsJson": "Turrets",
    "TurretUnitsJson": "TurretUnits",
    "WeaponsJson": "Weapons",
    "TurretWeaponsJson": "TurretWeapons",
    "WeaponAmmunitionsJson": "WeaponAmmunitions",
    "SensorUnitsJson": "SensorUnits",
    "SensorsJson": "Sensors",
    "SquadMembersJson": "SquadMembers",
    "SquadWeaponsJson": "SquadWeapons",
    "ModificationsJson": "Modifications",
    "OptionsJson": "Options",
    "UnitArmorsJson": "UnitArmors",
    "SpecializationAvailabilitiesJson": "SpecializationAvailabilities",
    "SpecializationsJson": "Specializations",
    "TransportAvailabilitiesJson": "TransportAvailabilities",
}

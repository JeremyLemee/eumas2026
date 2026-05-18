from rdflib import Namespace

LabN = Namespace("http://example.org/lab#")

# Core environment identifiers.
myLab = LabN.myLab
Lab = LabN.Lab

# Device state predicates used in the environment KG and action generation.
hasZ1Light = LabN.hasZ1Light
hasZ2Light = LabN.hasZ2Light
hasZ1Blinds = LabN.hasZ1Blinds
hasZ2Blinds = LabN.hasZ2Blinds
hasZ1Level = LabN.hasZ1Level
hasZ2Level = LabN.hasZ2Level
hasSunshine = LabN.hasSunshine
hasLightState = LabN.hasLightState

# Device availability/status predicates.
L1Status = LabN.L1Status
L2Status = LabN.L2Status
B1Status = LabN.B1Status
B2Status = LabN.B2Status

# Goal concepts used by action generation.
open_blinds = LabN.open_blinds
close_blinds = LabN.close_blinds

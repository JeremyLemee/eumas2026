from rdflib import Namespace


BDI = Namespace("http://localhost:8082/ontologies/bdi#")

hasPredicate = BDI.hasPredicate
hasValues = BDI.hasValues
hasStatement = BDI.hasStatement

predicate_ability = BDI.predicate_ability
set = BDI.set
set_env = BDI.set_env
disable_z1_blinds = BDI.disable_z1_blinds
disable_z2_blinds = BDI.disable_z2_blinds

set_goal = BDI.set_goal

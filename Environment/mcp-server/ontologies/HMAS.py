from rdflib import Namespace

# Base namespace for HMAS terms (note trailing slash so terms append correctly)
HMAS = Namespace("https://purl.org/hmas/")

# Classes / properties
recommendsAbility   = HMAS.recommendsAbility
ActionSpecification = HMAS.ActionSpecification
ActionExecution     = HMAS.ActionExecution
conveys             = HMAS.conveys
signifies           = HMAS.signifies
hasId               = HMAS.hasId
recommendsContext   = HMAS.recommendsContext
ResourceProfile     = HMAS.ResourceProfile
expects             = HMAS.expects
hasForm             = HMAS.hasForm
exposesSignifier    = HMAS.exposesSignifier

Signifier           = HMAS.Signifier
Annotation          = HMAS.Annotation
Agent               = HMAS.Agent
Artifact            = HMAS.Artifact
hasState            = HMAS.hasState
hasProcedure        = HMAS.hasProcedure
hasPrecondition     = HMAS.hasPrecondition
hasOperation        = HMAS.hasOperation
hasPostcondition    = HMAS.hasPostcondition
hasGoal             = HMAS.hasGoal
hasAbility          = HMAS.hasAbility
hasCreator          = HMAS.hasCreator

Generation          = HMAS.Generation
Transformation      = HMAS.Transformation
hasCodeLocation     = HMAS.hasCodeLocation

hasAnnotationPolicy = HMAS.hasAnnotationPolicy
hasInteractionPolicy = HMAS.hasInteractionPolicy
NoKnownAnnotation   = HMAS.NoKnownAnnotation
hasKnownAnnotation  = HMAS.hasKnownAnnotation

RecurrentPolicy = HMAS.RecurrentPolicy
hasRecurrentPolicy = HMAS.hasRecurrentPolicy
hasRepetitionTime = HMAS.hasRepetitionTime
hasCallbackUrl = HMAS.hasCallbackUrl
registerProfile = HMAS.registerProfile
queryAnnotations = HMAS.queryAnnotations


__all__ = [
    "HMAS",
    "recommendsAbility",
    "ActionSpecification",
    "ActionExecution",
    "signifies",
    "recommendsContext",
    "ResourceProfile",
    "expects",
    "hasForm",
    "exposesSignifier",
    "Signifier",
    "Agent",
    "Artifact",
    "hasState",
    "hasProcedure",
    "hasPrecondition",
    "hasOperation",
    "hasPostcondition",
    "hasGoal",
    "hasInteractionPolicy",
    "RecurrentPolicy",
    "registerProfile",
    "queryAnnotations",
]

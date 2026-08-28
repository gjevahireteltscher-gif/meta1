module Metonymy.ContextualChecked
  ( contextualFiberChecked
  , ContextualContraction (..)
  , contextualContractionChecked
  ) where

import Metonymy.Contextual
import Metonymy.Ontology (proveRequirement)
import Metonymy.Resolution (contractTarget)
import Metonymy.Types
import Metonymy.Verified (verifyContextLayerWithAgda)

contextualFiberChecked ::
  Snapshot ->
  [Relation] ->
  Int ->
  Context ->
  Either String [FiberStage]
contextualFiberChecked snapshot relations maxDepth context = do
  stages <- contextualFiber snapshot relations maxDepth context
  verifyStages stages
  pure stages
  where
    verifyStages [] = Right ()
    verifyStages (stage : rest) = do
      let prefixContext =
            context
              { contextConstraints =
                  take (stageIndex stage) (contextConstraints context)
              }
          acceptedTargets = stageTargets stage
          rejectedTargets = map obstructionTarget (stageObstructions stage)
      if all (verifyContextLayerWithAgda snapshot prefixContext) acceptedTargets
        then Right ()
        else Left ("agda-rejected-survivor-at-stage-" <> show (stageIndex stage))
      if all
          (not . verifyContextLayerWithAgda snapshot prefixContext)
          rejectedTargets
        then Right ()
        else Left ("agda-accepted-obstruction-at-stage-" <> show (stageIndex stage))
      verifyStages rest

obstructionTarget :: SnapshotObstruction -> EntityId
obstructionTarget (MissingRequirement _ candidate) = candidate
obstructionTarget (MissingRelation _ candidate _ _) = candidate
obstructionTarget (MissingRelated _ candidate _ _) = candidate

data ContextualContraction = ContextualContraction
  { contractionStages :: [FiberStage]
  , contractionSource :: EntityId
  , contractionTarget :: EntityId
  , contractionSafety :: String
  }
  deriving stock (Eq, Show)

contextualContractionChecked ::
  Snapshot ->
  [Relation] ->
  Int ->
  Context ->
  EntityId ->
  Either String ContextualContraction
contextualContractionChecked snapshot relations maxDepth context target = do
  stages <-
    contextualFiberChecked snapshot relations maxDepth context
  finalStage <-
    case reverse stages of
      stage : _ -> Right stage
      [] -> Left "empty-contextual-tower"
  let kb = snapshotKnowledgeBase snapshot
      finalTargets = stageTargets finalStage
      missingStages =
        [ stageIndex stage
        | stage <- stages
        , target `notElem` stageTargets stage
        ]
      generic =
        case proveRequirement kb target (HasSort GenericReading) of
          Just _ -> True
          Nothing -> False
      uniqueEntity =
        case finalTargets of
          [only] -> only == target
          _ -> False
      reverseBridge =
        any
          (\(coarse, _) -> coarseSource coarse == contextSource context)
          (contractTarget kb (HasSort Entity) relations maxDepth target)
  case missingStages of
    [] -> Right ()
    indexes
      | stageIndex finalStage `elem` indexes ->
          Left "explicit-target-not-in-final-fiber"
      | otherwise ->
          Left ("explicit-target-missing-at-stage-" <> show (head indexes))
  if not (generic || uniqueEntity)
    then Left "unsafe-contextual-contraction-non-singleton-fiber"
    else Right ()
  if not reverseBridge
    then Left "no-reverse-bridge-to-source"
    else
      Right
        ContextualContraction
          { contractionStages = stages
          , contractionSource = contextSource context
          , contractionTarget = target
          , contractionSafety =
              if uniqueEntity
                then "unique-contextual-fiber"
                else "generic-reading"
          }

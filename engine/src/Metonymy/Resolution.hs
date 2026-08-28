module Metonymy.Resolution
  ( expandFiber
  , contractTarget
  , verifyCertificate
  , roundTripHolds
  ) where

import qualified Data.Set as Set
import Metonymy.Ontology
import Metonymy.Types

expandFiber :: KnowledgeBase -> FiberQuery -> [FineMeaning]
expandFiber kb query =
  [ FineMeaning
      { fineTarget = target
      , finePath = path
      , fineRequirementProofs = proofs
      }
  | path <- outgoingPaths kb query
  , let target = pathTarget path
  , Just proofs <- [proveRequirement kb target (fiberRequirement query)]
  ]

contractTarget ::
  KnowledgeBase ->
  Requirement ->
  [Relation] ->
  Int ->
  EntityId ->
  [(CoarseMeaning, FineMeaning)]
contractTarget kb requirement allowed maxDepth target =
  [ ( CoarseMeaning
        { coarseSource = source
        , coarseFiber =
            FiberQuery
              { fiberSource = source
              , fiberRequirement = requirement
              , fiberRelations = allowed
              , fiberMaxDepth = maxDepth
              }
        , coarseLabel = maybe (show source) entityLabel (lookupEntity kb source)
        }
    , FineMeaning
        { fineTarget = target
        , finePath = reversePath
        , fineRequirementProofs = proofs
        }
    )
  | Just proofs <- [proveRequirement kb target requirement]
  , reversePath <- incomingPaths kb allowed maxDepth target
  , let source = pathSource reversePath
  ]

verifyCertificate :: KnowledgeBase -> Certificate -> Bool
verifyCertificate kb certificate =
  sourceMatches
    && targetMatches
    && pathAllowed
    && all stepExists steps
    && requirementStillProvable
  where
    coarse = certificateCoarse certificate
    fine = certificateFine certificate
    query = coarseFiber coarse
    BridgePath steps = finePath fine

    sourceMatches =
      case steps of
        [] -> fineTarget fine == coarseSource coarse
        firstStep : _ -> bridgeSource firstStep == coarseSource coarse

    targetMatches =
      case reverse steps of
        [] -> fineTarget fine == coarseSource coarse
        lastStep : _ -> bridgeTarget lastStep == fineTarget fine

    pathAllowed =
      length steps <= fiberMaxDepth query
        && all ((`elem` fiberRelations query) . bridgeRelation) steps

    stepExists step =
      any
        ( \assertion ->
            assertedRelation assertion == bridgeRelation step
              && relationSource assertion == bridgeSource step
              && relationTarget assertion == bridgeTarget step
        )
        (relationAssertions kb)

    requirementStillProvable =
      case proveRequirement kb (fineTarget fine) (fiberRequirement query) of
        Just _ -> True
        Nothing -> False

roundTripHolds :: KnowledgeBase -> Certificate -> Bool
roundTripHolds kb certificate =
  verifyCertificate kb certificate
    && fineTarget (certificateFine certificate)
      `elem` map fineTarget (expandFiber kb (coarseFiber (certificateCoarse certificate)))

outgoingPaths :: KnowledgeBase -> FiberQuery -> [BridgePath]
outgoingPaths kb query =
  go
    Set.empty
    (fiberMaxDepth query)
    (fiberSource query)
    []
  where
    go _ 0 _ _ = []
    go visited depth current prefix
      | current `Set.member` visited = []
      | otherwise =
          concatMap extend nextSteps
      where
        visited' = Set.insert current visited
        nextSteps =
          relationStepsFrom kb (fiberRelations query) current
        extend step =
          let newPrefix = prefix <> [step]
           in BridgePath newPrefix
                : go
                  visited'
                  (depth - 1)
                  (bridgeTarget step)
                  newPrefix

incomingPaths ::
  KnowledgeBase ->
  [Relation] ->
  Int ->
  EntityId ->
  [BridgePath]
incomingPaths kb allowed maxDepth target =
  map BridgePath (go Set.empty maxDepth target [])
  where
    go _ 0 _ _ = []
    go visited depth current suffix
      | current `Set.member` visited = []
      | otherwise =
          concatMap extend previousSteps
      where
        visited' = Set.insert current visited
        previousSteps = relationStepsTo kb allowed current
        extend step =
          let newSuffix = step : suffix
           in newSuffix
                : go
                  visited'
                  (depth - 1)
                  (bridgeSource step)
                  newSuffix

pathTarget :: BridgePath -> EntityId
pathTarget (BridgePath []) = error "empty bridge path has no target"
pathTarget (BridgePath steps) = bridgeTarget (last steps)

pathSource :: BridgePath -> EntityId
pathSource (BridgePath []) = error "empty bridge path has no source"
pathSource (BridgePath (step : _)) = bridgeSource step

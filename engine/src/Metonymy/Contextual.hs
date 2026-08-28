module Metonymy.Contextual
  ( LexicalAnchor (..)
  , ConstraintPayload (..)
  , ContextConstraint (..)
  , LexicalTree (..)
  , Context (..)
  , Snapshot (..)
  , ConstraintProof (..)
  , SnapshotObstruction (..)
  , ContextualCandidate (..)
  , FiberStage (..)
  , validateContext
  , contextualFiber
  , stageTargets
  ) where

import Data.List (nubBy)
import Metonymy.Ontology
import Metonymy.Resolution (expandFiber)
import Metonymy.Types

data LexicalAnchor = LexicalAnchor
  { anchorGFConstructor :: String
  , anchorLemma :: String
  , anchorSurface :: String
  , anchorStart :: Int
  , anchorEnd :: Int
  }
  deriving stock (Eq, Show)

data ConstraintPayload
  = Requires Requirement
  | RequiresRelation Relation EntityId
  deriving stock (Eq, Show)

data ContextConstraint = ContextConstraint
  { constraintOrigin :: LexicalAnchor
  , constraintPayload :: ConstraintPayload
  , constraintProvenance :: String
  }
  deriving stock (Eq, Show)

data LexicalTree
  = LexicalLeaf LexicalAnchor [ConstraintPayload]
  | LexicalApply String [LexicalTree]
  deriving stock (Eq, Show)

data Context = Context
  { contextTree :: LexicalTree
  , contextSnapshotHash :: String
  , contextSource :: EntityId
  , contextAction :: String
  , contextRole :: HoleRole
  , contextConstraints :: [ContextConstraint]
  , contextRuleProvenance :: [String]
  }
  deriving stock (Eq, Show)

data Snapshot = Snapshot
  { snapshotHash :: String
  , snapshotKnowledgeBase :: KnowledgeBase
  }
  deriving stock (Eq, Show)

data SnapshotObstruction
  = MissingRequirement ContextConstraint EntityId
  | MissingRelation ContextConstraint EntityId Relation EntityId
  deriving stock (Eq, Show)

data ConstraintProof
  = RequirementConstraintProof ContextConstraint [Proof]
  | RelationConstraintProof ContextConstraint Proof
  deriving stock (Eq, Show)

data ContextualCandidate = ContextualCandidate
  { contextualFineMeaning :: FineMeaning
  , contextualProofs :: [ConstraintProof]
  }
  deriving stock (Eq, Show)

data FiberStage = FiberStage
  { stageIndex :: Int
  , stageConstraint :: Maybe ContextConstraint
  , stageCandidates :: [ContextualCandidate]
  , stageObstructions :: [SnapshotObstruction]
  }
  deriving stock (Eq, Show)

validateContext :: Context -> Either String ()
validateContext context
  | null (contextSnapshotHash context) = Left "empty-snapshot-hash"
  | null (contextAction context) = Left "empty-action"
  | noLeaves (contextTree context) = Left "tree-without-lexical-leaves"
  | any (null . constraintProvenance) (contextConstraints context) =
      Left "empty-constraint-provenance"
  | any
      (`notElem` contextRuleProvenance context)
      (map constraintProvenance (contextConstraints context)) =
      Left "unknown-constraint-provenance"
  | otherwise =
      case invalidAnchor (allAnchors (contextTree context)) of
        Just _ -> Left "invalid-lexical-span"
        Nothing -> Right ()
  where
    noLeaves (LexicalLeaf _ _) = False
    noLeaves (LexicalApply _ children) = null children || all noLeaves children

    invalidAnchor = firstMatching (\anchor -> anchorStart anchor < 0 || anchorEnd anchor <= anchorStart anchor)

contextualFiber :: Snapshot -> [Relation] -> Int -> Context -> Either String [FiberStage]
contextualFiber snapshot relations maxDepth context = do
  validateContext context
  if contextSnapshotHash context /= snapshotHash snapshot
    then Left "snapshot-hash-mismatch"
    else Right ()
  if maxDepth <= 0
    then Left "invalid-max-depth"
    else Right ()
  let kb = snapshotKnowledgeBase snapshot
      initial =
        uniqueCandidates
          [ ContextualCandidate fine []
          | fine <-
              expandFiber
                kb
                FiberQuery
                  { fiberSource = contextSource context
                  , fiberRequirement = HasSort Entity
                  , fiberRelations = relations
                  , fiberMaxDepth = maxDepth
                  }
          ]
      initialStage = FiberStage 0 Nothing initial []
  pure (initialStage : applyConstraints kb initial 1 (contextConstraints context))
  where
    applyConstraints _ _ _ [] = []
    applyConstraints kb candidates index (constraint : rest) =
      let (survivors, obstructions) = applyConstraint kb constraint candidates
          stage = FiberStage index (Just constraint) survivors obstructions
       in stage : applyConstraints kb survivors (index + 1) rest

applyConstraint ::
  KnowledgeBase ->
  ContextConstraint ->
  [ContextualCandidate] ->
  ([ContextualCandidate], [SnapshotObstruction])
applyConstraint kb constraint =
  foldr step ([], [])
  where
    step candidate (survivors, obstructions) =
      case constraintPayload constraint of
        Requires requirement ->
          case proveRequirement kb target requirement of
            Just proofs ->
              ( candidate
                  { contextualProofs =
                      contextualProofs candidate
                        <> [RequirementConstraintProof constraint proofs]
                  }
                  : survivors
              , obstructions
              )
            Nothing ->
              (survivors, MissingRequirement constraint target : obstructions)
        RequiresRelation relation expectedTarget ->
          case relationProof relation target expectedTarget of
            Just proof ->
              (candidate {contextualProofs = contextualProofs candidate <> [RelationConstraintProof constraint proof]} : survivors, obstructions)
            Nothing ->
              (survivors, MissingRelation constraint target relation expectedTarget : obstructions)
      where
        target = fineTarget (contextualFineMeaning candidate)

    relationProof relation source target =
      case
          [ assertion
          | assertion <- relationAssertions kb
          , assertedRelation assertion == relation
          , relationSource assertion == source
          , relationTarget assertion == target
          ] of
        assertion : _ ->
          Just (RelationProof relation source target (relationProvenance assertion))
        [] -> Nothing

stageTargets :: FiberStage -> [EntityId]
stageTargets = map (fineTarget . contextualFineMeaning) . stageCandidates

uniqueCandidates :: [ContextualCandidate] -> [ContextualCandidate]
uniqueCandidates =
  nubBy
    (\left right -> fineTarget (contextualFineMeaning left) == fineTarget (contextualFineMeaning right))

allAnchors :: LexicalTree -> [LexicalAnchor]
allAnchors (LexicalLeaf anchor _) = [anchor]
allAnchors (LexicalApply _ children) = concatMap allAnchors children

firstMatching :: (value -> Bool) -> [value] -> Maybe value
firstMatching _ [] = Nothing
firstMatching predicate (value : values)
  | predicate value = Just value
  | otherwise = firstMatching predicate values

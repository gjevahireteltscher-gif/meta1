module Metonymy.Automatic
  ( Clause (..)
  , parseClause
  , automaticExpand
  , automaticContract
  ) where

import Data.List (find)
import Metonymy.Examples
import Metonymy.Ontology
import Metonymy.Resolution
import Metonymy.Types

data Clause = Clause
  { clauseSubjectGF :: String
  , clauseVerbGF :: String
  , clauseObjectGF :: String
  }
  deriving stock (Eq, Show)

parseClause :: String -> Maybe Clause
parseClause tree =
  case tokenize tree of
    ["Pred", subject, "(", "Compl", verb, object, ")"] ->
      Just
        Clause
          { clauseSubjectGF = subject
          , clauseVerbGF = verb
          , clauseObjectGF = object
          }
    _ -> Nothing
  where
    tokenize = words . concatMap spaceParenthesis
    spaceParenthesis '(' = " ( "
    spaceParenthesis ')' = " ) "
    spaceParenthesis character = [character]

automaticExpand ::
  KnowledgeBase ->
  [Predicate] ->
  String ->
  [Candidate]
automaticExpand kb predicates tree = do
  clause <- maybeToList (parseClause tree)
  predicate <- filter ((== clauseVerbGF clause) . gfFunction) predicates
  hole <- [ObjectHole, SubjectHole]
  let sourceGF = gfAt hole clause
      otherGF = gfAt (otherHole hole) clause
      requirement = requirementAt hole predicate
  sourceInfo <- filter ((== sourceGF) . entityGF) (entities kb)
  let source = entityId sourceInfo
  case proveRequirement kb source requirement of
    Just _ -> []
    Nothing -> do
      let query =
            FiberQuery
              { fiberSource = source
              , fiberRequirement = requirement
              , fiberRelations = [minBound .. maxBound]
              , fiberMaxDepth = 2
              }
          meanings = expandFiber kb query
      if null meanings
        then []
        else do
          let generic =
                maybe
                  source
                  fineTarget
                  (find (isGeneric kb . fineTarget) meanings)
              scenario =
                Scenario
                  { scenarioName =
                      "automatic-"
                        <> predicateName predicate
                        <> "-"
                        <> unEntityId source
                  , scenarioPredicate = predicate
                  , scenarioHoleRole = hole
                  , scenarioSource = source
                  , scenarioGenericTarget = generic
                  , scenarioAllowedRelations = [minBound .. maxBound]
                  , scenarioOtherArgumentGF = otherGF
                  }
          map (applyStrength predicate) (expandScenario kb scenario)

automaticContract ::
  KnowledgeBase ->
  [Predicate] ->
  String ->
  [Candidate]
automaticContract kb predicates tree = do
  clause <- maybeToList (parseClause tree)
  predicate <- filter ((== clauseVerbGF clause) . gfFunction) predicates
  hole <- [ObjectHole, SubjectHole]
  let targetGF = gfAt hole clause
      otherGF = gfAt (otherHole hole) clause
      requirement = requirementAt hole predicate
  targetInfo <- filter ((== targetGF) . entityGF) (entities kb)
  let target = entityId targetInfo
  _ <- maybeToList (proveRequirement kb target requirement)
  if not (isGeneric kb target)
    then []
    else do
      (coarse, _) <-
        contractTarget
          kb
          requirement
          [minBound .. maxBound]
          2
          target
      let source = coarseSource coarse
      case proveRequirement kb source requirement of
        Just _ -> []
        Nothing -> do
          let scenario =
                Scenario
                  { scenarioName =
                      "automatic-"
                        <> predicateName predicate
                        <> "-"
                        <> unEntityId source
                  , scenarioPredicate = predicate
                  , scenarioHoleRole = hole
                  , scenarioSource = source
                  , scenarioGenericTarget = target
                  , scenarioAllowedRelations = [minBound .. maxBound]
                  , scenarioOtherArgumentGF = otherGF
                  }
          map
            (applyStrength predicate)
            (maybeToList (contractScenario kb scenario target))

requirementAt :: HoleRole -> Predicate -> Requirement
requirementAt SubjectHole = subjectRequirement
requirementAt ObjectHole = objectRequirement

gfAt :: HoleRole -> Clause -> String
gfAt SubjectHole = clauseSubjectGF
gfAt ObjectHole = clauseObjectGF

otherHole :: HoleRole -> HoleRole
otherHole SubjectHole = ObjectHole
otherHole ObjectHole = SubjectHole

isGeneric :: KnowledgeBase -> EntityId -> Bool
isGeneric kb identifier =
  case proveRequirement kb identifier (HasSort GenericReading) of
    Just _ -> True
    Nothing -> False

maybeToList :: Maybe value -> [value]
maybeToList (Just value) = [value]
maybeToList Nothing = []

applyStrength :: Predicate -> Candidate -> Candidate
applyStrength predicate candidate =
  case predicateStrength predicate of
    HardRequirement -> candidate
    SelectionalPreference ->
      candidate
        { candidateScore = candidateScore candidate * 0.85
        }

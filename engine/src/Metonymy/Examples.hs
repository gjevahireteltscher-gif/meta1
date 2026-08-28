module Metonymy.Examples
  ( Scenario (..)
  , Recognition (..)
  , exampleKnowledgeBase
  , scenarios
  , scenariosFor
  , findScenario
  , findScenarioIn
  , recognizeTree
  , expandScenario
  , contractScenario
  , inputTree
  ) where

import Control.Applicative ((<|>))
import Data.List (find, isPrefixOf, nubBy)
import Metonymy.Ontology
import Metonymy.Resolution
import Metonymy.Types

data Scenario = Scenario
  { scenarioName :: String
  , scenarioPredicate :: Predicate
  , scenarioHoleRole :: HoleRole
  , scenarioSource :: EntityId
  , scenarioGenericTarget :: EntityId
  , scenarioAllowedRelations :: [Relation]
  , scenarioOtherArgumentGF :: String
  }
  deriving stock (Eq, Show)

data Recognition = Recognition
  { recognizedScenario :: Scenario
  , recognizedTarget :: EntityId
  }
  deriving stock (Eq, Show)

eid :: String -> EntityId
eid = EntityId

readPredicate, drinkPredicate, signPredicate :: Predicate
readPredicate =
  Predicate
    { predicateName = "read"
    , subjectRequirement = HasSort Human
    , objectRequirement = HasSort Readable
    , gfFunction = "Read"
    , predicateStrength = HardRequirement
    , predicateProvenance = "local:selectional-lexicon"
    }

drinkPredicate =
  Predicate
    { predicateName = "drink"
    , subjectRequirement = HasSort Human
    , objectRequirement = HasSort Drinkable
    , gfFunction = "Drink"
    , predicateStrength = HardRequirement
    , predicateProvenance = "local:selectional-lexicon"
    }

signPredicate =
  Predicate
    { predicateName = "sign an agreement"
    , subjectRequirement = HasSort Agent
    , objectRequirement = HasSort Agreement
    , gfFunction = "Sign"
    , predicateStrength = HardRequirement
    , predicateProvenance = "local:selectional-lexicon"
    }

scenarios :: [Scenario]
scenarios =
  [ Scenario
      { scenarioName = "read-tolstoy"
      , scenarioPredicate = readPredicate
      , scenarioHoleRole = ObjectHole
      , scenarioSource = eid "tolstoy"
      , scenarioGenericTarget = eid "works-of-tolstoy"
      , scenarioAllowedRelations = [Authored]
      , scenarioOtherArgumentGF = "Anna"
      }
  , Scenario
      { scenarioName = "drink-glass"
      , scenarioPredicate = drinkPredicate
      , scenarioHoleRole = ObjectHole
      , scenarioSource = eid "glass"
      , scenarioGenericTarget = eid "contents-of-glass"
      , scenarioAllowedRelations = [Contains]
      , scenarioOtherArgumentGF = "Anna"
      }
  , Scenario
      { scenarioName = "moscow-signs"
      , scenarioPredicate = signPredicate
      , scenarioHoleRole = SubjectHole
      , scenarioSource = eid "moscow"
      , scenarioGenericTarget = eid "russian-government"
      , scenarioAllowedRelations = [GovernedBy]
      , scenarioOtherArgumentGF = "Agreement"
      }
  ]

findScenario :: String -> Maybe Scenario
findScenario name = find ((== name) . scenarioName) scenarios

findScenarioIn :: KnowledgeBase -> String -> Maybe Scenario
findScenarioIn kb name =
  find ((== name) . scenarioName) (scenariosFor kb)

scenariosFor :: KnowledgeBase -> [Scenario]
scenariosFor kb =
  nubBy
    (\left right -> scenarioName left == scenarioName right)
    (scenarios <> importedAuthorScenarios)
  where
    writers =
      [ typedEntity assertion
      | assertion <- typeAssertions kb
      , assertedSort assertion == Writer
      ]

    importedAuthorScenarios =
      [ Scenario
          { scenarioName = "read-" <> unEntityId author
          , scenarioPredicate = readPredicate
          , scenarioHoleRole = ObjectHole
          , scenarioSource = author
          , scenarioGenericTarget = genericWorks
          , scenarioAllowedRelations = [Authored]
          , scenarioOtherArgumentGF = "Anna"
          }
      | author <- writers
      , genericWorks <-
          [ relationTarget assertion
          | assertion <- relationAssertions kb
          , assertedRelation assertion == Authored
          , relationSource assertion == author
          , "works-of-" `isPrefixOf` unEntityId (relationTarget assertion)
          ]
      ]

recognizeTree :: KnowledgeBase -> String -> Maybe Recognition
recognizeTree kb tree =
  recognizeCompositional <|> findRecognition catalog
  where
    catalog = scenariosFor kb

    recognizeCompositional = do
      (subjectGF, verbGF, objectGF) <- parsePredication tree
      findRecognitionForParts catalog subjectGF verbGF objectGF

    findRecognition [] = Nothing
    findRecognition (scenario : rest)
      | inputTree kb scenario == tree =
          Just
            Recognition
              { recognizedScenario = scenario
              , recognizedTarget = scenarioSource scenario
              }
      | otherwise =
          case
            find
              ((== tree) . candidateAbstractTree)
              (expandScenario kb scenario)
          of
            Just candidate ->
              Just
                Recognition
                  { recognizedScenario = scenario
                  , recognizedTarget =
                      fineTarget
                        ( certificateFine
                            (candidateCertificate candidate)
                        )
                  }
            Nothing -> findRecognition rest

    findRecognitionForParts [] _ _ _ = Nothing
    findRecognitionForParts (scenario : rest) subjectGF verbGF objectGF
      | gfFunction (scenarioPredicate scenario) /= verbGF =
          findRecognitionForParts rest subjectGF verbGF objectGF
      | otherwise =
          case scenarioHoleRole scenario of
            ObjectHole ->
              case lookupTarget objectGF scenario of
                Just target ->
                  Just
                    Recognition
                      { recognizedScenario =
                          scenario {scenarioOtherArgumentGF = subjectGF}
                      , recognizedTarget = target
                      }
                Nothing ->
                  findRecognitionForParts rest subjectGF verbGF objectGF
            SubjectHole
              | scenarioOtherArgumentGF scenario /= objectGF ->
                  findRecognitionForParts rest subjectGF verbGF objectGF
              | otherwise ->
                  case lookupTarget subjectGF scenario of
                    Just target ->
                      Just
                        Recognition
                          { recognizedScenario = scenario
                          , recognizedTarget = target
                          }
                    Nothing ->
                      findRecognitionForParts rest subjectGF verbGF objectGF

    lookupTarget gf scenario = do
      info <- find ((== gf) . entityGF) (entities kb)
      let target = entityId info
          admissibleTargets =
            scenarioSource scenario
              : map
                (fineTarget . certificateFine . candidateCertificate)
                (expandScenario kb scenario)
      if target `elem` admissibleTargets then Just target else Nothing

parsePredication :: String -> Maybe (String, String, String)
parsePredication tree =
  case tokenize tree of
    ["Pred", subject, "(", "Compl", verb, object, ")"] ->
      Just (subject, verb, object)
    _ -> Nothing
  where
    tokenize = words . concatMap spaceParenthesis
    spaceParenthesis '(' = " ( "
    spaceParenthesis ')' = " ) "
    spaceParenthesis character = [character]

exampleKnowledgeBase :: KnowledgeBase
exampleKnowledgeBase =
  KnowledgeBase
    { entities =
        [ entity "anna" "Anna" "Anna"
        , entity "alice" "Alice" "Alice"
        , entity "bob" "Bob" "Bob"
        , entity "john" "John" "John"
        , entity "mary" "Mary" "Mary"
        , entity "tolstoy" "Tolstoy" "Tolstoy"
        , entity "works-of-tolstoy" "Tolstoy's works" "WorksOfTolstoy"
        , entity "war-and-peace" "War and Peace" "WarAndPeace"
        , entity "anna-karenina" "Anna Karenina" "AnnaKarenina"
        , entity "glass" "a glass" "Glass"
        , entity "contents-of-glass" "the contents of a glass" "ContentsOfGlass"
        , entity "moscow" "Moscow" "Moscow"
        , entity "russian-government" "the Russian government" "RussianGovernment"
        , entity "agreement" "the agreement" "Agreement"
        ]
    , typeAssertions =
        [ typed "anna" Human
        , typed "alice" Human
        , typed "bob" Human
        , typed "john" Human
        , typed "mary" Human
        , typed "tolstoy" Writer
        , typed "works-of-tolstoy" LiteraryWork
        , typed "works-of-tolstoy" GenericReading
        , typed "war-and-peace" LiteraryWork
        , typed "anna-karenina" LiteraryWork
        , typed "glass" Container
        , typed "contents-of-glass" Drinkable
        , typed "contents-of-glass" GenericReading
        , typed "moscow" Place
        , typed "russian-government" Institution
        , typed "russian-government" GenericReading
        , typed "agreement" Agreement
        ]
    , relationAssertions =
        [ related Authored "tolstoy" "works-of-tolstoy"
        , related Authored "tolstoy" "war-and-peace"
        , related Authored "tolstoy" "anna-karenina"
        , related Contains "glass" "contents-of-glass"
        , related GovernedBy "moscow" "russian-government"
        ]
    , subsortRules =
        [ (Writer, Human, "writer-is-human")
        , (LiteraryWork, Readable, "literary-work-is-readable")
        , (Institution, Agent, "institution-is-agent")
        ]
    }
  where
    entity identifier label gf =
      EntityInfo (eid identifier) label gf
    typed identifier sort =
      TypeAssertion
        (eid identifier)
        sort
        (LocalFact (identifier <> ":is-a:" <> show sort))
    related relation source target =
      RelationAssertion
        relation
        (eid source)
        (eid target)
        (LocalFact (source <> ":" <> show relation <> ":" <> target))

expandScenario :: KnowledgeBase -> Scenario -> [Candidate]
expandScenario kb scenario =
  map toCandidate fineMeanings
  where
    query =
      FiberQuery
        { fiberSource = scenarioSource scenario
        , fiberRequirement = holeRequirement scenario
        , fiberRelations = scenarioAllowedRelations scenario
        , fiberMaxDepth = 1
        }
    coarse =
      CoarseMeaning
        { coarseSource = scenarioSource scenario
        , coarseFiber = query
        , coarseLabel = entityLabelOrId kb (scenarioSource scenario)
        }
    fineMeanings = expandFiber kb query
    toCandidate fine =
      Candidate
        { candidateSurface = ""
        , candidateSourceTree = inputTree kb scenario
        , candidateAbstractTree = treeForTarget kb scenario (fineTarget fine)
        , candidateCertificate =
            Certificate
              { certificateDirection = Expand
              , certificatePredicate = scenarioPredicate scenario
              , certificateHoleRole = scenarioHoleRole scenario
              , certificateCoarse = coarse
              , certificateFine = fine
              , certificateSafeToForget =
                  fineTarget fine == scenarioGenericTarget scenario
              , certificateForgetContext = defaultForgetContext
              }
        , candidateScore =
            if fineTarget fine == scenarioGenericTarget scenario
              then 1.0
              else 0.7
        }

contractScenario ::
  KnowledgeBase ->
  Scenario ->
  EntityId ->
  Maybe Candidate
contractScenario kb scenario target = do
  (coarse, fine) <-
    find
      ((== scenarioSource scenario) . coarseSource . fst)
      ( contractTarget
          kb
          (holeRequirement scenario)
          (scenarioAllowedRelations scenario)
          1
          target
      )
  let safe = target == scenarioGenericTarget scenario
  if safe
    then
      pure
        Candidate
          { candidateSurface = ""
          , candidateSourceTree = treeForTarget kb scenario target
          , candidateAbstractTree = inputTree kb scenario
          , candidateCertificate =
              Certificate
                { certificateDirection = Contract
                , certificatePredicate = scenarioPredicate scenario
                , certificateHoleRole = scenarioHoleRole scenario
                , certificateCoarse = coarse
                , certificateFine = fine
                , certificateSafeToForget = True
                , certificateForgetContext = defaultForgetContext
                }
          , candidateScore = 1.0
          }
    else Nothing

inputTree :: KnowledgeBase -> Scenario -> String
inputTree kb scenario =
  treeForTarget kb scenario (scenarioSource scenario)

holeRequirement :: Scenario -> Requirement
holeRequirement scenario =
  case scenarioHoleRole scenario of
    SubjectHole -> subjectRequirement (scenarioPredicate scenario)
    ObjectHole -> objectRequirement (scenarioPredicate scenario)

treeForTarget :: KnowledgeBase -> Scenario -> EntityId -> String
treeForTarget kb scenario target =
  case scenarioHoleRole scenario of
    SubjectHole ->
      "Pred "
        <> targetGF
        <> " (Compl "
        <> gfFunction predicate
        <> " "
        <> scenarioOtherArgumentGF scenario
        <> ")"
    ObjectHole ->
      "Pred "
        <> scenarioOtherArgumentGF scenario
        <> " (Compl "
        <> gfFunction predicate
        <> " "
        <> targetGF
        <> ")"
  where
    predicate = scenarioPredicate scenario
    targetGF =
      maybe (error ("unknown entity " <> show target)) entityGF (lookupEntity kb target)

entityLabelOrId :: KnowledgeBase -> EntityId -> String
entityLabelOrId kb identifier =
  maybe (show identifier) entityLabel (lookupEntity kb identifier)

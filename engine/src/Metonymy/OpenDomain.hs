module Metonymy.OpenDomain
  ( DatasetHint (..)
  , OpenFamily (..)
  , OpenDecision (..)
  , EndpointProposal (..)
  , ActionRoleIndex
  , buildActionRoleIndex
  , loadEndpointSnapshot
  , analyzeOpen
  , analyzeOpenAt
  , analyzeOpenAtWithEndpoints
  , openFamilyName
  ) where

import Data.Char (isAlphaNum, toLower)
import Data.List (find, isInfixOf, sortOn)
import qualified Data.Map.Strict as Map
import Metonymy.Ontology
import Metonymy.Resolution (expandFiber)
import Metonymy.Types

data DatasetHint
  = WiMCorLocation
  | ConMeCCategory String
  | UnspecifiedDomain
  deriving stock (Eq, Show)

data OpenFamily
  = LocationInstitution
  | LocationTeam
  | LocationEvent
  | LocationArtifact
  | ContainerContent
  | ProducerProduct
  | ProductProducer
  | LocationPeople
  | CauserResult
  | PossessedPossessor
  deriving stock (Eq, Ord, Show, Enum, Bounded)

data OpenDecision
  = OpenLiteral
  | OpenAbstain String
  | OpenRewrite
      { openFamily :: OpenFamily
      , openKnowledgeBase :: KnowledgeBase
      , openPredicates :: [Predicate]
      , openCandidate :: Candidate
      }
  deriving stock (Eq, Show)

data FamilySpec = FamilySpec
  { specSourceSort :: Sort
  , specRelation :: Relation
  , specTargetSort :: Sort
  }

data EndpointProposal = EndpointProposal
  { endpointRecordId :: String
  , endpointFamily :: OpenFamily
  , endpointSourceAlias :: String
  , endpointId :: EntityId
  , endpointLabel :: String
  , endpointProvenance :: String
  }
  deriving stock (Eq, Show)

type ActionRoleIndex = Map.Map String [ActionRoleRequirement]

buildActionRoleIndex ::
  [Predicate] ->
  [ActionRoleRequirement] ->
  ActionRoleIndex
buildActionRoleIndex predicates imported =
  Map.fromListWith (<>)
    [ (form, [role])
    | role <- imported <> concatMap predicateRoles predicates
    , form <- actionForms (actionLemma role)
    ]
  where
    predicateRoles predicate =
      [ role SubjectHole (subjectRequirement predicate)
      , role ObjectHole (objectRequirement predicate)
      ]
      where
        role hole requirement =
          ActionRoleRequirement
            { actionId = "predicate:" <> gfFunction predicate
            , actionLemma = predicateName predicate
            , actionFrame = gfFunction predicate
            , actionThematicRole = show hole
            , actionHoleRole = hole
            , actionRequirement = requirement
            , actionStrength = predicateStrength predicate
            , actionProvenance = predicateProvenance predicate
            }

openFamilyName :: OpenFamily -> String
openFamilyName LocationInstitution = "location-for-institution"
openFamilyName LocationTeam = "location-for-team"
openFamilyName LocationEvent = "location-for-event"
openFamilyName LocationArtifact = "location-for-artifact"
openFamilyName ContainerContent = "container-for-content"
openFamilyName ProducerProduct = "producer-for-product"
openFamilyName ProductProducer = "product-for-producer"
openFamilyName LocationPeople = "location-for-people"
openFamilyName CauserResult = "causer-for-result"
openFamilyName PossessedPossessor = "possessed-for-possessor"

analyzeOpen ::
  ActionRoleIndex ->
  KnowledgeBase ->
  DatasetHint ->
  String ->
  String ->
  OpenDecision
analyzeOpen actionRoles base hint target sentence
  = analyzeOpenAt actionRoles base hint target Nothing sentence

analyzeOpenAt ::
  ActionRoleIndex ->
  KnowledgeBase ->
  DatasetHint ->
  String ->
  Maybe (Int, Int) ->
  String ->
  OpenDecision
analyzeOpenAt actionRoles base hint target suppliedSpan sentence
  = analyzeOpenAtWithEndpoints
      builtinEndpoints actionRoles base hint target suppliedSpan sentence

analyzeOpenAtWithEndpoints ::
  [EndpointProposal] ->
  ActionRoleIndex ->
  KnowledgeBase ->
  DatasetHint ->
  String ->
  Maybe (Int, Int) ->
  String ->
  OpenDecision
analyzeOpenAtWithEndpoints
  endpointSnapshot actionRoles base hint target suppliedSpan sentence
  | null normalizedTarget =
      OpenAbstain "empty-target"
  | normalizedTarget `notElemPhrase` normalizedSentence =
      OpenAbstain "target-not-found"
  | not (validSpan suppliedSpan target sentence) =
      OpenAbstain "invalid-target-span"
  | otherwise =
      case
          [ decision
          | role <- chooseActionRoles actionRoles target sentence
          , Just decision <-
              [ buildTypedRewrite
                  endpointSnapshot base hint triggerWindow target role
              ]
          ]
        of
        decision : _ -> decision
        [] ->
          case chooseFamily hint triggerWindow of
            Nothing -> OpenLiteral
            Just family ->
              buildRewrite
                base
                family
                target
                (lookupEndpoint endpointSnapshot family target)
  where
    normalizedTarget = normalize target
    normalizedSentence = " " <> normalize sentence <> " "
    triggerWindow =
      " "
        <> normalize
          (case suppliedSpan of
             Nothing -> sentence
             Just (start, _) ->
               take 96 (drop (max 0 (start - 72)) sentence)
          )
        <> " "

validSpan :: Maybe (Int, Int) -> String -> String -> Bool
validSpan Nothing _ _ = True
validSpan (Just (start, end)) target sentence =
  start >= 0
    && end > start
    && end <= length sentence
    && normalize (take (end - start) (drop start sentence))
      == normalize target

chooseActionRoles ::
  ActionRoleIndex ->
  String ->
  String ->
  [ActionRoleRequirement]
chooseActionRoles index target sentence =
  case sortOn roleRank matching of
    [] -> []
    ranked@((_, nearest) : _) ->
      [ role
      | (role, distance) <- ranked
      , distance == nearest
      ]
  where
    normalizedSentence = normalize sentence
    normalizedTarget = normalize target
    targetPosition = substringPosition normalizedTarget normalizedSentence
    tokens = words normalizedSentence
    phrases =
      tokens
        <> zipWith (\left right -> left <> " " <> right) tokens (drop 1 tokens)
        <> zipWith3
          (\first second third -> first <> " " <> second <> " " <> third)
          tokens
          (drop 1 tokens)
          (drop 2 tokens)
    candidates =
      [ (phrase, role)
      | phrase <- phrases
      , role <- Map.findWithDefault [] phrase index
      ]
    matching =
      [ (role, abs (actionPosition - targetOffset))
      | (phrase, role) <- candidates
      , Just actionPosition <- [substringPosition phrase normalizedSentence]
      , Just targetOffset <- [targetPosition]
      , actionHoleRole role
          == if targetOffset < actionPosition then SubjectHole else ObjectHole
      ]
    roleRank (role, distance) =
      ( distance
      , case actionStrength role of
          HardRequirement -> 0 :: Int
          SelectionalPreference -> 1
      , negate (length (actionLemma role))
      , actionId role
      )

actionForms :: String -> [String]
actionForms rawLemma =
  unique
    [ lemma
    , lemma <> "s"
    , lemma <> "ed"
    , lemma <> "ing"
    , if endsWith "e" lemma then init lemma <> "ed" else lemma <> "ed"
    , if endsWith "e" lemma then init lemma <> "ing" else lemma <> "ing"
    , if endsWith "y" lemma then init lemma <> "ies" else lemma <> "s"
    ]
  where
    lemma = normalize rawLemma
    unique [] = []
    unique (value : values) =
      value : unique (filter (/= value) values)

endsWith :: String -> String -> Bool
endsWith suffix value =
  length value >= length suffix
    && drop (length value - length suffix) value == suffix

substringPosition :: String -> String -> Maybe Int
substringPosition needle haystack
  | null needle = Nothing
  | otherwise = search 0 haystack
  where
    search _ [] = Nothing
    search offset remaining
      | needle `isPrefixOfText` remaining = Just offset
      | otherwise = search (offset + 1) (drop 1 remaining)
    isPrefixOfText prefix value =
      take (length prefix) value == prefix

chooseFamily :: DatasetHint -> String -> Maybe OpenFamily
chooseFamily WiMCorLocation sentence
  | hasAny sportsTriggers sentence = Just LocationTeam
  | hasAny eventTriggers sentence = Just LocationEvent
  | hasAny artifactTriggers sentence = Just LocationArtifact
  | hasAny agentTriggers sentence = Just LocationInstitution
  | otherwise = Nothing
chooseFamily (ConMeCCategory category) sentence =
  case map toLower category of
    "container"
      | hasAny consumptionTriggers sentence -> Just ContainerContent
    "producer"
      | hasAny productUseTriggers sentence -> Just ProducerProduct
    "product"
      | hasAny agentTriggers sentence -> Just ProductProducer
    "location"
      | hasAny agentTriggers sentence -> Just LocationPeople
    "causer"
      | hasAny agentTriggers sentence -> Just CauserResult
    "possessed"
      | hasAny agentTriggers sentence -> Just PossessedPossessor
    _ -> Nothing
chooseFamily UnspecifiedDomain sentence
  | hasAny consumptionTriggers sentence = Just ContainerContent
  | hasAny sportsTriggers sentence = Just LocationTeam
  | hasAny agentTriggers sentence = Just LocationInstitution
  | otherwise = Nothing

buildTypedRewrite ::
  [EndpointProposal] ->
  KnowledgeBase ->
  DatasetHint ->
  String ->
  String ->
  ActionRoleRequirement ->
  Maybe OpenDecision
buildTypedRewrite endpointSnapshot base hint triggerWindow target role =
  case sortOn resultRank results of
    result : _ -> Just (toDecision result)
    [] -> Nothing
  where
    preferredFamily = chooseFamily hint triggerWindow
    results =
      [ result
      | family <- [minBound .. maxBound]
      , result <- maybeToList (searchFamily family)
      ]

    searchFamily family =
      case
          buildRewrite
            base
            family
            target
            (lookupEndpoint endpointSnapshot family target)
        of
        OpenRewrite _ candidateKB _ template -> do
          let templateCertificate = candidateCertificate template
              source =
                coarseSource (certificateCoarse templateCertificate)
              query =
                FiberQuery
                  { fiberSource = source
                  , fiberRequirement = actionRequirement role
                  , fiberRelations = [minBound .. maxBound]
                  , fiberMaxDepth = 2
                  }
          fine <- firstOrNothing (expandFiber candidateKB query)
          let function = predicateConstructor family
              predicate =
                Predicate
                  { predicateName = actionLemma role
                  , subjectRequirement =
                      requirementAt SubjectHole role
                  , objectRequirement =
                      requirementAt ObjectHole role
                  , gfFunction = function
                  , predicateStrength = actionStrength role
                  , predicateProvenance = actionProvenance role
                  }
              coarse =
                CoarseMeaning
                  { coarseSource = source
                  , coarseFiber = query
                  , coarseLabel = target
                  }
              (sourceTree, targetTree) =
                openTrees (actionHoleRole role) function
              certificate =
                Certificate
                  { certificateDirection = Expand
                  , certificatePredicate = predicate
                  , certificateHoleRole = actionHoleRole role
                  , certificateCoarse = coarse
                  , certificateFine = fine
                  , certificateSafeToForget = True
                  , certificateForgetContext = defaultForgetContext
                  }
              candidate =
                template
                  { candidateSourceTree = sourceTree
                  , candidateAbstractTree = targetTree
                  , candidateCertificate = certificate
                  , candidateScore =
                      candidateScore template
                        + if Just family == preferredFamily then 0.2 else 0
                  }
          pure (family, candidateKB, predicate, candidate)
        _ -> Nothing

    resultRank (family, _, _, candidate) =
      ( negate (candidateScore candidate)
      , case actionStrength role of
          HardRequirement -> 0 :: Int
          SelectionalPreference -> 1
      , fromEnum family
      )

    toDecision (family, candidateKB, predicate, candidate) =
      OpenRewrite
        { openFamily = family
        , openKnowledgeBase = candidateKB
        , openPredicates = [predicate]
        , openCandidate = candidate
        }

    requirementAt hole selected
      | hole == actionHoleRole selected = actionRequirement selected
      | otherwise = HasSort Entity

    openTrees SubjectHole function =
      ( "Pred OpenSourceNP (Compl " <> function <> " OpenContextNP)"
      , "Pred OpenTargetNP (Compl " <> function <> " OpenContextNP)"
      )
    openTrees ObjectHole function =
      ( "Pred OpenContextNP (Compl " <> function <> " OpenSourceNP)"
      , "Pred OpenContextNP (Compl " <> function <> " OpenTargetNP)"
      )

    firstOrNothing [] = Nothing
    firstOrNothing (value : _) = Just value

    maybeToList Nothing = []
    maybeToList (Just value) = [value]

buildRewrite ::
  KnowledgeBase ->
  OpenFamily ->
  String ->
  Maybe EndpointProposal ->
  OpenDecision
buildRewrite base family target proposal =
  OpenRewrite
    { openFamily = family
    , openKnowledgeBase = knowledgeBase
    , openPredicates = [predicate]
    , openCandidate = candidate
    }
  where
    spec = familySpec family
    familyName = openFamilyName family
    source = EntityId ("open:" <> familyName <> ":source")
    explicit =
      maybe
        (EntityId ("open:" <> familyName <> ":generic"))
        endpointId
        proposal
    context = EntityId ("open:" <> familyName <> ":context")
    sourceGF = "OpenSourceNP"
    explicitGF = "OpenTargetNP"
    contextGF = "OpenContextNP"
    predicateGF = predicateConstructor family
    provenance =
      maybe
        ("open-family:" <> familyName <> ":v1")
        endpointProvenance
        proposal
    sourceInfo = EntityInfo source target sourceGF
    explicitInfo =
      EntityInfo
        explicit
        (maybe (explicitLabel family target) endpointLabel proposal)
        explicitGF
    contextInfo = EntityInfo context "open context" contextGF
    sourceType =
      TypeAssertion source (specSourceSort spec) (LocalFact provenance)
    targetType =
      TypeAssertion explicit (specTargetSort spec) (LocalFact provenance)
    genericType =
      TypeAssertion explicit GenericReading (LocalFact provenance)
    relationAssertion =
      RelationAssertion
        (specRelation spec)
        source
        explicit
        (LocalFact provenance)
    knowledgeBase =
      base
        { entities = sourceInfo : explicitInfo : contextInfo : entities base
        , typeAssertions =
            sourceType
              : targetType
              : ( case proposal of
                    Nothing -> genericType : typeAssertions base
                    Just _ -> typeAssertions base
                )
        , relationAssertions =
            relationAssertion : relationAssertions base
        }
    predicate =
      Predicate
        { predicateName = "open " <> familyName
        , subjectRequirement = HasSort (specTargetSort spec)
        , objectRequirement = HasSort Entity
        , gfFunction = predicateGF
        , predicateStrength = HardRequirement
        , predicateProvenance = provenance
        }
    query =
      FiberQuery
        { fiberSource = source
        , fiberRequirement = HasSort (specTargetSort spec)
        , fiberRelations = [specRelation spec]
        , fiberMaxDepth = 1
        }
    coarse =
      CoarseMeaning
        { coarseSource = source
        , coarseFiber = query
        , coarseLabel = target
        }
    step =
      BridgeStep
        { bridgeRelation = specRelation spec
        , bridgeSource = source
        , bridgeTarget = explicit
        , bridgeEvidence =
            RelationProof
              (specRelation spec)
              source
              explicit
              (LocalFact provenance)
        }
    fine =
      FineMeaning
        { fineTarget = explicit
        , finePath = BridgePath [step]
        , fineRequirementProofs =
            [ TypeProof
                explicit
                (specTargetSort spec)
                (LocalFact provenance)
            ]
        }
    sourceTree =
      "Pred "
        <> sourceGF
        <> " (Compl "
        <> predicateGF
        <> " "
        <> contextGF
        <> ")"
    targetTree =
      "Pred "
        <> explicitGF
        <> " (Compl "
        <> predicateGF
        <> " "
        <> contextGF
        <> ")"
    certificate =
      Certificate
        { certificateDirection = Expand
        , certificatePredicate = predicate
        , certificateHoleRole = SubjectHole
        , certificateCoarse = coarse
        , certificateFine = fine
        , certificateSafeToForget = True
        , certificateForgetContext = defaultForgetContext
        }
    candidate =
      Candidate
        { candidateSurface =
            maybe (explicitLabel family target) endpointLabel proposal
        , candidateSourceTree = sourceTree
        , candidateAbstractTree = targetTree
        , candidateCertificate = certificate
        , candidateScore = 1.0
        }

-- This cache is deliberately independent of WiMCor annotations. Production
-- caches are expected to be frozen Wikidata exports with the same fields.
lookupEndpoint ::
  [EndpointProposal] ->
  OpenFamily ->
  String ->
  Maybe EndpointProposal
lookupEndpoint proposals family target =
  find
    ( \proposal ->
        endpointFamily proposal == family
          && normalize (endpointSourceAlias proposal) == normalize target
    )
    proposals

builtinEndpoints :: [EndpointProposal]
builtinEndpoints =
  [ EndpointProposal
      { endpointRecordId = "wikidata-v1:moscow-government"
      , endpointFamily = LocationInstitution
      , endpointSourceAlias = "Moscow"
      , endpointId = EntityId "Q2184"
      , endpointLabel = "Government of Russia"
      , endpointProvenance = "wikidata-link-cache:v1:Q649→Q2184"
      }
  ]

loadEndpointSnapshot :: FilePath -> IO [EndpointProposal]
loadEndpointSnapshot path = do
  contents <- readFile path
  case lines contents of
    [] -> fail ("empty endpoint snapshot: " <> path)
    header : rows
      | header
          /= "record_id\tfamily\tsource_alias\tendpoint_id\tendpoint_label\tprovenance" ->
          fail ("unexpected endpoint snapshot header: " <> path)
      | otherwise -> traverse parseRow (zip [2 :: Int ..] rows)
  where
    parseRow (lineNumber, row) =
      case splitTabs row of
        [recordId, familyName, sourceAlias, identifier, label, provenance] ->
          case parseFamily familyName of
            Nothing ->
              fail
                (path <> ":" <> show lineNumber <> ": unknown family")
            Just family ->
              pure
                EndpointProposal
                  { endpointRecordId = recordId
                  , endpointFamily = family
                  , endpointSourceAlias = sourceAlias
                  , endpointId = EntityId identifier
                  , endpointLabel = label
                  , endpointProvenance = provenance
                  }
        _ ->
          fail
            (path <> ":" <> show lineNumber <> ": expected six TSV fields")

parseFamily :: String -> Maybe OpenFamily
parseFamily name =
  find ((== name) . openFamilyName) [minBound .. maxBound]

splitTabs :: String -> [String]
splitTabs value =
  case break (== '\t') value of
    (field, []) -> [field]
    (field, _ : rest) -> field : splitTabs rest

familySpec :: OpenFamily -> FamilySpec
familySpec LocationInstitution =
  FamilySpec Place GovernedBy Institution
familySpec LocationTeam =
  FamilySpec Place HomeOf HumanGroup
familySpec LocationEvent =
  FamilySpec Place Hosts Event
familySpec LocationArtifact =
  FamilySpec Place Represents Artifact
familySpec ContainerContent =
  FamilySpec Container Contains Content
familySpec ProducerProduct =
  FamilySpec Producer Produces Product
familySpec ProductProducer =
  FamilySpec Product ProducedBy Producer
familySpec LocationPeople =
  FamilySpec Place InhabitedBy HumanGroup
familySpec CauserResult =
  FamilySpec Entity Causes Result
familySpec PossessedPossessor =
  FamilySpec Entity PossessedBy Possessor

explicitLabel :: OpenFamily -> String -> String
explicitLabel LocationInstitution source = "the institution of " <> source
explicitLabel LocationTeam source = "the team from " <> source
explicitLabel LocationEvent source = "the event in " <> source
explicitLabel LocationArtifact source = "the work named " <> source
explicitLabel ContainerContent source = "the contents of " <> source
explicitLabel ProducerProduct source = "a product by " <> source
explicitLabel ProductProducer source = "the producer of " <> source
explicitLabel LocationPeople source = "the people at " <> source
explicitLabel CauserResult source = "the result associated with " <> source
explicitLabel PossessedPossessor source = "the possessor of " <> source

predicateConstructor :: OpenFamily -> String
predicateConstructor LocationInstitution = "OpenAgentive"
predicateConstructor LocationTeam = "OpenAgentive"
predicateConstructor LocationEvent = "OpenEventive"
predicateConstructor LocationArtifact = "OpenArtifactive"
predicateConstructor ContainerContent = "OpenConsumptive"
predicateConstructor ProducerProduct = "OpenProductUse"
predicateConstructor ProductProducer = "OpenAgentive"
predicateConstructor LocationPeople = "OpenAgentive"
predicateConstructor CauserResult = "OpenAgentive"
predicateConstructor PossessedPossessor = "OpenAgentive"

normalize :: String -> String
normalize = unwords . words . map normalizeCharacter
  where
    normalizeCharacter character
      | isAlphaNum character = toLower character
      | otherwise = ' '

notElemPhrase :: String -> String -> Bool
notElemPhrase needle haystack =
  not (needle `isInfixOf` haystack)

hasAny :: [String] -> String -> Bool
hasAny triggers sentence =
  any (`isInfixOf` sentence) triggers

agentTriggers, sportsTriggers, eventTriggers, artifactTriggers :: [String]
agentTriggers =
  [ " said "
  , " says "
  , " announced "
  , " decided "
  , " signed "
  , " voted "
  , " agreed "
  , " rejected "
  , " supported "
  , " demanded "
  , " ordered "
  , " warned "
  , " protested "
  , " celebrated "
  , " cheered "
  ]
sportsTriggers =
  [ " beat "
  , " defeated "
  , " won "
  , " lost "
  , " scored "
  , " played "
  , " drew "
  ]
eventTriggers =
  [ " war "
  , " festival "
  , " conference "
  , " olympics "
  , " championship "
  ]
artifactTriggers =
  [ " read "
  , " translated "
  , " published "
  , " watched "
  , " film "
  , " book "
  , " album "
  ]

consumptionTriggers, productUseTriggers :: [String]
consumptionTriggers =
  [ " ate "
  , " eat "
  , " drank "
  , " drink "
  , " consumed "
  , " finished "
  , " emptied "
  , " poured "
  , " ordered "
  ]
productUseTriggers =
  [ " bought "
  , " buy "
  , " wore "
  , " wear "
  , " drove "
  , " drive "
  , " drank "
  , " drink "
  , " read "
  , " watched "
  , " used "
  ]
